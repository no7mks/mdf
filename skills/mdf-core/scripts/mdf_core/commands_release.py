import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import doctor
from .closeout_stage import apply_closeout, summarize_closeout
from .closeout_validate import run_verify_commands
from .errors import MDFError, emit, serialize_findings
from .gitutil import (
    branch_details,
    current_branch,
    ensure_clean,
    repo_path,
    require_git_root,
)
from .paths import ensure_safe_managed_paths, load_manifest
from .yamlutil import read_frontmatter


def _json_argument(raw: str | None, *, name: str, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise MDFError(
            f"{name} must be valid inline JSON", code="invalid_closeout_spec"
        ) from exc


def manifest_verification_commands(manifest: dict[str, Any]) -> list[str]:
    verification = manifest.get("verification")
    commands = (
        verification.get("commands") if isinstance(verification, dict) else None
    )
    if (
        not isinstance(commands, list)
        or not commands
        or any(
            not isinstance(command, str) or not command.strip()
            for command in commands
        )
    ):
        raise MDFError(
            "ready manifest 要求 verification.commands 为非空字符串列表",
            code="invalid_manifest",
        )
    return list(commands)


def derive_closeout_spec(
    repo: Path, args: argparse.Namespace
) -> dict[str, Any]:
    details = branch_details(current_branch(repo))
    if details["kind"] not in {"release", "hotfix"}:
        raise MDFError(
            "release closeout 只接受 release/<version> 或 hotfix/<version>",
            code="unsupported_branch",
        )
    mode = details["kind"]
    version = details["version"]
    manifest = load_manifest(repo)
    versioning = manifest.get("versioning")
    previous = (
        versioning.get("latest_release")
        if isinstance(versioning, dict)
        else None
    )
    release_date = args.release_date or dt.date.today().isoformat()
    if mode == "release":
        slugs = (
            sorted(
                path.name
                for path in (repo / "changes" / "unreleased").iterdir()
                if path.is_dir() and not path.is_symlink()
            )
            if (repo / "changes" / "unreleased").is_dir()
            else []
        )
        requirements: set[str] = set()
        fixed: set[str] = set()
        closed: set[str] = set()
        deferred: set[str] = set()
        closed_resolutions: dict[str, str] = {}
        for slug in slugs:
            metadata, _ = read_frontmatter(
                repo / "changes" / "unreleased" / slug / "CHANGE.md"
            )
            requirements.update(metadata.get("requirements", []))
            fixed.update(metadata.get("fixed", []))
            closed.update(metadata.get("closed", []))
            deferred.update(metadata.get("deferred", []))
            raw_resolutions = metadata.get("closed_resolutions", {})
            if isinstance(raw_resolutions, dict):
                closed_resolutions.update(raw_resolutions)
        hotfix_change = None
    else:
        raw_hotfix = _json_argument(
            args.hotfix_change_json, name="--hotfix-change-json", default={}
        )
        if not isinstance(raw_hotfix, dict):
            raise MDFError(
                "--hotfix-change-json 必须是对象", code="invalid_closeout_spec"
            )
        hotfix_change = dict(raw_hotfix)
        hotfix_change.setdefault("source_branch", f"hotfix/{version}")
        hotfix_change.setdefault("change_kind", "hotfix")
        hotfix_change.setdefault("requirements", [])
        hotfix_change.setdefault("fixed", [])
        hotfix_change.setdefault("closed", [])
        hotfix_change.setdefault("deferred", [])
        hotfix_change.setdefault("adrs", [])
        hotfix_change.setdefault("release_notes", "none")
        hotfix_change.setdefault("breaking", False)
        hotfix_change.setdefault(
            "evidence", {"tests": [], "commands": [], "artifacts": []}
        )
        hotfix_change.setdefault("body", "Hotfix result verified.")
        requirements = set(hotfix_change["requirements"])
        fixed = set(hotfix_change["fixed"])
        closed = set(hotfix_change["closed"])
        deferred = set(hotfix_change["deferred"])
        closed_resolutions = dict(hotfix_change.get("closed_resolutions", {}))

    explicit = _json_argument(
        args.closures_json, name="--closures-json", default=None
    )
    if explicit is None:
        closures: list[dict[str, Any]] = []
        closures.extend(
            {
                "id": identifier,
                "resolution": "fulfilled",
                "fulfilled_in": version,
            }
            for identifier in sorted(requirements)
        )
        closures.extend(
            {"id": identifier, "resolution": "fixed", "fixed_in": version}
            for identifier in sorted(fixed)
        )
        closures.extend(
            {
                "id": identifier,
                "resolution": closed_resolutions.get(identifier, "wont-fix"),
            }
            for identifier in sorted(closed)
        )
        closures.extend(
            {"id": identifier, "resolution": "deferred"}
            for identifier in sorted(deferred)
        )
    else:
        if not isinstance(explicit, list):
            raise MDFError(
                "--closures-json 必须是列表", code="invalid_closeout_spec"
            )
        closures = explicit
    acceptance = _json_argument(
        args.deferred_acceptance_json,
        name="--deferred-acceptance-json",
        default={},
    )
    if not isinstance(acceptance, dict):
        raise MDFError(
            "--deferred-acceptance-json 必须是对象",
            code="invalid_closeout_spec",
        )
    commands = manifest_verification_commands(manifest)
    semantic = _json_argument(
        getattr(args, "semantic_attestation_json", None),
        name="--semantic-attestation-json",
        default=None,
    )
    if semantic is None:
        raise MDFError(
            "必须提供 --semantic-attestation-json",
            code="invalid_closeout_spec",
        )
    if not isinstance(semantic, dict):
        raise MDFError(
            "--semantic-attestation-json 必须是对象",
            code="invalid_closeout_spec",
        )
    if "waivers" in semantic:
        raise MDFError(
            "语义 attestation 禁止 waivers 字段",
            code="invalid_closeout_spec",
            details={"attestation": semantic},
        )
    if (
        semantic.get("semantic") != "passed"
        or semantic.get("finding_count") != 0
    ):
        raise MDFError(
            "语义 attestation 必须声明 semantic 为 passed 且 finding_count 为 0",
            code="audit_not_passed",
            details={"attestation": semantic},
        )
    summary = semantic.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise MDFError(
            "语义 attestation 必须提供非空 summary",
            code="invalid_closeout_spec",
            details={"attestation": semantic},
        )
    return {
        "schema_version": 2,
        "mode": mode,
        "expected_branch": f"{mode}/{version}",
        "version": version,
        "previous_version": previous,
        "release_date": release_date,
        "closures": closures,
        "deferred_acceptance": acceptance,
        "hotfix_change": hotfix_change,
        "audit_attestation": {
            "deterministic": "passed",
            "semantic": "passed",
            "finding_count": 0,
            "validation_commands": commands,
            "summary": summary,
        },
    }


def command_release_closeout(args: argparse.Namespace) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_safe_managed_paths(repo)
    ensure_clean(repo)
    manifest = load_manifest(repo)
    if manifest.get("state") != "ready":
        raise MDFError(
            "release closeout 要求 manifest state 为 ready",
            code="manifest_not_ready",
        )
    pre_findings = doctor.collect_findings(repo, full=True)
    if pre_findings:
        raise MDFError(
            "release closeout 要求全量确定性审计零 finding",
            code="audit_not_passed",
            details={"findings": serialize_findings(pre_findings)},
        )
    spec = derive_closeout_spec(repo, args)
    from .closeout_validate import validate_closeout_shape

    context = validate_closeout_shape(repo, spec)
    if args.dry_run:
        emit(
            {
                "ok": True,
                "operation": "release-closeout",
                "dry_run": True,
                "summary": summarize_closeout(repo, context),
            }
        )
        return

    command_results = run_verify_commands(
        repo,
        context["attestation"]["validation_commands"],
    )
    ensure_clean(repo)
    spec["verify_command_results"] = command_results
    context = validate_closeout_shape(repo, spec)
    result = apply_closeout(repo, context)
    post_findings = doctor.collect_findings(repo, full=True)
    if post_findings:
        raise MDFError(
            "release closeout 的 post-validation 失败；请依据 git 工作树状态人工检查",
            code="post_validation_failed",
            details={"findings": serialize_findings(post_findings)},
        )
    emit(
        {
            "ok": True,
            "operation": "release-closeout",
            "dry_run": False,
            "version": context["version"],
            "release_set": result["slugs"],
            "moves": result["moves"],
            "archived": result["archived"],
            "outcomes": result["outcomes"],
            "semver": result["semver"],
            "rewrites": result["rewrites"],
            "verification": {
                "commands": context["attestation"]["validation_commands"],
                "results": command_results,
            },
            "audit_attestation": context["attestation"],
        }
    )
