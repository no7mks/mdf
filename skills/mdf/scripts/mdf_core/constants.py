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


TOOL_VERSION = 2
PROTOCOL_VERSION = 2
SCHEMA_VERSION = 2
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
    "product_reference",
    "system_boundary",
    "architecture",
    "interfaces",
    "data",
    "operations",
    "deviations",
)
BASELINE_PATHS = {
    "glossary": "GLOSSARY.md",
    "product_reference": "docs/product/reference/index.md",
    "system_boundary": "docs/system/overview.md",
    "architecture": "docs/system/architecture/index.md",
    "interfaces": "docs/system/interfaces/index.md",
    "data": "docs/system/data/index.md",
    "operations": "docs/system/operations/index.md",
    "deviations": "docs/system/deviations.md",
}
BASELINE_DOC_TYPES = {
    "product_reference": "product-reference",
    "system_boundary": "system-boundary",
    "architecture": "system-architecture",
    "interfaces": "system-interfaces",
    "data": "system-data",
    "operations": "system-operations",
    "deviations": "system-deviations",
}
STABLE_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
EPOCH_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)$")
OBJECT_FILE_RE = re.compile(
    r"^((?:prp|bug)-[A-HJ-NP-Z2-9]{4})-"
    r"([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)\.md$"
)
JOT_ID_RE = re.compile(r"^jot-[A-HJ-NP-Z2-9]{4}$")
OBJECT_ID_RE = re.compile(
    r"^(?:(?:prp|bug|jot)-[A-HJ-NP-Z2-9]{4}|adr-\d{4})$"
)
OBJECT_ID_SLUG_RE = re.compile(r"^(?:prp|bug)-[a-hj-np-z2-9]{4}$")
MDF_BLOCK_START = "<!-- MDF:BEGIN -->"
MDF_BLOCK_END = "<!-- MDF:END -->"
MARKER_RE = re.compile(r"\{\{[^{}\n]+\}\}|(?:^|\s)TODO(?:\s|:|$)", re.MULTILINE)
ALL_MARKDOWN_LINK_RE = re.compile(
    r"!?\[[^\]]*]\(([^()]*(?:\([^()]*\)[^()]*)*)\)"
)
FACT_ROOTS = ("docs/product", "docs/system")
MANAGED_ROOTS = (
    ".mdf",
    "AGENTS.md",
    "PROJECT.md",
    "GLOSSARY.md",
    "CHANGELOG.md",
    "docs",
)
DOC_TYPES = {
    "product-tutorial",
    "product-how-to",
    "product-reference",
    "product-explanation",
    "system-boundary",
    "system-architecture",
    "system-interfaces",
    "system-data",
    "system-operations",
    "system-deviations",
}
PRODUCT_DOC_TYPES = {
    "tutorials": "product-tutorial",
    "how-to": "product-how-to",
    "reference": "product-reference",
    "explanation": "product-explanation",
}
SYSTEM_DOC_TYPES = {
    "overview.md": "system-boundary",
    "architecture": "system-architecture",
    "interfaces": "system-interfaces",
    "data": "system-data",
    "operations": "system-operations",
    "deviations.md": "system-deviations",
}
CHANGELOG_CATEGORIES = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
)
