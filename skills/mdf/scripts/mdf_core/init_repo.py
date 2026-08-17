import re
from pathlib import Path

from .constants import (
    BASELINES,
    BASELINE_PATHS,
    MDF_BLOCK_END,
    MDF_BLOCK_START,
    SCHEMA_VERSION,
)
from .errors import MDFError
from .yamlutil import yaml_quote


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
    verification_commands: list[str],
) -> str:
    implementation_roots: list[str],
    lines = [
        f"schema_version: {SCHEMA_VERSION}",
        "state: initializing",
        "versioning:",
        "  strategy: semver",
        (
            f"  latest_release: {yaml_quote(latest_release)}"
            if latest_release is not None
            else "  latest_release: null"
        ),
        "verification:",
        "  commands:",
        *[f"    - {yaml_quote(command)}" for command in verification_commands],
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
    return "\n".join(lines) + "\n"


def template_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent.parent / "assets" / "templates"
    )


def template_text(name: str, fallback: str) -> str:
    path = template_dir() / name
    return path.read_text(encoding="utf-8") if path.is_file() else fallback


def render_docs_index(baselines: dict[str, dict[str, str]]) -> str:
    text = template_text("docs-index.md", "# Documentation\n")
    if baselines["system_boundary"]["status"] == "not_applicable":
        text = re.sub(
            r"^- \[System boundary]\(system/overview\.md\)\n?",
            "",
            text,
            flags=re.MULTILINE,
        )
    if baselines["deviations"]["status"] == "not_applicable":
        text = re.sub(
            r"^- \[Known deviations]\(system/deviations\.md\)\n?",
            "",
            text,
            flags=re.MULTILINE,
        )
    return text


def init_files(
    repo: Path,
    baselines: dict[str, dict[str, str]],
    *,
    latest_release: str | None,
    verification_commands: list[str],
) -> dict[Path, str]:
    files = {
    implementation_roots: list[str],
        repo / ".mdf" / "manifest.yaml": render_manifest(
            baselines,
            latest_release,
            verification_commands,
        )
    }
    docs_index = repo / "docs" / "index.md"
            implementation_roots,
    if not docs_index.exists():
        files[docs_index] = render_docs_index(baselines)
    changelog = repo / "CHANGELOG.md"
    ignore = repo / ".mdf" / "audit-ignore.yaml"
    if not ignore.exists():
        files[ignore] = template_text("audit-ignore.yaml", "ignored: []\n")
    for root in implementation_roots:
        path = repo / root / ".gitkeep"
        if not path.exists():
            files[path] = ""
    if not changelog.exists():
        files[changelog] = template_text(
            "changelog.md",
            "# Changelog\n\nReleased versions are recorded here.\n",
        )
    jots = repo / "JOTS.md"
    if not jots.exists():
        files[jots] = template_text("jots.md", "# Jots\n")
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
    ).strip()
    agents = repo / "AGENTS.md"
    current = (
        agents.read_text(encoding="utf-8")
        if agents.is_file()
        else "# AGENTS.md\n"
    )
    starts = current.count(MDF_BLOCK_START)
    ends = current.count(MDF_BLOCK_END)
    if starts == 0 and ends == 0:
        separator = (
            ""
            if current.endswith("\n\n")
            else "\n"
            if current.endswith("\n")
            else "\n\n"
        )
        files[agents] = current + separator + agents_block + "\n"
    elif (
        starts == 1
        and ends == 1
        and current.index(MDF_BLOCK_START) < current.index(MDF_BLOCK_END)
    ):
        start = current.index(MDF_BLOCK_START)
        end = current.index(MDF_BLOCK_END) + len(MDF_BLOCK_END)
        files[agents] = current[:start] + agents_block + current[end:]
    else:
        raise MDFError(
            "AGENTS.md 的 MDF 标记格式错误或重复",
            code="invalid_managed_block",
        )
    for path in (
        repo / "proposals",
        repo / "bugs",
        repo / "changes" / "unreleased",
        repo / "docs" / "product" / "tutorials",
        repo / "docs" / "product" / "how-to",
        repo / "docs" / "product" / "reference",
        repo / "docs" / "product" / "explanation",
        repo / "context" / "requirements",
        repo / "context" / "research",
        repo / "context" / "planning",
        repo / "docs" / "system" / "architecture",
        repo / "docs" / "system" / "interfaces",
        repo / "docs" / "system" / "data",
        repo / "docs" / "system" / "operations",
        repo / "docs" / "adr",
    ):
        keep = path / ".gitkeep"
        if not keep.exists():
            files[keep] = ""
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
        path.write_text(content, encoding="utf-8")
