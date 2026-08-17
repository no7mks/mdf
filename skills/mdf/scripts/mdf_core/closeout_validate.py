import subprocess
from pathlib import Path
from typing import Any

from .constants import (
    BUG_TERMINAL_RESOLUTIONS,
    CHANGELOG_CATEGORIES,
    PROPOSAL_CLOSED_RESOLUTIONS,
)
from .errors import MDFError


def require_exact_keys(
    value: Any,
    required: set[str],
    optional: set[str],
    context: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MDFError(
            f"{context} must be an object", code="invalid_closeout_spec"
        )
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing or unknown:
        raise MDFError(
            f"{context} has missing or unknown keys",
            code="invalid_closeout_spec",
            details={
                "context": context,
                "missing": missing,
                "unknown": unknown,
            },
        )
    return value


CLOSURE_RESOLUTIONS = {
    "fulfilled",
    "fixed",
    "deferred",
    *PROPOSAL_CLOSED_RESOLUTIONS,
    *BUG_TERMINAL_RESOLUTIONS,
}

HOTFIX_REQUIRED_FIELDS = {"body", "evidence", "release_notes"}
HOTFIX_OPTIONAL_FIELDS = {
    "proposals",
    "fixed",
    "closed",
    "deferred",
    "closed_resolutions",
    "adrs",
    "breaking",
}


def _string_list(raw: Any, context: str) -> list[str]:
    if not isinstance(raw, list) or any(
        not isinstance(value, str) or not value.strip() for value in raw
    ):
        raise MDFError(
            f"{context} 必须是非空字符串元素组成的列表",
            code="invalid_closeout_spec",
        )
    return list(raw)


def _hotfix_release_notes(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        raise MDFError(
            "hotfix release_notes 必须是类别映射",
            code="invalid_closeout_spec",
        )
    unknown = sorted(set(raw) - set(CHANGELOG_CATEGORIES))
    if unknown:
        raise MDFError(
            "hotfix release_notes 含未知类别",
            code="invalid_closeout_spec",
            details={"unknown": unknown},
        )
    notes: dict[str, list[str]] = {}
    for category, values in raw.items():
        if category not in CHANGELOG_CATEGORIES:
            continue
        notes[category] = _string_list(
            values,
            f"hotfix release_notes.{category}",
        )
    if not any(notes.values()):
        raise MDFError(
            "hotfix release_notes 至少需要一条非空 release note",
            code="invalid_closeout_spec",
        )
    return notes


def _hotfix_evidence(raw: Any) -> dict[str, list[str]]:
    evidence = require_exact_keys(
        raw,
        {"tests", "commands", "artifacts"},
        set(),
        "hotfix evidence",
    )
    normalized = {
        key: _string_list(evidence[key], f"hotfix evidence.{key}")
        for key in ("tests", "commands", "artifacts")
    }
    if not any(normalized.values()):
        raise MDFError(
            "hotfix evidence 至少需要一条证据",
            code="invalid_closeout_spec",
        )
    return normalized


def normalize_hotfix_change(raw: Any, version: str) -> dict[str, Any]:
    """Validate user JSON and add only Core-owned hotfix identity fields."""
    change = require_exact_keys(
        raw,
        HOTFIX_REQUIRED_FIELDS,
        HOTFIX_OPTIONAL_FIELDS,
        "--hotfix-change-json",
    )
    body = change["body"]
    if not isinstance(body, str) or not body.strip():
        raise MDFError(
            "hotfix body 必须是非空字符串",
            code="invalid_closeout_spec",
        )
    breaking = change.get("breaking", False)
    if not isinstance(breaking, bool):
        raise MDFError(
            "hotfix breaking 必须是布尔值",
            code="invalid_closeout_spec",
        )
    release_notes = _hotfix_release_notes(change["release_notes"])
    if "Removed" in release_notes and breaking is not True:
        raise MDFError(
            "hotfix Removed release note 要求 breaking 为 true",
            code="invalid_closeout_spec",
        )
    normalized: dict[str, Any] = {
        "change_kind": "hotfix",
        "source_branch": f"hotfix/{version}",
        "body": body,
        "proposals": _string_list(
            change.get("proposals", []),
            "hotfix proposals",
        ),
        "fixed": _string_list(change.get("fixed", []), "hotfix fixed"),
        "closed": _string_list(change.get("closed", []), "hotfix closed"),
        "deferred": _string_list(
            change.get("deferred", []),
            "hotfix deferred",
        ),
        "adrs": _string_list(change.get("adrs", []), "hotfix adrs"),
        "release_notes": release_notes,
        "breaking": breaking,
        "evidence": _hotfix_evidence(change["evidence"]),
    }
    closed = normalized["closed"]
    if len(closed) != len(set(closed)):
        raise MDFError(
            "hotfix closed 不能包含重复 Bug ID",
            code="invalid_closeout_spec",
        )
    outcomes = [
        identifier
        for key in ("fixed", "closed", "deferred")
        for identifier in normalized[key]
    ]
    if len(outcomes) != len(set(outcomes)):
        raise MDFError(
            "hotfix 的每个 Bug 只能有一个 outcome",
            code="invalid_closeout_spec",
        )
    raw_resolutions = change.get("closed_resolutions", {})
    if not isinstance(raw_resolutions, dict) or any(
        not isinstance(identifier, str)
        or not identifier.strip()
        or not isinstance(resolution, str)
        or resolution not in BUG_TERMINAL_RESOLUTIONS
        for identifier, resolution in raw_resolutions.items()
    ):
        raise MDFError(
            "hotfix closed_resolutions 必须是终态 Bug resolution 映射",
            code="invalid_closeout_spec",
        )
    if set(raw_resolutions) != set(closed):
        raise MDFError(
            "hotfix closed_resolutions 必须精确覆盖 closed Bug ID",
            code="invalid_closeout_spec",
        )
    normalized["closed_resolutions"] = dict(raw_resolutions)
    return normalized


def require_spec_key(spec: dict[str, Any], key: str) -> Any:
    if key not in spec:
        raise MDFError(
            f"closeout spec 缺少必需字段: {key}",
            code="invalid_closeout_spec",
        )
    return spec[key]


def run_verify_commands(
    repo: Path, commands: list[str]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                cwd=repo,
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            raise MDFError(
                f"verification command 超时（600 秒）: {command}",
                code="verify_command_failed",
                details={
                    "command": command,
                    "timeout_seconds": 600,
                    "results": results,
                },
            ) from exc
        entry = {
            "command": command,
            "exit_code": completed.returncode,
        }
        results.append(entry)
        if completed.returncode != 0:
            raise MDFError(
                f"verification command 失败: {command}",
                code="verify_command_failed",
                details={
                    "command": command,
                    "exit_code": completed.returncode,
                    "stdout_tail": completed.stdout[-2000:],
                    "stderr_tail": completed.stderr[-2000:],
                    "results": results,
                },
            )
    return results
