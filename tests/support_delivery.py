"""交付类 E2E 共用的仓库、交付与角色 worktree 准备。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from _support import run


def attach_origin(repo: Path, tmp_path: Path) -> Path:
    remote = tmp_path / "origin.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    git(remote, "symbolic-ref", "HEAD", "refs/heads/master")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "--all", "--set-upstream", "origin")
    git(repo, "remote", "set-head", "origin", "--auto")
    return remote


def start_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "-m", "master")
    git(repo, "branch", "develop")
    return repo, attach_origin(repo, tmp_path)


def local_repo(tmp_path: Path) -> Path:
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "-m", "master")
    git(repo, "branch", "develop")
    return repo


def commit(repo, message="test: 提交当前阶段"):
    git(repo, "add", "--all")
    git(repo, "commit", "-m", message)


def write_changelog_release(
    repo: Path, version: str, *, date: str = "2026-07-30"
) -> None:
    load_core_module()
    from mdf_core.lifecycle.closeout_render import update_changelog_text
    from mdf_core.foundation.constants import CHANGELOG_CATEGORIES

    notes = {name: [] for name in CHANGELOG_CATEGORIES}
    notes["Fixed"] = ["测试发布条目"]
    path = repo / "CHANGELOG.md"
    path.write_text(
        update_changelog_text(
            path.read_text(encoding="utf-8"),
            version=version,
            release_date=date,
            notes=notes,
        ),
        encoding="utf-8",
    )


def git_primary(repo):
    raw = git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    path = Path(raw)
    if not path.is_absolute():
        path = (repo / path).resolve()
    else:
        path = path.resolve()
    return path.parent


def role_paths(python_exe, owner):
    trees = payload(mdf(python_exe, "delivery", "status", "--repo", str(owner))
                    )["result"]["worktrees"]
    return Path(trees["qa"][0]["path"]), Path(trees["dev"][0]["path"])


def sync_roles(python_exe, owner):
    qa, dev = role_paths(python_exe, owner)
    branch = git(owner, "branch", "--show-current").stdout.strip()
    message = f"chore(delivery): 合入 {branch}"
    for path in (qa, dev):
        git(path, "merge", "--no-ff", "--no-edit", "-m", message, branch)
    return qa, dev


def setup_delivery(python_exe, tmp_path):
    repo, remote = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text(
        "# 目标\n\n- needs_design: yes\n\n实现健康状态接口。\n"
    )
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                       "--proposal", "prp-0001", "--objectives-file", str(obj)))
    work = Path(data["worktree"])
    primary = git_primary(work)
    assert work == (
        primary.parent / f"{primary.name}-worktrees" / "feature" / "service-health"
    )
    qa = Path(data["roles"]["qa"][0]["worktree"])
    assert qa == (
        primary.parent / f"{primary.name}-worktrees" / "qa" / "feature"
        / "service-health"
    )
    root = work / "changes/unreleased/service-health"
    assert json.loads((root / "delivery.json").read_text())["start_commit"] == data["start_commit"]
    objectives = root / "objectives.md"
    objectives.write_text(objectives.read_text() + "\n[design.md](./design.md)\n")
    (root / "design.md").write_text(
        "# 设计\n\n[实现](../../../src/service.py)\n\n"
        "[objectives.md](./objectives.md)\n"
        "[see design.md](./design.md)\n"
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"protected_paths": ["tests/", "pytest.ini"], "suites": ["billing"]}))
    payload(mdf(python_exe, "delivery", "record", "--repo", str(work), "--stage", "design",
                "--policy-file", str(policy), "--summary", "用户确认接口及验收；测试配置已识别"))
    commit(work)
    return work, root, remote


def record(python_exe, repo, stage, *extra):
    return mdf(python_exe, "delivery", "record", "--repo", str(repo), "--stage", stage,
               "--summary", "按目标逐项核对，相关结果已复核", *extra)


def converge_ready(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    payload(mdf(python_exe, "delivery", "roster-join", "--repo", str(repo)))
    return repo, root


def write_change(work, source, slug):
    root = work / "changes/unreleased" / slug
    root.mkdir(parents=True, exist_ok=True)
    (root / "CHANGE.md").write_text(
        f"---\nchange_kind: fix\nsource_branch: {source}\nproposals: []\n"
        "fixed: []\nclosed: []\ndeferred: []\nadrs: []\nrelease_notes: none\nbreaking: false\n"
        'evidence:\n  tests: []\n  commands: ["true"]\n  artifacts: []\n---\n'
        "\n# Change\n\n## 结果\n\n完成本次修正。\n\n## 已更新的当前文档\n\n无。\n\n## 已知偏差\n\n无。\n"
    )
    return root
