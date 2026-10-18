"""upgrade 的预览、替换、托管区块更新与上游变动保护。"""
from __future__ import annotations
from types import SimpleNamespace
from mdf_test_support import *  # noqa: F403
import json
import sys
from pathlib import Path
from conftest import skill_dir
from mdf_test_support import git, init_git, mdf, payload
from support_delivery import *  # noqa: F403
from support_upgrade import *  # noqa: F403


def test_upgrade_rejects_source_movement_before_writing(python_exe, tmp_path):
    upstream = init_upstream(tmp_path, "reviewed")
    repo = init_target(tmp_path)
    preview = payload(mdf(python_exe, "upgrade", "--repo", str(repo), "--source", str(upstream), "--dry-run"))
    head = source_head(repo)
    (upstream / "skills/mdf/SKILL.md").write_text("not reviewed\n")
    commit(upstream)
    result = mdf(python_exe, "upgrade", "--repo", str(repo), "--source", str(upstream),
                 "--expected-commit", preview["new_commit"])
    assert "upgrade_source_changed" in result.stderr
    assert source_head(repo) == head
    assert (repo / ".codex/skills/mdf/SKILL.md").read_text() == "old-codex\n"
    missing = mdf(python_exe, "upgrade", "--repo", str(repo), "--source", str(upstream))
    assert "missing_expected_commit" in missing.stderr


BEGIN = "<!-- MDF:BEGIN -->"


END = "<!-- MDF:END -->"


def names_at_head(repo: Path) -> set[str]:
    raw = git(repo, "diff-tree", "--no-commit-id", "-r", "--name-only", "HEAD")
    return set(raw.stdout.splitlines())


def test_upgrade_default_source_is_mars_mdf() -> None:
    scripts = str((skill_dir("mdf") / "scripts").resolve())
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from mdf_core.workspace.upgrade import DEFAULT_SKILL_SOURCE

    assert DEFAULT_SKILL_SOURCE == "http://10.1.5.65:8929/mars/mdf"


def test_upgrade_dry_run_does_not_replace(python_exe: str, tmp_path: Path) -> None:
    upstream = init_upstream(tmp_path, "new-skill")
    target = init_target(tmp_path)
    before = source_head(target)
    commit = source_head(upstream)

    data = payload(
        mdf(
            python_exe,
            "upgrade",
            "--repo",
            str(target),
            "--source",
            str(upstream), "--expected-commit", source_head(upstream),
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
    assert {item["from"] for item in data["history"]} == {
        "old-codex-hash",
        "old-cursor-hash",
    }
    assert all(item["status"] == "unknown_base" for item in data["history"])
    assert data["commit"] == {
        "action": "planned",
        "paths": [".codex/skills/mdf", ".cursor/skills/mdf"],
        "message": f"chore(mdf): 升级已安装 Skill 到 {commit[:12]}",
    }
    assert source_head(target) == before
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
    (target / "README.md").write_text("dirty-keep\n", encoding="utf-8")
    before = source_head(target)
    commit = source_head(upstream)

    data = payload(
        mdf(
            python_exe,
            "upgrade",
            "--repo",
            str(target),
            "--source",
            str(upstream), "--expected-commit", source_head(upstream),
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
    assert data["commit"]["action"] == "created"
    assert data["commit"]["commit"] == source_head(target)
    assert data["commit"]["message"] == (
        f"chore(mdf): 升级已安装 Skill 到 {commit[:12]}"
    )
    assert source_head(target) != before
    names = names_at_head(target)
    assert ".codex/skills/mdf/SKILL.md" in names
    assert "README.md" not in names
    assert (target / "README.md").read_text(encoding="utf-8") == "dirty-keep\n"


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
        str(upstream), "--expected-commit", source_head(upstream),
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
            str(upstream), "--expected-commit", source_head(upstream),
        )
    )

    assert data["agents"] == {"path": "AGENTS.md", "action": "update"}
    assert data["commit"]["action"] == "created"
    assert "AGENTS.md" in names_at_head(target)
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
            str(upstream), "--expected-commit", source_head(upstream),
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
            str(upstream), "--expected-commit", source_head(upstream),
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
            str(upstream), "--expected-commit", source_head(upstream),
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
        str(upstream), "--expected-commit", source_head(upstream),
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
        str(upstream), "--expected-commit", source_head(upstream),
    )
    assert result.returncode != 0
    error = json.loads(result.stderr)
    assert error["error"] == "upgrade_missing_agents_template"
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == original
    assert (target / ".codex/skills/mdf/SKILL.md").read_text(
        encoding="utf-8"
    ) == "old-codex\n"


def set_versions(repo: Path, commit: str) -> None:
    for folder in (".codex/skills/mdf", ".cursor/skills/mdf"):
        path = repo / folder / "references" / ".version"
        path.write_text(f"{commit}\n", encoding="utf-8")


def preview(python_exe: str, target: Path, source: Path):
    return payload(mdf(
        python_exe, "upgrade", "--repo", str(target),
        "--source", str(source), "--dry-run",
    ))


def test_upgrade_dry_run_lists_skill_history(
    python_exe: str, tmp_path: Path
) -> None:
    upstream = init_upstream(tmp_path, "v1")
    baseline = source_head(upstream)
    (upstream / "UNRELATED.md").write_text("nope\n", encoding="utf-8")
    git(upstream, "add", "--all")
    git(upstream, "commit", "-m", "docs: 不进入已安装 Skill")
    note = upstream / "skills" / "mdf" / "references" / "note.md"
    note.write_text("updated-note\n", encoding="utf-8")
    git(upstream, "add", "--all")
    git(upstream, "commit", "-m", "fix: 更新 skill 说明")
    head = source_head(upstream)
    target = init_target(tmp_path)
    set_versions(target, baseline)
    data = preview(python_exe, target, upstream)
    group = data["history"][0]
    assert data["new_commit"] == head
    assert group["status"] == "ok"
    assert group["from"] == baseline
    assert group["to"] == head
    assert set(group["targets"]) == {
        ".codex/skills/mdf",
        ".cursor/skills/mdf",
    }
    assert [item["subject"] for item in group["commits"]] == [
        "fix: 更新 skill 说明"
    ]
    assert group["commits"][0]["commit"] == head
    assert group["files"] == [{"status": "M", "path": "references/note.md"}]
    assert (target / ".codex/skills/mdf/SKILL.md").read_text(
        encoding="utf-8"
    ) == "old-codex\n"


def test_upgrade_history_same_when_already_current(
    python_exe: str, tmp_path: Path
) -> None:
    upstream = init_upstream(tmp_path, "current")
    commit = source_head(upstream)
    target = init_target(tmp_path)
    set_versions(target, commit)
    assert preview(python_exe, target, upstream)["history"] == [
        {
            "from": commit,
            "to": commit,
            "status": "same",
            "commits": [],
            "files": [],
            "targets": [".codex/skills/mdf", ".cursor/skills/mdf"],
        }
    ]


def test_upgrade_history_without_version_file(
    python_exe: str, tmp_path: Path
) -> None:
    upstream = init_upstream(tmp_path, "new-skill")
    target = init_target(tmp_path)
    for folder in (".codex/skills/mdf", ".cursor/skills/mdf"):
        (target / folder / "references" / ".version").unlink()
    group = preview(python_exe, target, upstream)["history"][0]
    assert group["from"] is None
    assert group["status"] == "no_current_version"
    assert group["commits"] == []
    assert group["files"] == []
