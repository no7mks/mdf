import re
from pathlib import Path
from typing import Any

from mdf_core.foundation.constants import (
    BASELINES,
    BASELINE_PATHS,
    MDF_BLOCK_END,
    MDF_BLOCK_START,
    SCHEMA_VERSION,
    TESTING_CONVENTIONS,
    TESTING_INDEX,
)
from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.paths import load_manifest, manifest_path
from mdf_core.foundation.yamlutil import parse_yaml, yaml_quote
from mdf_core.workspace.agents_block import block_span, render_block


def parse_baselines(values: list[str]) -> dict[str, dict[str, str]]:
    parsed: dict[str, dict[str, str]] = {}
    for raw in values:
        if "=" not in raw:
            raise MDFError(
                f"Baseline must be NAME=STATUS[:REASON]: {raw}",
                code="bad_baseline",
            )
        name, remainder = raw.split("=", 1)
        if name not in BASELINES:
            raise MDFError(f"Unknown baseline: {name}", code="bad_baseline")
        status, separator, reason = remainder.partition(":")
        if status not in ("documented", "not_applicable"):
            raise MDFError(
                f"Invalid baseline status for {name}: {status}",
                code="bad_baseline",
            )
        entry = {"status": status}
        if status == "not_applicable":
            if not separator or not reason.strip():
                raise MDFError(
                    f"{name}=not_applicable requires a reason",
                    code="bad_baseline",
                )
            entry["reason"] = reason.strip()
        else:
            declared_path = (
                reason.strip() if separator else BASELINE_PATHS[name]
            )
            if "\n" in declared_path or "\r" in declared_path:
                raise MDFError(
                    f"{name}=documented path must not contain newlines",
                    code="bad_baseline",
                )
            raw_path = Path(declared_path)
            if (
                not declared_path
                or raw_path.is_absolute()
                or ".." in raw_path.parts
            ):
                raise MDFError(
                    f"{name}=documented path must be repository-relative",
                    code="bad_baseline",
                )
            entry["path"] = raw_path.as_posix()
        if name in parsed:
            raise MDFError(f"Duplicate baseline: {name}", code="bad_baseline")
        parsed[name] = entry
    missing = sorted(set(BASELINES) - set(parsed))
    if missing:
        raise MDFError(
            "Every baseline must be declared",
            code="missing_baselines",
            details={"missing": missing},
        )
    return parsed


def render_manifest(
    baselines: dict[str, dict[str, str]],
    latest_release: str | None,
    implementation_roots: list[str],
    logo: str | None = None,
    hooks: dict | None = None,
    rules: dict | None = None,
    closeout: dict | None = None,
    workflow: dict | None = None,
) -> str:
    lines = [
        f"schema_version: {SCHEMA_VERSION}",
        "state: initializing",
        f"logo: {yaml_quote(logo or '📍')}",
        "versioning:",
        "  strategy: semver",
        (
            f"  latest_release: {yaml_quote(latest_release)}"
            if latest_release is not None
            else "  latest_release: null"
        ),
        "implementation_roots:",
        *[f"  - {yaml_quote(root)}" for root in implementation_roots],
        "baselines:",
    ]
    for name in BASELINES:
        entry = baselines[name]
        lines.append(f"  {name}:")
        lines.append(f"    status: {entry['status']}")
        if "path" in entry:
            lines.append(f"    path: {yaml_quote(entry['path'])}")
        if "reason" in entry:
            lines.append(f"    reason: {yaml_quote(entry['reason'])}")
    if hooks:
        from mdf_core.workspace.hooks import validate_hooks
        validate_hooks({"hooks": hooks})
        lines.append("hooks:")
        for name, entry in hooks.items():
            lines.extend([f"  {name}:", f"    type: {entry['type']}",
                          f"    path: {yaml_quote(entry['path'])}"])
    if rules is not None:
        from mdf_core.workspace.project_rules import validate_rules
        validate_rules({"rules": rules})
        lines.append("rules:" if rules else "rules: {}")
        for stage, path in rules.items():
            lines.append(f"  {stage}: {yaml_quote(path)}")
    if workflow is not None:
        from mdf_core.workspace.workflow_policy import parse_workflow, render_workflow_lines
        lines.extend(render_workflow_lines(parse_workflow({"workflow": workflow})))
    if closeout is not None:
        from mdf_core.workspace.merge_policy import config
        from mdf_core.workspace.workflow_policy import render_closeout_lines
        lines.extend(render_closeout_lines(config({"closeout": closeout})))
    return "\n".join(lines) + "\n"


def template_dir() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "assets" / "templates"
    )


def template_text(name: str, fallback: str) -> str:
    path = template_dir() / name
    return path.read_text(encoding="utf-8") if path.is_file() else fallback


# not_applicable 基线对应的文档入口链接行；模板中每条链接独占一行。
_INDEX_LINES_BY_BASELINE = {
    "user_guide": (r"user-guide/README\.md",),
    "system_boundary": (r"system/overview\.md",),
    "deviations": (r"system/deviations\.md",),
}


