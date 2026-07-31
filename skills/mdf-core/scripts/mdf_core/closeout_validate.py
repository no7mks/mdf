import datetime as dt
import subprocess
from pathlib import Path
from typing import Any

from .constants import BUG_TERMINAL_RESOLUTIONS, REQUIREMENT_CLOSED_RESOLUTIONS
from .errors import MDFError
from .gitutil import current_branch
from .paths import load_manifest, relative
from .textutil import stable_semver


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
    *REQUIREMENT_CLOSED_RESOLUTIONS,
    *BUG_TERMINAL_RESOLUTIONS,
}


def require_spec_key(spec: dict[str, Any], key: str) -> Any:
    if key not in spec:
        raise MDFError(
            f"closeout spec 缺少必需字段: {key}",
            code="invalid_closeout_spec",
        )
    return spec[key]


def validate_closeout_attestation(raw: Any) -> dict[str, Any]:
    attestation = require_exact_keys(
        raw,
        {
            "deterministic",
            "semantic",
            "finding_count",
            "validation_commands",
            "summary",
        },
        set(),
        "audit_attestation",
    )
    if (
        attestation["deterministic"] != "passed"
        or attestation["semantic"] != "passed"
        or attestation["finding_count"] != 0
    ):
        raise MDFError(
            "release closeout 要求确定性与语义 attestation 均为零 finding",
            code="audit_not_passed",
        )
    commands = attestation["validation_commands"]
    if (
        not isinstance(commands, list)
        or not commands
        or any(
            not isinstance(command, str) or not command.strip()
            for command in commands
        )
    ):
        raise MDFError(
            "audit_attestation.validation_commands 必须是非空字符串列表",
            code="invalid_closeout_spec",
        )
    summary = attestation["summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise MDFError(
            "audit_attestation.summary 必须是非空字符串",
            code="invalid_closeout_spec",
        )
    return attestation


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


def validate_closeout_shape(
    repo: Path,
    spec: dict[str, Any],
) -> dict[str, Any]:
    if (
        type(spec.get("schema_version")) is not int
        or spec.get("schema_version") != 2
    ):
        raise MDFError(
            "closeout payload 的 schema_version 必须为 2",
            code="invalid_closeout_spec",
        )
    mode = require_spec_key(spec, "mode")
    if mode not in {"release", "hotfix"}:
        raise MDFError(
            "closeout mode 必须是 release 或 hotfix",
            code="invalid_closeout_spec",
        )
    version = require_spec_key(spec, "version")
    candidate = stable_semver(version)
    if candidate is None:
        raise MDFError(
            "closeout version 必须是稳定 SemVer",
            code="invalid_closeout_spec",
        )
    expected_branch = f"{mode}/{version}"
    if spec.get("expected_branch") != expected_branch:
        raise MDFError(
            f"expected_branch must equal {expected_branch}",
            code="invalid_closeout_spec",
        )
    actual_branch = current_branch(repo)
    if actual_branch != expected_branch:
        raise MDFError(
            f"Current branch is {actual_branch}; expected {expected_branch}",
            code="branch_mismatch",
        )
    release_date_raw = require_spec_key(spec, "release_date")
    try:
        release_date = dt.date.fromisoformat(release_date_raw)
    except (TypeError, ValueError) as exc:
        raise MDFError(
            "release_date 必须使用 YYYY-MM-DD",
            code="invalid_closeout_spec",
        ) from exc
    if release_date.isoformat() != release_date_raw:
        raise MDFError(
            "release_date 必须使用规范 YYYY-MM-DD",
            code="invalid_closeout_spec",
        )

    manifest = load_manifest(repo)
    versioning = manifest.get("versioning")
    manifest_previous = (
        versioning.get("latest_release")
        if isinstance(versioning, dict)
        else None
    )
    previous = require_spec_key(spec, "previous_version")
    if previous is not None and stable_semver(previous) is None:
        raise MDFError(
            "previous_version 必须为 null 或稳定 SemVer",
            code="invalid_closeout_spec",
        )
    if previous != manifest_previous:
        raise MDFError(
            "previous_version 与 manifest latest_release 不一致",
            code="release_history_mismatch",
            details={"manifest": manifest_previous, "spec": previous},
        )
    previous_tuple = (0, 0, 0) if previous is None else stable_semver(previous)
    if previous_tuple is None or candidate <= previous_tuple:
        raise MDFError(
            "closeout version 必须大于 previous_version",
            code="not_increasing",
        )
    target = repo / "changes" / version
    if target.exists():
        raise MDFError(
            f"Release directory already exists: {relative(repo, target)}",
            code="collision",
        )

    unreleased = repo / "changes" / "unreleased"
    actual_slugs = (
        sorted(
            path.name
            for path in unreleased.iterdir()
            if path.is_dir() and not path.is_symlink()
        )
        if unreleased.is_dir()
        else []
    )
    release_items = [
        {"slug": slug, "source": f"changes/unreleased/{slug}"}
        for slug in actual_slugs
    ]
    slugs = actual_slugs
    if mode == "release":
        if not slugs:
            raise MDFError(
                "release 模式至少需要一个 unreleased feature/bugfix Change",
                code="invalid_closeout_spec",
            )
    else:
        if slugs:
            raise MDFError(
                "hotfix 分支跳过 unreleased Change；closeout 前须清空 unreleased",
                code="hotfix_unreleased_present",
            )

    raw_closures = require_spec_key(spec, "closures")
    if not isinstance(raw_closures, list):
        raise MDFError(
            "closures must be a list",
            code="invalid_closeout_spec",
        )
    closures: list[dict[str, Any]] = []
    closure_ids: set[str] = set()
    for index, raw_closure in enumerate(raw_closures):
        closure = require_exact_keys(
            raw_closure,
            {"id", "resolution"},
            {"fulfilled_in", "fixed_in"},
            f"closures[{index}]",
        )
        identifier = closure["id"]
        if not isinstance(identifier, str) or identifier in closure_ids:
            raise MDFError(
                "closure IDs must be unique strings",
                code="invalid_closeout_spec",
            )
        resolution = closure["resolution"]
        if (
            not isinstance(resolution, str)
            or resolution not in CLOSURE_RESOLUTIONS
        ):
            raise MDFError(
                f"closures[{index}].resolution 必须是受支持的 resolution",
                code="invalid_closeout_spec",
                details={
                    "id": identifier,
                    "resolution": resolution,
                    "allowed": sorted(CLOSURE_RESOLUTIONS),
                },
            )
        closure_ids.add(identifier)
        closures.append(dict(closure))
    attestation = validate_closeout_attestation(spec.get("audit_attestation"))
    return {
        "mode": mode,
        "version": version,
        "candidate": candidate,
        "previous": previous,
        "previous_tuple": previous_tuple,
        "release_date": release_date.isoformat(),
        "release_items": release_items,
        "hotfix": None,
        "hotfix_change": spec.get("hotfix_change"),
        "closures": closures,
        "attestation": attestation,
        "deferred_acceptance": spec.get("deferred_acceptance", {}),
        "verify_command_results": spec.get("verify_command_results") or [],
    }
