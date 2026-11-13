"""github-flow 测试共用：写入 workflow 配置的 fixture 仓库。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from support_delivery import attach_origin, commit


def set_workflow(repo: Path, model: str = "github-flow", trunk: str = "master") -> None:
    manifest = repo / ".mdf" / "manifest.yaml"
    text = manifest.read_text(encoding="utf-8")
    block = f"workflow:\n  model: {model}\n  trunk: {trunk}\n"
    manifest.write_text(text.replace("implementation_roots:", block + "implementation_roots:", 1), encoding="utf-8")


def github_flow_repo(tmp_path: Path, *, trunk: str = "master", origin: bool = False, pr: bool = False):
    """trunk 上无 develop 分支的 github-flow 仓库；origin=True 时附带裸远端。"""
    repo = copy_fixture(tmp_path)
    set_workflow(repo, trunk=trunk)
    if pr:
        manifest = repo / ".mdf" / "manifest.yaml"
        manifest.write_text(manifest.read_text() + "closeout:\n  mode: pr\n  provider: github\n", encoding="utf-8")
    init_git(repo)
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
