"""在隔离 Git 远端中验证启动失败现场与版本收口后的交付。"""

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


def test_start_does_not_require_origin(
    python_exe: str, tmp_path: Path,
):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n交付健康接口。\n")
    result = payload(mdf(python_exe, "start", "--repo", str(repo),
                         "--kind", "feature", "--proposal", "prp-001",
                         "--objectives-file", str(obj)))
    work = Path(result["worktree"])
    assert result["pushed"] is False
    assert "upstream" not in result
    assert result["branch"] == "feature/service-health"
    assert result["roster"] == {"qa": 1, "dev": 1, "reviewers": 3}
    assert result["roles"]["qa"][0]["branch"] == "qa/feature/service-health"
    assert result["roles"]["dev"][0]["branch"] == "dev/feature/service-health"
    assert Path(result["roles"]["qa"][0]["worktree"]).is_dir()
    assert Path(result["roles"]["dev"][0]["worktree"]).is_dir()
    tracking = run(["git", "rev-parse", "--abbrev-ref", "@{upstream}"], cwd=work)
    assert tracking.returncode != 0
    assert git(repo, "branch", "--show-current").stdout.strip() == "master"


@pytest.mark.parametrize("kind", ["feature", "bugfix", "release", "hotfix"])
def test_start_uses_local_base_without_upstream(
    python_exe: str, tmp_path: Path, kind: str,
):
    repo, _remote = start_repo(tmp_path)
    git(repo, "checkout", "develop")
    (repo / "development.txt").write_text("开发线\n", encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 区分开发线与发布线")
    git(repo, "push")
    base = "master" if kind == "hotfix" else "develop"
    expected = git(repo, "rev-parse", base).stdout.strip()
    if kind == "feature":
        obj = tmp_path / "objectives.md"
        obj.write_text("# 目标\n\n交付健康接口。\n")
        identifier = [
            "--proposal", "prp-001", "--objectives-file", str(obj),
        ]
    elif kind == "bugfix":
        identifier = ["--bug", "bug-CD34"]
    else:
        identifier = ["--version", "1.3.0"]
    result = payload(mdf(python_exe, "start", "--repo", str(repo),
                         "--kind", kind, *identifier))

    work = Path(result["worktree"])
    assert result["base"] == base
    assert result["start_commit"] == expected
    key = f"branch.{result['branch']}.mdf-start-commit"
    assert git(work, "config", "--local", "--get", key).stdout.strip() == expected
    assert result["pushed"] is False
    assert work == repo.parent / f"{repo.name}-worktrees" / Path(result["branch"])
    assert work != repo
    assert git(work, "branch", "--show-current").stdout.strip() == result["branch"]
    assert git(repo, "branch", "--show-current").stdout.strip() != result["branch"]
    if kind == "feature":
        expected = git(work, "rev-parse", "HEAD").stdout.strip()
        qa = Path(result["roles"]["qa"][0]["worktree"])
        assert qa == repo.parent / f"{repo.name}-worktrees" / "qa" / Path(result["branch"])
        assert git(qa, "rev-parse", "HEAD").stdout.strip() == result["start_commit"]
    assert git(work, "rev-parse", "HEAD").stdout.strip() == expected
    tracking = run(["git", "rev-parse", "--abbrev-ref", "@{upstream}"], cwd=work)
    assert tracking.returncode != 0


@pytest.mark.parametrize("kind", ["release", "hotfix"])
def test_preview_then_committed_closeout_can_finish_without_reapplying(
    python_exe: str, tmp_path: Path, kind: str,
):
    if kind == "release":
        repo = prepare_release_closeout_repo(tmp_path)
        version = "1.3.0"
        git(repo, "branch", "master", "main^")
        git(repo, "branch", "develop", "main")
        extra = []
    else:
        repo = copy_fixture(tmp_path)
        replace(repo / "docs/bugs" / BUG_NAME, "status: open", "status: fixed")
        init_git(repo)
        git(repo, "branch", "master")
        git(repo, "branch", "develop")
        version = "1.2.1"
        git(repo, "checkout", "-b", f"hotfix/{version}")
        extra = ["--hotfix-change-json", json.dumps({
            "body": "修复服务超时。",
            "fixed": [BUG_ID],
            "release_notes": {"Fixed": ["修复服务超时"]},
            "evidence": {"tests": [], "commands": ["true"], "artifacts": []},
        })]
    remote = attach_origin(repo, tmp_path)
    before_local = git(repo, "show-ref").stdout
    before_remote = git(remote, "show-ref").stdout
    args = ["release-closeout", "--repo", str(repo),
            "--release-date", "2026-09-08", *extra]

    preview = payload(mdf(python_exe, *args, "--dry-run"))
    assert preview["dry_run"] is True
    assert git(repo, "show-ref").stdout == before_local
    assert git(remote, "show-ref").stdout == before_remote
    assert not git(repo, "status", "--porcelain").stdout
    assert not (repo / "changes" / version).exists()

    payload(mdf(python_exe, *args))
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "chore: 复核并提交版本收口")
    git(repo, "push", "origin", "master", "develop")
    root_change = repo / "changes" / version / "CHANGE.md"
    root_before = root_change.read_bytes()
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full"))
    assert_ok(mdf(python_exe, "fact-audit", "--repo", str(repo)))

    finished = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo)))

    assert finished["tag"] == f"v{version}"
    assert finished["pushed"] is True
    assert root_change.read_bytes() == root_before
    git(repo, "merge-base", "--is-ancestor", "master", "develop")
    assert git(remote, "rev-parse", f"v{version}^{{}}").stdout == git(
        repo, "rev-parse", "master",
    ).stdout
    assert not git(repo, "for-each-ref", f"refs/heads/{kind}/{version}").stdout
    assert not git(repo, "status", "--porcelain").stdout


