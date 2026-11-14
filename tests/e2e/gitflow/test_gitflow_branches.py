"""在隔离 Git 远端中验证启动失败现场与版本收口后的交付。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from _support import run
from support_delivery import *  # noqa: F403


def _error(result):
    assert result.returncode != 0
    return json.loads(result.stderr.strip().splitlines()[-1])


def _advance_origin(remote: Path, branch: str, tmp_path: Path) -> None:
    other = tmp_path / f"ahead-{branch}"
    git(tmp_path, "clone", "--branch", branch, str(remote), str(other))
    (other / f"{branch}-remote.txt").write_text("远程更新\n", encoding="utf-8")
    commit(other, f"test: 远程推进 {branch}")
    git(other, "push")


def test_start_allows_local_base_ahead_of_origin(python_exe: str, tmp_path: Path):
    repo, _remote = start_repo(tmp_path)
    git(repo, "checkout", "develop")
    (repo / "local-only.txt").write_text("本地更新\n", encoding="utf-8")
    commit(repo, "test: 本地领先 develop")
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n- needs_design: yes\n\n交付健康接口。\n")
    result = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-0001", "--objectives-file", str(obj),
    ))
    assert result["base"] == "develop"
    assert result["pushed"] is False


@pytest.mark.parametrize("kind,base", [("feature", "develop"), ("hotfix", "master")])
def test_start_rejects_origin_commits_missing_locally(
    python_exe: str, tmp_path: Path, kind: str, base: str,
):
    repo, remote = start_repo(tmp_path)
    _advance_origin(remote, base, tmp_path)
    if kind == "feature":
        obj = tmp_path / "objectives.md"
        obj.write_text("# 目标\n\n- needs_design: yes\n\n交付健康接口。\n")
        identifier = ["--proposal", "prp-0001", "--objectives-file", str(obj)]
        branch = "feature/service-health"
    else:
        identifier = [
            "--version", "1.3.0",
            "--objectives-file", str(write_work_objectives(tmp_path)),
        ]
        branch = "hotfix/1.3.0"
    failed = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", kind, *identifier,
    )
    assert _error(failed)["error"] == "remote_ahead"
    assert run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo,
    ).returncode != 0


def test_start_rejects_diverged_base(python_exe: str, tmp_path: Path):
    repo, remote = start_repo(tmp_path)
    git(repo, "checkout", "develop")
    (repo / "local-diverge.txt").write_text("本地分叉\n", encoding="utf-8")
    commit(repo, "test: 本地分叉 develop")
    _advance_origin(remote, "develop", tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n- needs_design: yes\n\n交付健康接口。\n")
    failed = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-0001", "--objectives-file", str(obj),
    )
    assert _error(failed)["error"] == "remote_ahead"


def test_start_does_not_require_origin(
    python_exe: str, tmp_path: Path,
):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n- needs_design: yes\n\n交付健康接口。\n")
    result = payload(mdf(python_exe, "start", "--repo", str(repo),
                         "--kind", "feature", "--proposal", "prp-0001",
                         "--objectives-file", str(obj)))
    work = Path(result["worktree"])
    assert result["pushed"] is False
    assert "upstream" not in result
    assert result["branch"] == "feature/service-health"
    assert result["roster"] == {
        "qa": 1, "dev": 1, "reviewers": 2,
        "qa_strategy": "best-of-n", "dev_strategy": "best-of-n",
        "review_strategy": "replicate",
    }
    assert result["roles"]["qa"][0]["branch"] == "qa/feature/service-health"
    assert result["roles"]["dev"][0]["branch"] == "dev/feature/service-health"
    assert Path(result["roles"]["qa"][0]["worktree"]).is_dir()
    assert Path(result["roles"]["dev"][0]["worktree"]).is_dir()
    tracking = run(["git", "rev-parse", "--abbrev-ref", "@{upstream}"], cwd=work)
    assert tracking.returncode != 0
    assert git(repo, "branch", "--show-current").stdout.strip() == "master"


def test_start_preserves_dirty_source_and_uses_committed_base(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    git(repo, "switch", "develop")
    git(repo, "commit", "--allow-empty", "-m", "test: 推进交付基线")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    manifest = repo / ".mdf/manifest.yaml"
    committed = manifest.read_text()
    manifest.write_text(committed + "\nworkflow:\n  model: github-flow\n  trunk: other\n")
    git(repo, "add", "--", ".mdf/manifest.yaml")
    manifest.write_text(manifest.read_text() + "# 未暂存配置\n")
    (repo / "scratch.txt").write_text("临时改动\n")
    status = git(repo, "status", "--porcelain").stdout
    staged = git(repo, "diff", "--cached").stdout
    unstaged = git(repo, "diff").stdout
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n- needs_design: yes\n")

    result = mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                 "--proposal", "prp-0001", "--objectives-file", str(obj))
    data = payload(result)
    work = Path(data["worktree"])

    assert "警告" in result.stderr
    assert data["base"] == "develop" and data["start_commit"] == base
    assert git(work, "rev-parse", "HEAD^").stdout.strip() == base
    assert (work / ".mdf/manifest.yaml").read_text() == committed
    assert not (work / "scratch.txt").exists()
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == base
    assert git(repo, "status", "--porcelain").stdout == status
    assert git(repo, "diff", "--cached").stdout == staged
    assert git(repo, "diff").stdout == unstaged
    assert (repo / "scratch.txt").read_text() == "临时改动\n"


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
        obj.write_text("# 目标\n\n- needs_design: yes\n\n交付健康接口。\n")
        identifier = [
            "--proposal", "prp-0001", "--objectives-file", str(obj),
        ]
    elif kind == "bugfix":
        identifier = [
            "--bug", "bug-CD34",
            "--objectives-file", str(write_work_objectives(tmp_path)),
        ]
    elif kind == "release":
        identifier = [
            "--version", "1.3.0",
            "--objectives-file", str(write_release_objectives(tmp_path)),
        ]
    else:
        identifier = [
            "--version", "1.3.0",
            "--objectives-file", str(write_work_objectives(tmp_path)),
        ]
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
    elif kind in {"release", "bugfix", "hotfix"}:
        expected = git(work, "rev-parse", "HEAD").stdout.strip()
        assert expected != result["start_commit"]
        folder = {
            "release": "1.3.0",
            "hotfix": "1.3.0",
            "bugfix": "bug-cd34",
        }[kind]
        root = work / "changes/unreleased" / folder
        assert (root / "objectives.md").is_file()
        assert (root / "delivery.json").is_file()
        identity = json.loads((root / "delivery.json").read_text())
        assert identity["branch"] == result["branch"]
        assert identity["start_commit"] == result["start_commit"]
        if kind == "release":
            doctor = payload(mdf(python_exe, "doctor", "--repo", str(work)))
            assert doctor["findings"] == []
    assert git(work, "rev-parse", "HEAD").stdout.strip() == expected
    tracking = run(["git", "rev-parse", "--abbrev-ref", "@{upstream}"], cwd=work)
    assert tracking.returncode != 0


@pytest.mark.parametrize("kind", ["release", "hotfix"])
def test_preview_then_committed_closeout_can_finish_without_reapplying(
    python_exe: str, tmp_path: Path, kind: str,
):
    if kind == "release":
        repo = prepare_release_closeout_repo(tmp_path, python_exe=python_exe)
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
        payload(mdf(
            python_exe, "bug", "close", BUG_ID, "--fixed-in", version, "--repo", str(repo),
        ))
        git(repo, "add", "--all")
        git(repo, "commit", "-m", "test: 验收并关闭热修复 Bug")
        seed_verify_branch(python_exe, repo)
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
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--level", "strict"))
    assert_ok(mdf(python_exe, "fact-audit", "--repo", str(repo)))

    finished = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo)))

    assert finished["tag"] == f"v{version}"
    assert finished["pushed"] is True
    assert git(repo, "cat-file", "-t", f"v{version}").stdout.strip() == "tag"
    contents = git(
        repo, "tag", "-l", "--format=%(contents)", f"v{version}"
    ).stdout
    assert contents.startswith(f"chore(release): 发布 v{version}")
    assert f"## [{version}]" in contents
    assert root_change.read_bytes() == root_before
    git(repo, "merge-base", "--is-ancestor", "master", "develop")
    assert git(remote, "rev-parse", f"v{version}^{{}}").stdout == git(
        repo, "rev-parse", "master",
    ).stdout
    assert not git(repo, "for-each-ref", f"refs/heads/{kind}/{version}").stdout
    assert not git(repo, "status", "--porcelain").stdout


def _add_ready_prp(repo: Path, identifier: str, slug: str) -> None:
    template = (repo / "docs/proposals" / PRP_NAME).read_text()
    text = template.replace("prp-0001", identifier)
    (repo / "docs/proposals" / f"{identifier}-{slug}.md").write_text(text)


def test_start_from_delivery_branch_creates_worktree_and_finish_detaches_it(
    python_exe: str, tmp_path: Path,
):
    repo, _remote = start_repo(tmp_path)
    git(repo, "checkout", "develop")
    _add_ready_prp(repo, "prp-0003", "parallel")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "docs(prp): 增加可并行提案")
    first = tmp_path / "first.md"
    first.write_text("# 目标\n\n- needs_design: yes\n\n交付健康接口。\n")
    first_start = payload(mdf(python_exe, "start", "--repo", str(repo),
                 "--kind", "feature", "--proposal", "prp-0001",
                 "--objectives-file", str(first)))
    health = Path(first_start["worktree"])
    assert health != repo
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(health, "branch", "--show-current").stdout.strip() == (
        "feature/service-health"
    )

    second = tmp_path / "second.md"
    second.write_text("# 目标\n\n- needs_design: yes\n\n交付并行接口。\n")
    created = payload(mdf(python_exe, "start", "--repo", str(repo),
                           "--kind", "feature", "--proposal", "prp-0003",
                           "--objectives-file", str(second)))
    work = Path(created["worktree"])
    assert created["branch"] == "feature/parallel"
    assert work != repo and work != health
    assert work.is_dir()
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(work, "branch", "--show-current").stdout.strip() == "feature/parallel"

    extra = payload(mdf(python_exe, "start", "--repo", str(repo),
                          "--kind", "bugfix", "--bug", "bug-CD34",
                          "--objectives-file",
                          str(write_work_objectives(tmp_path))))
    bugfix = Path(extra["worktree"])
    assert extra["branch"] == "bugfix/bug-CD34"
    assert extra["pushed"] is False
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    (bugfix / "fix.txt").write_text("ok\n")
    git(bugfix, "add", "--all")
    git(bugfix, "commit", "-m", "fix: 补充热修复文件")
    source = git(bugfix, "rev-parse", "HEAD").stdout
    finished = payload(mdf(python_exe, "finish-gitflow", "--repo", str(bugfix)))
    assert finished["pushed"] is False
    assert bugfix.is_dir()
    assert finished["retained_worktree"] == str(bugfix)
    assert finished["primary_worktree"] == str(repo)
    assert not git(bugfix, "branch", "--show-current").stdout.strip()
    assert git(bugfix, "rev-parse", "HEAD").stdout == source
    assert not git(bugfix, "status", "--porcelain").stdout
    assert not git(repo, "for-each-ref", "refs/heads/bugfix/bug-CD34").stdout
    assert run(["git", "config", "--local", "--get",
                "branch.bugfix/bug-CD34.mdf-start-commit"], cwd=repo).returncode == 1
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(repo, "show", "develop:fix.txt").stdout == "ok\n"


def test_start_feature_rejects_name_and_derives_slug_from_prp(
    python_exe: str, tmp_path: Path,
):
    repo, _remote = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n- needs_design: yes\n\n交付健康接口。\n")
    rejected = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--name", "delivery", "--proposal", "prp-0001",
        "--objectives-file", str(obj),
    )
    assert "unexpected_name" in rejected.stderr
    created = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-0001", "--objectives-file", str(obj),
    ))
    assert created["branch"] == "feature/service-health"
    assert created["roles"]["qa"][0]["branch"] == "qa/feature/service-health"


def test_start_rewrites_repo_root_style_objectives_links(
    python_exe: str, tmp_path: Path,
):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text(
        f"# 目标\n\n- needs_design: yes\n\n"
        f"[需求](docs/proposals/{PRP_NAME})\n"
        "[能力](docs/user-guide/README.md)\n"
        "[外链](/docs/user-guide/README.md)\n"
    )
    data = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-0001", "--objectives-file", str(obj),
    ))
    work = Path(data["worktree"])
    text = (work / "changes/unreleased/service-health/objectives.md").read_text()
    assert f"[需求](../../../docs/proposals/{PRP_NAME})" in text
    assert "[能力](../../../docs/user-guide/README.md)" in text
    assert "[外链](/docs/user-guide/README.md)" in text


def test_start_bugfix_uses_bug_id_and_rejects_name(
    python_exe: str, tmp_path: Path,
):
    repo, _remote = start_repo(tmp_path)
    obj = write_work_objectives(tmp_path)
    named = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--name", "timeout-fix", "--objectives-file", str(obj),
    )
    assert "unexpected_name" in named.stderr
    missing = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--objectives-file", str(obj),
    )
    assert "missing_bug" in missing.stderr
    wrong = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--bug", "prp-0001", "--objectives-file", str(obj),
    )
    assert "missing_bug" in wrong.stderr
    created = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--bug", "bug-CD34", "--objectives-file", str(obj),
    ))
    assert created["branch"] == "bugfix/bug-CD34"
    assert created["roster"] == {
        "qa": 0, "dev": 0, "reviewers": 1,
        "qa_strategy": "best-of-n", "dev_strategy": "best-of-n",
        "review_strategy": "replicate",
    }
    assert created["roles"] == {"qa": [], "dev": []}
    work = Path(created["worktree"])
    assert (work / "changes/unreleased/bug-cd34/objectives.md").is_file()


@pytest.mark.parametrize("kind", ["bugfix", "hotfix"])
def test_review_start_stays_fixed_when_parent_moves(python_exe, tmp_path, kind):
    repo = local_repo(tmp_path)
    obj = write_work_objectives(tmp_path)
    identifier = (
        ["--bug", "bug-CD34", "--objectives-file", str(obj)]
        if kind == "bugfix"
        else ["--version", "1.2.1", "--objectives-file", str(obj)]
    )
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", kind, *identifier))
    work = Path(data["worktree"])
    head_before = git(work, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", data["base"])
    (repo / "later.txt").write_text("后续交付\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 推进父分支")
    key = f"branch.{data['branch']}.mdf-start-commit"
    saved = git(work, "config", "--local", "--get", key).stdout.strip()
    assert saved == data["start_commit"]
    assert saved != git(repo, "rev-parse", data["base"]).stdout.strip()
    assert git(work, "rev-parse", "HEAD").stdout.strip() == head_before
    assert head_before != saved


def test_start_release_requires_objectives_and_rejects_markers(
    python_exe: str, tmp_path: Path,
):
    repo = local_repo(tmp_path)
    missing = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "release",
        "--version", "1.3.0",
    )
    assert "missing_objectives" in missing.stderr
    template = tmp_path / "blank.md"
    template.write_text("# 发布目标\n\n{{MDF_RELEASE_SCOPE}}\n")
    marked = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "release",
        "--version", "1.3.0", "--objectives-file", str(template),
    )
    assert "missing_objectives" in marked.stderr
    hotfix_missing = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "hotfix",
        "--version", "1.2.1",
    )
    assert "missing_objectives" in hotfix_missing.stderr
    hotfix = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "hotfix",
        "--version", "1.2.1", "--objectives-file",
        str(write_work_objectives(tmp_path)),
    ))
    assert (Path(hotfix["worktree"]) / "changes/unreleased/1.2.1/objectives.md").is_file()
