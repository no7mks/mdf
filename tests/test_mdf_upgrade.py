"""已安装 MDF Skill 的预览与替换。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from conftest import skill_dir
from mdf_test_support import git, init_git, mdf, payload

BEGIN = "<!-- MDF:BEGIN -->"
END = "<!-- MDF:END -->"


def write_agents_template(skill: Path, body: str) -> None:
    folder = skill / "assets" / "templates"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "agents-managed-block.md").write_text(
        f"{BEGIN}\n{body}\n{END}\n", encoding="utf-8"
    )


def init_upstream(
    tmp_path: Path, marker: str, *, agents_body: str | None = None
) -> Path:
    source = tmp_path / "upstream"
    skill = source / "skills" / "mdf"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"{marker}\n", encoding="utf-8")
    (skill / "references" / "note.md").write_text("skill\n", encoding="utf-8")
    if agents_body is not None:
        write_agents_template(skill, agents_body)
    init_git(source)
    return source


def write_installed(repo: Path, folder: str, marker: str, version: str) -> Path:
    skill = repo / folder / "mdf"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"{marker}\n", encoding="utf-8")
    (skill / "references" / ".version").write_text(
        f"{version}\n", encoding="utf-8"
    )
    return skill


def init_target(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("app\n", encoding="utf-8")
    (target / "docs").mkdir()
    (target / "docs" / "README.md").write_text("keep-docs\n", encoding="utf-8")
    (target / ".mdf").mkdir()
    (target / ".mdf" / "manifest.yaml").write_text(
        "keep-mdf\n", encoding="utf-8"
    )
    (target / "skills" / "mdf").mkdir(parents=True)
    (target / "skills" / "mdf" / "SKILL.md").write_text(
        "source-tree\n", encoding="utf-8"
    )
    write_installed(target, ".codex/skills", "old-codex", "old-codex-hash")
    write_installed(target, ".cursor/skills", "old-cursor", "old-cursor-hash")
    init_git(target)
    return target


def source_head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def test_upgrade_default_source_is_mars_mdf() -> None:
    scripts = str((skill_dir("mdf") / "scripts").resolve())
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from mdf_core.upgrade import DEFAULT_SKILL_SOURCE

    assert DEFAULT_SKILL_SOURCE == "http://10.1.5.65:8929/mars/mdf"


def test_upgrade_dry_run_does_not_replace(python_exe: str, tmp_path: Path) -> None:
    upstream = init_upstream(tmp_path, "new-skill")
    target = init_target(tmp_path)
    commit = source_head(upstream)

    data = payload(
        mdf(
            python_exe,
            "upgrade",
            "--repo",
            str(target),
            "--source",
            str(upstream),
            "--dry-run",
        )
    )

    assert data["ok"] is True
    assert data["dry_run"] is True
    assert data["new_commit"] == commit
    assert data["source"] == str(upstream)
    paths = {item["path"]: item["current_commit"] for item in data["targets"]}
    assert paths[".codex/skills/mdf"] == "old-codex-hash"
    assert paths[".cursor/skills/mdf"] == "old-cursor-hash"
    assert data["agents"] == {
        "path": "AGENTS.md",
        "action": "skip",
        "reason": "absent",
    }
    assert (target / ".codex/skills/mdf/SKILL.md").read_text(
        encoding="utf-8"
    ) == "old-codex\n"
    assert (target / "docs" / "README.md").read_text(encoding="utf-8") == (
        "keep-docs\n"
    )


def test_upgrade_replaces_installed_copies_only(
    python_exe: str, tmp_path: Path
) -> None:
    upstream = init_upstream(tmp_path, "new-skill")
    target = init_target(tmp_path)
    commit = source_head(upstream)

    data = payload(
        mdf(
            python_exe,
            "upgrade",
            "--repo",
            str(target),
            "--source",
            str(upstream),
        )
    )

    assert data["ok"] is True
    assert data["dry_run"] is False
    assert data["new_commit"] == commit
    assert set(data["replaced"]) == {
        ".codex/skills/mdf",
        ".cursor/skills/mdf",
    }
    for folder in (".codex/skills/mdf", ".cursor/skills/mdf"):
        skill = target / folder
        assert skill.joinpath("SKILL.md").read_text(encoding="utf-8") == (
            "new-skill\n"
        )
        assert skill.joinpath("references", ".version").read_text(
            encoding="utf-8"
        ) == f"{commit}\n"
    assert (target / "skills" / "mdf" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "source-tree\n"
    assert (target / "docs" / "README.md").read_text(encoding="utf-8") == (
        "keep-docs\n"
    )
    assert (target / ".mdf" / "manifest.yaml").read_text(
        encoding="utf-8"
    ) == "keep-mdf\n"
    assert data["agents"] == {
        "path": "AGENTS.md",
        "action": "skip",
        "reason": "absent",
    }


def test_upgrade_requires_an_installed_skill(
    python_exe: str, tmp_path: Path
) -> None:
    upstream = init_upstream(tmp_path, "new-skill")
    target = tmp_path / "plain"
    target.mkdir()
    (target / "README.md").write_text("app\n", encoding="utf-8")
    (target / "skills" / "mdf").mkdir(parents=True)
    (target / "skills" / "mdf" / "SKILL.md").write_text(
        "source-tree\n", encoding="utf-8"
    )
    init_git(target)

    result = mdf(
        python_exe,
        "upgrade",
        "--repo",
        str(target),
        "--source",
        str(upstream),
        "--dry-run",
    )
    assert result.returncode != 0
    error = json.loads(result.stderr)
    assert error["error"] == "upgrade_no_install"
    assert (target / "skills" / "mdf" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "source-tree\n"


def test_upgrade_rejects_missing_upstream_skill(
    python_exe: str, tmp_path: Path
) -> None:
    source = tmp_path / "empty"
    source.mkdir()
    (source / "README.md").write_text("no-skill\n", encoding="utf-8")
    init_git(source)
    target = init_target(tmp_path)

    result = mdf(
        python_exe,
        "upgrade",
        "--repo",
        str(target),
        "--source",
        str(source),
        "--dry-run",
    )
    assert result.returncode != 0
    error = json.loads(result.stderr)
    assert error["error"] == "upgrade_missing_skill"
    assert (target / ".codex/skills/mdf/SKILL.md").read_text(
        encoding="utf-8"
    ) == "old-codex\n"


def write_agents(repo: Path, body: str, extra: str = "") -> str:
    text = f"# Existing rules\n\n{BEGIN}\n{body}\n{END}\n{extra}"
    (repo / "AGENTS.md").write_text(text, encoding="utf-8")
    return text


def test_upgrade_updates_existing_agents_managed_block(
    python_exe: str, tmp_path: Path
) -> None:
    upstream = init_upstream(tmp_path, "new-skill", agents_body="new-block")
    target = init_target(tmp_path)
    write_agents(target, "old-block", extra="\nKeep this exact rule.\n")

    data = payload(
        mdf(
            python_exe,
            "upgrade",
            "--repo",
            str(target),
            "--source",
            str(upstream),
        )
    )

    assert data["agents"] == {"path": "AGENTS.md", "action": "update"}
    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# Existing rules\n\n")
    assert f"{BEGIN}\nnew-block\n{END}" in agents
    assert "old-block" not in agents
    assert "Keep this exact rule." in agents
    assert (target / ".codex/skills/mdf/SKILL.md").read_text(
        encoding="utf-8"
    ) == "new-skill\n"


def test_upgrade_dry_run_does_not_write_agents_block(
    python_exe: str, tmp_path: Path
) -> None:
    upstream = init_upstream(tmp_path, "new-skill", agents_body="new-block")
    target = init_target(tmp_path)
    original = write_agents(target, "old-block")

    data = payload(
        mdf(
            python_exe,
            "upgrade",
            "--repo",
            str(target),
            "--source",
            str(upstream),
            "--dry-run",
        )
    )

    assert data["dry_run"] is True
    assert data["agents"]["action"] == "update"
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == original
    assert (target / ".codex/skills/mdf/SKILL.md").read_text(
        encoding="utf-8"
    ) == "old-codex\n"


def test_upgrade_skips_agents_without_managed_block(
    python_exe: str, tmp_path: Path
) -> None:
    upstream = init_upstream(tmp_path, "new-skill", agents_body="new-block")
    target = init_target(tmp_path)
    original = "# Local agent notes\n"
    (target / "AGENTS.md").write_text(original, encoding="utf-8")

    data = payload(
        mdf(
            python_exe,
            "upgrade",
            "--repo",
            str(target),
            "--source",
            str(upstream),
        )
    )

    assert data["agents"] == {
        "path": "AGENTS.md",
        "action": "skip",
        "reason": "no_block",
    }
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == original
    assert (target / ".codex/skills/mdf/SKILL.md").read_text(
        encoding="utf-8"
    ) == "new-skill\n"


def test_upgrade_reports_unchanged_agents_block(
    python_exe: str, tmp_path: Path
) -> None:
    upstream = init_upstream(tmp_path, "new-skill", agents_body="same-block")
    target = init_target(tmp_path)
    original = write_agents(target, "same-block")

    data = payload(
        mdf(
            python_exe,
            "upgrade",
            "--repo",
            str(target),
            "--source",
            str(upstream),
        )
    )

    assert data["agents"] == {"path": "AGENTS.md", "action": "unchanged"}
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == original


def test_upgrade_rejects_invalid_agents_block_before_replace(
    python_exe: str, tmp_path: Path
) -> None:
    upstream = init_upstream(tmp_path, "new-skill", agents_body="new-block")
    target = init_target(tmp_path)
    (target / "AGENTS.md").write_text(
        f"{BEGIN}\nfirst\n{END}\n{BEGIN}\nsecond\n{END}\n",
        encoding="utf-8",
    )

    result = mdf(
        python_exe,
        "upgrade",
        "--repo",
        str(target),
        "--source",
        str(upstream),
    )
    assert result.returncode != 0
    error = json.loads(result.stderr)
    assert error["error"] == "invalid_managed_block"
    assert (target / ".codex/skills/mdf/SKILL.md").read_text(
        encoding="utf-8"
    ) == "old-codex\n"
    assert (target / "AGENTS.md").read_text(encoding="utf-8").count(BEGIN) == 2


def test_upgrade_requires_template_when_updating_agents_block(
    python_exe: str, tmp_path: Path
) -> None:
    upstream = init_upstream(tmp_path, "new-skill")
    target = init_target(tmp_path)
    original = write_agents(target, "old-block")

    result = mdf(
        python_exe,
        "upgrade",
        "--repo",
        str(target),
        "--source",
        str(upstream),
    )
    assert result.returncode != 0
    error = json.loads(result.stderr)
    assert error["error"] == "upgrade_missing_agents_template"
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == original
    assert (target / ".codex/skills/mdf/SKILL.md").read_text(
        encoding="utf-8"
    ) == "old-codex\n"
