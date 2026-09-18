#!/usr/bin/env python3
"""Deterministic local tooling for Mars Development Flow.

Every successful command writes one JSON object to stdout. Expected failures
are JSON on stderr and use a non-zero exit status. The implementation uses only
the Python standard library only, including the built-in YAML subset parser.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import errno
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import unquote

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


TOOL_VERSION = 3
PROTOCOL_VERSION = 3
SCHEMA_VERSION = 3
# A Bug discovered on the current, not-yet-released line is deliberately not
# represented as a fake SemVer.  ``unreleased`` is a state marker, not a
# version and must never be used for fixed_in/released_in or release paths.
UNRELEASED_SENTINEL = "unreleased"


def is_unreleased_sentinel(value: Any) -> bool:
    """True iff *value* is exactly the ``unreleased`` state marker."""
    return value == UNRELEASED_SENTINEL


def contains_unreleased_sentinel(value: Any) -> bool:
    """Recursively check a YAML value (dict/list nesting) for the marker."""
    if is_unreleased_sentinel(value):
        return True
    if isinstance(value, dict):
        return any(
            contains_unreleased_sentinel(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(contains_unreleased_sentinel(item) for item in value)
    return False


def is_unreleased_heading(value: str) -> bool:
    """Case-insensitive ``Unreleased`` match for CHANGELOG release headings."""
    return value.lower() == UNRELEASED_SENTINEL


CHANGELOG_UNRELEASED_HEADING_RE = re.compile(
    rf"^##+\s+\[?{re.escape(UNRELEASED_SENTINEL)}]?\s*$",
    re.MULTILINE | re.IGNORECASE,
)
CHANGELOG_UNRELEASED_ENTRY_RE = re.compile(
    rf"^\s*(?:[-*+]\s+)?{re.escape(UNRELEASED_SENTINEL)}\s*$", re.MULTILINE
)
BUG_SEVERITIES = {"critical", "major", "trivial"}
BUG_REJECT_REASONS = {
    "wont-fix",
    "not-a-bug",
    "cannot-reproduce",
    "obsolete",
    "duplicate",
}
BUG_STATUSES = {"open", "fixed", "closed", "rejected"}
# 收口 payload 仍以 resolution 描述本次操作；持久化 Bug 使用 status/reject-reason。
BUG_TERMINAL_RESOLUTIONS = BUG_REJECT_REASONS - {"duplicate"}
BUG_RESOLUTIONS = {"fixed", "duplicate", *BUG_TERMINAL_RESOLUTIONS}
# Proposal 拒绝原因，用于发布收口的一次性操作输入。
PROPOSAL_CLOSED_RESOLUTIONS = {"wont-do", "duplicate", "obsolete"}
CHANGE_KINDS = {"feature", "bugfix", "release", "hotfix"}
BASELINES = (
    "glossary",
    "user_guide",
    "system_boundary",
    "architecture",
    "interfaces",
    "data",
    "operations",
    "deviations",
)
BASELINE_PATHS = {
    "glossary": "GLOSSARY.md",
    "user_guide": "docs/user-guide/README.md",
    "system_boundary": "docs/system/overview.md",
    "architecture": "docs/system/architecture/index.md",
    "interfaces": "docs/system/interfaces/index.md",
    "data": "docs/system/data/index.md",
    "operations": "docs/system/operations/index.md",
    "deviations": "docs/system/deviations.md",
}
BASELINE_DOC_TYPES = {
    "user_guide": "user-guide",
    "system_boundary": "system-boundary",
    "architecture": "system-architecture",
    "interfaces": "system-interfaces",
    "data": "system-data",
    "operations": "system-operations",
    "deviations": "system-deviations",
}
STABLE_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
EPOCH_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)$")
# PRP：001–999 固定三位；1000 起不再补零。Bug/Jot 仍为四位短码。
_PRP_ID_BODY = r"(?:00[1-9]|0[1-9]\d|[1-9]\d{2,})"
_SHORT_ID_BODY = r"[A-HJ-NP-Z2-9]{4}"
_OBJECT_SLUG = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
# ADR slug 与对象 slug 同形，但必须含字母，避免纯数字序号冒充主题。
_ADR_SLUG = rf"(?=[a-z0-9-]*[a-z]){_OBJECT_SLUG}"
OBJECT_FILE_RE = re.compile(
    rf"^((?:prp-{_PRP_ID_BODY}|bug-{_SHORT_ID_BODY}))-"
    rf"({_OBJECT_SLUG})\.md$"
)
ADR_FILE_RE = re.compile(rf"^({_ADR_SLUG})\.md$")
JOT_ID_RE = re.compile(rf"^jot-{_SHORT_ID_BODY}$")
PRP_ID_RE = re.compile(rf"^prp-{_PRP_ID_BODY}$")
OBJECT_ID_RE = re.compile(
    rf"^(?:prp-{_PRP_ID_BODY}|bug-{_SHORT_ID_BODY}|jot-{_SHORT_ID_BODY}|"
    rf"adr-{_ADR_SLUG})$"
)
OBJECT_ID_SLUG_RE = re.compile(
    rf"^(?:prp-{_PRP_ID_BODY}|bug-[a-hj-np-z2-9]{{4}}|adr-{_OBJECT_SLUG})$"
)
MDF_BLOCK_START = "<!-- MDF:BEGIN -->"
MDF_BLOCK_END = "<!-- MDF:END -->"
MARKER_RE = re.compile(r"\{\{[^{}\n]+\}\}|(?:^|\s)TODO(?:\s|:|$)", re.MULTILINE)
ALL_MARKDOWN_LINK_RE = re.compile(
    r"!?\[[^\]]*]\(([^()]*(?:\([^()]*\)[^()]*)*)\)"
)
FACT_ROOTS = ("docs/user-guide", "docs/system")
ADR_ROOT = "docs/context/adr"
# 不属于当前布局、须由 migrate 收敛的 docs 目录。
RETIRED_DOC_DIRS = ("docs/product", "docs/adr")
MANAGED_ROOTS = (
    ".mdf",
    "AGENTS.md",
    "PROJECT.md",
    "GLOSSARY.md",
    "CHANGELOG.md",
    "changes",
    "docs",
)
USER_GUIDE_DOC_TYPE = "user-guide"
DOC_TYPES = {
    USER_GUIDE_DOC_TYPE,
    "system-boundary",
    "system-architecture",
    "system-interfaces",
    "system-data",
    "system-operations",
    "system-deviations",
}
SYSTEM_DOC_TYPES = {
    "overview.md": "system-boundary",
    "architecture": "system-architecture",
    "interfaces": "system-interfaces",
    "data": "system-data",
    "operations": "system-operations",
    "deviations.md": "system-deviations",
}
# 文档体积（物理行）：按加载角色分软硬限制；软限制超出为 warning，硬限制超出为
# finding。GLOSSARY.md 与 changes/ 材料不检查。
SIZE_ROUTER = ("router", 80, 120)
SIZE_PROJECT = ("project", 200, 400)
SIZE_FACT = ("fact", 400, 500)
SIZE_ADR = ("adr", 200, 400)
SIZE_WORK_ITEM = ("work-item", None, 500)
ENTRY_DOCUMENTS = ("README.md", "AGENTS.md", "PROJECT.md", "docs/README.md")
CHANGELOG_CATEGORIES = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
)
