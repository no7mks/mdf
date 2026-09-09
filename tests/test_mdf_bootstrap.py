"""新项目共用初始化 CLI 的可执行验收，不模拟 Agent 的语义判定。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mdf_test_support import (
    all_not_applicable_baselines,
    git,
    mdf,
    payload,
    replace,
)


@pytest.mark.parametrize("with_template", [False, True])
def test_new_project_can_reach_ready_without_fact_pages_or_remote(
    python_exe: str, tmp_path: Path, with_template: bool
):
    repo = tmp_path / "project"
    repo.mkdir()
    root = "app" if with_template else "src"
    if with_template:
        (repo / root).mkdir()
        (repo / root / "main.py").write_text('print("Hello, world!")\n')
    git(repo, "init", "--initial-branch=master")
    git(repo, "config", "user.name", "MDF Test")
    git(repo, "config", "user.email", "mdf@example.invalid")
    if with_template:
        git(repo, "add", "--", root)
        git(repo, "commit", "-m", "chore: 保存原始工程模板")
    data = payload(mdf(
        python_exe, "init", "--repo", str(repo), "--latest-release", "none",
        *all_not_applicable_baselines(), "--implementation-root", root,
        "--verification-item",
        '{"id":"check","kind":"custom","command":"git diff --check"}',
    ))
    assert data["plan"]["state"] == "initializing"
    assert not list((repo / "docs" / "product").rglob("*.md"))
    assert not list((repo / "docs" / "system").rglob("*.md"))
    if with_template:
        assert (repo / root / "main.py").read_text() == 'print("Hello, world!")\n'
        assert not (repo / "src").exists()
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "docs: 建立 MDF 起点")
    initializing = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert initializing.returncode == 2
    findings = json.loads(initializing.stdout)["findings"]
    assert [item["code"] for item in findings] == ["manifest.initializing"]
    # 模拟调用方取得启用确认后的状态写入，不调用 fact-audit。
    replace(repo / ".mdf" / "manifest.yaml", "state: initializing", "state: ready")
    payload(mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full"))
    git(repo, "add", "--", ".mdf/manifest.yaml")
    git(repo, "commit", "-m", "chore: 启用 MDF 工作流")
    git(repo, "branch", "develop", "master")
    payload(mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full"))
    assert git(repo, "rev-parse", "develop").stdout == git(repo, "rev-parse", "master").stdout
    assert git(repo, "remote").stdout == ""
    assert git(repo, "status", "--porcelain").stdout == ""
