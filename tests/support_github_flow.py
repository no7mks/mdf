"""github-flow 测试共用：写入 workflow 配置的 fixture 仓库。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from support_delivery import attach_origin, commit


def set_workflow(repo: Path, model: str = "github-flow", trunk: str = "master") -> None:
    manifest = repo / ".mdf" / "manifest.yaml"
    text = manifest.read_text(encoding="utf-8")
    block = f"workflow:\n  model: {model}\n  trunk: {trunk}\n"
    manifest.write_text(text.replace("implementation_roots:", block + "implementation_roots:", 1), encoding="utf-8")


def github_flow_repo(tmp_path: Path, *, trunk: str = "master", origin: bool = False, pr: bool = False, previous_release: bool = False):
    """trunk 上无 develop 分支的 github-flow 仓库；origin=True 时附带裸远端。"""
    repo = copy_fixture(tmp_path)
    set_workflow(repo, trunk=trunk)
    if pr:
        manifest = repo / ".mdf" / "manifest.yaml"
        manifest.write_text(manifest.read_text() + "closeout:\n  mode: pr\n  provider: github\n", encoding="utf-8")
    init_git(repo, previous_release=previous_release)
    git(repo, "branch", "-m", trunk)
    remote = None
    if origin:
        remote = tmp_path / "origin.git"
        remote.mkdir()
        git(remote, "init", "--bare")
        git(remote, "symbolic-ref", "HEAD", f"refs/heads/{trunk}")
        git(repo, "remote", "add", "origin", str(remote))
        git(repo, "push", "--all", "--set-upstream", "origin")
        git(repo, "remote", "set-head", "origin", "--auto")
    return (repo, remote) if origin else repo


def error_of(result) -> dict:
    assert result.returncode != 0, result.stdout
    return json.loads(result.stderr.strip().splitlines()[-1])


def has_ref(repo: Path, ref: str) -> bool:
    from _support import run as _run
    return _run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=repo).returncode == 0


def prepare_release_materials(python_exe, work):
    """准备已收敛的发布材料。"""
    from mdf_test_support import mdf, payload
    from support_pull import squash_pending
    from mdf_core.lifecycle.delivery_state import locate
    root, data = locate(work)
    hotfix = data["branch"].startswith("hotfix/")
    path = root / "objectives.md"
    text = path.read_text()
    boundary = "- [ ] catch-up" if hotfix else "- [ ] publish"
    if boundary not in text:
        return
    if hotfix:
        seed_verify_branch(python_exe, work)
    before, after = text.split(boundary, 1)
    path.write_text(before.replace("- [ ]", "- [x]") + boundary + after)
    commit(work, "test: 完成发布基线")
    squash_pending(work)
    sync = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    payload(mdf(python_exe, "catch-up", "--repo", str(work), "--complete",
                "--reviewed-head", sync["head"], "--summary", "已完成测试夹具增量验收"))
    from support_delivery import seed_consolidation
    if hotfix:
        change = {"fixed": [], "release_notes": {"Fixed": ["修复维护线交付回归场景"]},
                  "body": "维护线变更已通过回归验证。", "evidence": {"tests": [], "commands": ["python -m pytest"], "artifacts": []}}
        payload(mdf(python_exe, "consolidate", "--repo", str(work), "--release-date", "2026-11-21",
                    "--hotfix-change-json", json.dumps(change)))
    else:
        seed_consolidation(work, mark=True)


def publish_release(python_exe, work):
    from mdf_test_support import mdf, payload
    prepare_release_materials(python_exe, work)
    return payload(mdf(python_exe, "publish", "--repo", str(work)))["release_head"]
