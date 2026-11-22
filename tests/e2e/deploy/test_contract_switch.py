"""contract-switch 只改一行，且不跑其他门禁。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import skill_dir
from mdf_core.foundation.errors import MDFError
from mdf_core.inspection.validate_manifest import validate_manifest
from mdf_core.workspace.contract_switch import valid_contract_source
from mdf_test_support import git, init_git, mdf, payload


def repository(tmp_path: Path, schema: int, *, pr: bool = False) -> Path:
    repo = tmp_path / "repo"
    (repo / ".mdf").mkdir(parents=True)
    text = f"schema_version: {schema}\n"
    if pr:
        text += "closeout:\n  mode: pr\n  provider: github\n"
    (repo / ".mdf" / "manifest.yaml").write_text(text, encoding="utf-8")
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    (repo / ".gitignore").write_text(
        "# MDF local artifacts\n/.mdf/logs/\n/.mdf/tmp/\n/.mdf/reports/\n/.mdf/cache/\n/.agents/skills/mdf/\n",
        encoding="utf-8",
    )
    init_git(repo)
    git(repo, "branch", "-M", "master")
    return repo


def test_switch_commits_only_the_schema_line(python_exe: str, tmp_path: Path) -> None:
    repo = repository(tmp_path, 2)
    before = (repo / "README.md").read_text(encoding="utf-8")
    data = payload(mdf(python_exe, "contract-switch", "--repo", str(repo)))
    assert data["changed"] is True
    assert data["schema_version"] == 3
    assert "schema_version: 3\n" in (repo / ".mdf" / "manifest.yaml").read_text(encoding="utf-8")
    assert (repo / "README.md").read_text(encoding="utf-8") == before
    assert git(repo, "log", "-1", "--format=%s").stdout.strip() == "chore(mdf): 切换 MDF 契约到 3"
    again = payload(mdf(python_exe, "contract-switch", "--repo", str(repo)))
    assert again["changed"] is False


def test_newer_declaration_asks_for_upgrade(python_exe: str, tmp_path: Path) -> None:
    repo = repository(tmp_path, 4)
    result = mdf(python_exe, "contract-switch", "--repo", str(repo))
    assert result.returncode != 0
    assert "contract_tool_outdated" in result.stderr
    assert "更新命令：$mdf upgrade" in result.stderr
    assert "schema_version: 4\n" in (repo / ".mdf" / "manifest.yaml").read_text(encoding="utf-8")


def test_pr_mode_branch_is_a_one_line_whitelist(python_exe: str, tmp_path: Path) -> None:
    repo = repository(tmp_path, 2, pr=True)
    data = payload(mdf(python_exe, "contract-switch", "--repo", str(repo)))
    assert data["source"] == "codex/contract-switch"
    base = git(repo, "rev-parse", "master").stdout.strip()
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    from mdf_core.workspace.contract_switch import valid_contract_source
    assert valid_contract_source(repo, base, head, "master")
    assert not valid_contract_source(repo, base, head, "develop")


def test_whitelist_rejects_other_edits(python_exe: str, tmp_path: Path) -> None:
    repo = repository(tmp_path, 2, pr=True)
    payload(mdf(python_exe, "contract-switch", "--repo", str(repo)))
    base = git(repo, "rev-parse", "master").stdout.strip()
    good = git(repo, "rev-parse", "HEAD").stdout.strip()
    assert valid_contract_source(repo, base, good, "master")

    def amended(path: str) -> str:
        git(repo, "add", "--", path)
        git(repo, "commit", "--amend", "--no-edit")
        return git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "README.md").write_text("extra\n", encoding="utf-8")
    assert not valid_contract_source(repo, base, amended("README.md"), "master")
    git(repo, "reset", "--hard", good)
    manifest = repo / ".mdf" / "manifest.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "logo: x\n", encoding="utf-8")
    assert not valid_contract_source(repo, base, amended(".mdf/manifest.yaml"), "master")
    git(repo, "reset", "--hard", good)
    git(repo, "update-index", "--chmod=+x", ".mdf/manifest.yaml")
    git(repo, "commit", "--amend", "--no-edit")
    assert not valid_contract_source(repo, base, git(repo, "rev-parse", "HEAD").stdout.strip(), "master")
    git(repo, "reset", "--hard", good)
    git(repo, "commit", "--allow-empty", "-m", "test: 第二笔提交")
    assert not valid_contract_source(repo, base, git(repo, "rev-parse", "HEAD").stdout.strip(), "master")


def test_review_uses_the_real_whitelist(python_exe: str, tmp_path: Path) -> None:
    repo = repository(tmp_path, 2, pr=True)
    payload(mdf(python_exe, "contract-switch", "--repo", str(repo)))
    path = skill_dir("mdf") / "assets" / "ci" / "review.py"
    spec = importlib.util.spec_from_file_location("ci_review_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "review-out"
    args = SimpleNamespace(
        repo=str(repo), source="codex/contract-switch", head="HEAD", policy_ref="master",
        target="master", backend="codex", output_dir=str(output),
    )
    assert module.run(args) == 0
    assert (output / "contract-switch.json").is_file()
    (repo / "README.md").write_text("extra\n", encoding="utf-8")
    git(repo, "add", "--", "README.md")
    git(repo, "commit", "-m", "test: 多余文件")
    with pytest.raises(MDFError) as caught:
        module.run(SimpleNamespace(**{**args.__dict__, "output_dir": str(tmp_path / "review-bad")}))
    assert caught.value.code == "invalid_contract_switch"


def test_ordinary_command_hints_when_the_declaration_is_newer(python_exe: str, tmp_path: Path) -> None:
    repo = repository(tmp_path, 4)
    nested = repo / "src"
    nested.mkdir()
    result = mdf(python_exe, "doctor", "--repo", str(nested))
    assert "MDF 提示：" in result.stderr
    assert ".mdf/manifest.yaml 声明的 4" in result.stderr
    assert "更新命令：$mdf upgrade" in result.stderr
    findings = []
    validate_manifest(repo, findings)
    assert any(item.code == "manifest.tool_outdated" for item in findings)
    assert not any(item.code == "manifest.schema" for item in findings)


def test_drift_hint_reads_origin_trunk_even_when_worktree_matches(python_exe: str, tmp_path: Path) -> None:
    repo = repository(tmp_path, 3)
    manifest = repo / ".mdf" / "manifest.yaml"
    manifest.write_text(
        "schema_version: 3\nworkflow:\n  model: github-flow\n  trunk: main\n",
        encoding="utf-8",
    )
    git(repo, "add", "--", ".mdf/manifest.yaml")
    git(repo, "commit", "-m", "test: 声明 trunk")
    git(repo, "branch", "-M", "main")
    manifest.write_text(
        "schema_version: 4\nworkflow:\n  model: github-flow\n  trunk: main\n",
        encoding="utf-8",
    )
    git(repo, "add", "--", ".mdf/manifest.yaml")
    git(repo, "commit", "-m", "test: 远端更高契约")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "reset", "--hard", "HEAD~1")
    result = mdf(python_exe, "doctor", "--repo", str(repo))
    assert "origin/main 声明的 4" in result.stderr
    assert "更新命令：$mdf upgrade" in result.stderr