def render_docs_index(baselines: dict[str, dict[str, str]]) -> str:
    text = template_text("docs-readme.md", "# 文档\n")
    for name, patterns in _INDEX_LINES_BY_BASELINE.items():
        if baselines[name]["status"] != "not_applicable":
            continue
        for pattern in patterns:
            text = re.sub(
                rf"^.*\]\({pattern}\).*\n?", "", text, flags=re.MULTILINE
            )
    return text


def init_files(
    repo: Path,
    baselines: dict[str, dict[str, str]],
    *,
    latest_release: str | None,
    verification: dict[str, Any],
    implementation_roots: list[str],
    workflow: dict[str, str] | None = None,
    closeout_mode: str | None = None,
    closeout_provider: str | None = None,
) -> dict[Path, str]:
    from mdf_core.execution.modules_check import render_modules_yaml

    manifest = load_manifest(repo) if manifest_path(repo).is_file() else {}
    from mdf_core.workspace.project_rules import validate_rules
    validate_rules(manifest)
    from mdf_core.workspace.merge_policy import config
    closeout = config(manifest)
    if closeout_mode is not None:
        closeout["mode"] = closeout_mode
    if closeout_provider is not None:
        closeout["provider"] = closeout_provider
    files = {
        repo / ".mdf" / "manifest.yaml": render_manifest(
            baselines,
            latest_release,
            implementation_roots,
            logo=manifest.get("logo"),
            hooks=manifest.get("hooks"),
            rules=manifest.get("rules"),
            closeout=closeout if "closeout" in manifest or closeout_mode or closeout_provider else None,
            workflow=workflow if workflow is not None else manifest.get("workflow"),
        )
    }
    modules = repo / ".mdf" / "modules.yaml"
    if not modules.exists():
        overrides = verification.get("overrides")
        if isinstance(overrides, dict) and overrides:
            commands = overrides
        else:
            commands = verification.get("commands", verification)
        budgets = verification.get("budgets", {})
        sourceset = [f"{root}/**" for root in implementation_roots]
        files[modules] = render_modules_yaml(
            sourceset=sourceset or ["src/**"],
            lint=commands["lint"],
            build=commands["build"],
            quick=commands["quick"],
            smoke=commands["smoke"],
            release=commands["release"],
            budgets=budgets or None,
            tests_quick=["tests/**"],
            tests_smoke=["tests/**"],
            tests_release=["tests/**"],
        )
    for root in implementation_roots:
        path = repo / root / ".gitkeep"
        if not path.exists():
            files[path] = ""
    docs_index = repo / "docs" / "README.md"
    if not docs_index.exists():
        files[docs_index] = render_docs_index(baselines)
    changelog = repo / "CHANGELOG.md"
    if not changelog.exists():
        files[changelog] = template_text(
            "changelog.md",
            "# Changelog\n\n本文件记录已发布的版本。\n",
        )
    jots = repo / "docs/JOTS.md"
    if not jots.exists():
        files[jots] = template_text("jots.md", "# 随手记录\n")
    for name, fallback in (
        ("GLOSSARY.md", "# Glossary\n"),
        ("PROJECT.md", "# Project\n"),
    ):
        path = repo / name
        if not path.exists():
            files[path] = template_text(name.lower(), fallback)
    agents_block = template_text(
        "agents-managed-block.md",
        f"{MDF_BLOCK_START}\n"
        "Use repository-local Mars Development Flow records "
        "as versioned context.\n"
        f"{MDF_BLOCK_END}\n",
    )
    agents_block = render_block(agents_block, parse_yaml(files[manifest_path(repo)]))
    agents = repo / "AGENTS.md"
    current = (
        agents.read_bytes().decode("utf-8")
        if agents.is_file()
        else "# AGENTS.md\n"
    )
    span = block_span(current)
    if span is None:
        separator = (
            ""
            if current.endswith("\n\n")
            else "\n"
            if current.endswith("\n")
            else "\n\n"
        )
        files[agents] = current + separator + agents_block + "\n"
    else:
        start, end = span
        files[agents] = current[:start] + agents_block + current[end:]
    for path in (
        repo / "docs/proposals",
        repo / "docs/bugs",
        repo / "changes/unreleased",
        repo / "docs/context/research",
        repo / "docs/context/adr",
        repo / "docs" / "user-guide",
        repo / "docs" / "system" / "architecture",
        repo / "docs" / "system" / "interfaces",
        repo / "docs" / "system" / "data",
        repo / "docs" / "system" / "operations",
    ):
        keep = path / ".gitkeep"
        if not keep.exists():
            files[keep] = ""
    testing_index = repo / TESTING_INDEX
    if not testing_index.exists():
        files[testing_index] = template_text(
            "system-testing-index.md",
            "# 测试\n",
        )
    testing_conventions = repo / TESTING_CONVENTIONS
    if not testing_conventions.exists():
        files[testing_conventions] = template_text(
            "system-testing-conventions.md",
            "# 测试约定\n",
        )
    return files


def write_files(
    files: dict[Path, str], *, replace_allowed: set[Path] | None = None
) -> None:
    allowed = replace_allowed or set()
    existing = [
        str(path) for path in files if path.exists() and path not in allowed
    ]
    if existing:
        raise MDFError(
            "初始化会覆盖已有文件",
            code="init_collision",
            details={"paths": existing},
        )
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