def _add_ready_prp(repo: Path, identifier: str, slug: str) -> None:
    template = (repo / "docs/proposals" / PRP_NAME).read_text()
    text = template.replace("prp-001", identifier)
    (repo / "docs/proposals" / f"{identifier}-{slug}.md").write_text(text)


def test_start_from_delivery_branch_creates_worktree_and_finish_removes_it(
    python_exe: str, tmp_path: Path,
):
    repo, _remote = start_repo(tmp_path)
    git(repo, "checkout", "develop")
    _add_ready_prp(repo, "prp-003", "parallel")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "docs(prp): 增加可并行提案")
    first = tmp_path / "first.md"
    first.write_text("# 目标\n\n交付健康接口。\n")
    first_start = payload(mdf(python_exe, "start", "--repo", str(repo),
                 "--kind", "feature", "--proposal", "prp-001",
                 "--objectives-file", str(first)))
    health = Path(first_start["worktree"])
    assert health != repo
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(health, "branch", "--show-current").stdout.strip() == (
        "feature/service-health"
    )

    second = tmp_path / "second.md"
    second.write_text("# 目标\n\n交付并行接口。\n")
    created = payload(mdf(python_exe, "start", "--repo", str(repo),
                           "--kind", "feature", "--proposal", "prp-003",
                           "--objectives-file", str(second)))
    work = Path(created["worktree"])
    assert created["branch"] == "feature/parallel"
    assert work != repo and work != health
    assert work.is_dir()
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(work, "branch", "--show-current").stdout.strip() == "feature/parallel"

    extra = payload(mdf(python_exe, "start", "--repo", str(repo),
                          "--kind", "bugfix", "--bug", "bug-CD34"))
    bugfix = Path(extra["worktree"])
    assert extra["branch"] == "bugfix/bug-CD34"
    assert extra["pushed"] is False
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    (bugfix / "fix.txt").write_text("ok\n")
    git(bugfix, "add", "--all")
    git(bugfix, "commit", "-m", "fix: 补充热修复文件")
    finished = payload(mdf(python_exe, "finish-gitflow", "--repo", str(bugfix)))
    assert finished["pushed"] is False
    assert not bugfix.exists()
    assert run(["git", "config", "--local", "--get",
                "branch.bugfix/bug-CD34.mdf-start-commit"], cwd=repo).returncode == 1
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(repo, "show", "develop:fix.txt").stdout == "ok\n"


def test_start_feature_rejects_name_and_derives_slug_from_prp(
    python_exe: str, tmp_path: Path,
):
    repo, _remote = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n交付健康接口。\n")
    rejected = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--name", "delivery", "--proposal", "prp-001",
        "--objectives-file", str(obj),
    )
    assert "unexpected_name" in rejected.stderr
    created = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj),
    ))
    assert created["branch"] == "feature/service-health"
    assert created["roles"]["qa"][0]["branch"] == "qa/feature/service-health"


def test_start_rewrites_repo_root_style_objectives_links(
    python_exe: str, tmp_path: Path,
):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text(
        f"# 目标\n\n[需求](docs/proposals/{PRP_NAME})\n"
        "[能力](docs/product/reference/capabilities.md)\n"
        "[外链](/docs/product/reference/capabilities.md)\n"
    )
    data = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj),
    ))
    work = Path(data["worktree"])
    text = (work / "changes/unreleased/service-health/objectives.md").read_text()
    assert f"[需求](../../../docs/proposals/{PRP_NAME})" in text
    assert "[能力](../../../docs/product/reference/capabilities.md)" in text
    assert "[外链](/docs/product/reference/capabilities.md)" in text



def test_start_bugfix_uses_bug_id_and_rejects_name(
    python_exe: str, tmp_path: Path,
):
    repo, _remote = start_repo(tmp_path)
    named = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--name", "timeout-fix",
    )
    assert "unexpected_name" in named.stderr
    missing = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
    )
    assert "missing_bug" in missing.stderr
    wrong = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--bug", "prp-001",
    )
    assert "missing_bug" in wrong.stderr
    created = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--bug", "bug-CD34",
    ))
    assert created["branch"] == "bugfix/bug-CD34"
    assert created["roster"] == {"qa": 0, "dev": 0, "reviewers": 3}
    assert created["roles"] == {"qa": [], "dev": []}


@pytest.mark.parametrize("kind", ["bugfix", "hotfix"])
def test_review_start_stays_fixed_when_parent_moves(python_exe, tmp_path, kind):
    repo = local_repo(tmp_path)
    identifier = ["--bug", "bug-CD34"] if kind == "bugfix" else ["--version", "1.2.1"]
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", kind, *identifier))
    work = Path(data["worktree"])
    git(repo, "checkout", data["base"])
    (repo / "later.txt").write_text("后续交付\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 推进父分支")
    key = f"branch.{data['branch']}.mdf-start-commit"
    saved = git(work, "config", "--local", "--get", key).stdout.strip()
    assert saved == data["start_commit"]
    assert saved != git(repo, "rev-parse", data["base"]).stdout.strip()
    assert git(work, "diff", saved, "HEAD").stdout == ""
