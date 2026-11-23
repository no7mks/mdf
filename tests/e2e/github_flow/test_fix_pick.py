"""已有修复的移植保留目标基线与完整验收链。"""

from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from support_github_flow import error_of, github_flow_repo


def lines_with_fix(tmp_path, kind, *, origin=False, archive_bug=False):
    project = github_flow_repo(tmp_path, trunk="main", origin=origin)
    repo = project[0] if origin else project
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "tag", "v1.2.0")
    git(repo, "branch", "support/1.2")
    if origin:
        git(repo, "push", "origin", "support/1.2")
    if kind == "bugfix":
        git(repo, "checkout", "support/1.2")
    elif archive_bug:
        bug = repo / "docs/bugs" / BUG_NAME
        archive = bug.parent / "archive" / "1.3"
        archive.mkdir(parents=True)
        bug.write_text(bug.read_text().replace("status: open", "status: closed\nfixed_in: 1.3.0"))
        bug.rename(archive / bug.name)
    (repo / "repair.txt").write_text("已有修复\n")
    commit(repo, f"fix: 修复 {BUG_ID}")
    fix = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "regression.txt").write_text("已有回归用例\n")
    commit(repo, f"test: 覆盖 {BUG_ID}")
    test = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "main")
    return repo, base, fix, test


@pytest.mark.parametrize("kind", ["hotfix", "bugfix"])
def test_pick_bypasses_development_and_routes_through_acceptance(python_exe, tmp_path, kind):
    repo, base, fix, test = lines_with_fix(tmp_path, kind, origin=True, archive_bug=(kind == "hotfix"))
    if kind == "hotfix":
        git(repo, "push", "origin", "main")
        kind_args = ("--version", "1.2.1")
        source, target = "refs/remotes/origin/main", "support/1.2"
    else:
        git(repo, "push", "origin", "support/1.2")
        git(repo, "branch", "-D", "support/1.2")
        kind_args = ("--pick-from", "support/1.2")
        source, target = "refs/remotes/origin/support/1.2", "main"
    objective = write_work_objectives(tmp_path)
    objective.write_text(
        "# 目标\n\n移植已有修复。\n\n- needs_design: no\n\n"
        "## 步骤\n\n- [ ] 修复\n- [ ] converge\n- [x] lint\n- [x] code-review\n"
        "\n## 准备说明\n\n已有环境。\n"
    )
    started = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", kind, "--bug", BUG_ID,
                          *kind_args, "--pick-commit", fix, "--pick-commit", test, "--objectives-file", str(objective)))
    work = Path(started["worktree"])
    assert started["base"] == target
    assert started["start_commit"] == base
    assert started["roles"] == {"qa": [], "dev": []}
    assert started["pick"] == {"bug": BUG_ID, "source_ref": source, "source_head": test, "commits": [fix, test]}
    assert not (work / "repair.txt").exists()
    from mdf_core.lifecycle.delivery_state import locate

    root, identity = locate(work)
    assert identity["pick"] == started["pick"]
    assert identity["needs_design"] is False
    path = root / "objectives.md"
    assert "## 准备说明\n\n已有环境。" in path.read_text()
    route = ("delivery", "route", "--repo", str(work))
    expected = ["pick", "lint", "code-review", "verify branch", "fact audit", "catch-up", "consolidate"]
    assert payload(mdf(python_exe, *route))["result"]["pending"] == expected
    if kind == "hotfix":
        patch = tmp_path / "fix.patch"
        patch.write_text(git(work, "diff", f"{fix}^", fix, "--", "repair.txt").stdout)
        git(work, "apply", "--3way", "--index", str(patch))
        git(work, "commit", "-m", f"fix: 移植 {BUG_ID}", "-m", f"来源 {fix}")
        git(work, "cherry-pick", "-x", test)
    else:
        git(work, "cherry-pick", "-x", fix, test)
    assert (work / "repair.txt").read_text() == "已有修复\n"
    assert (work / "regression.txt").read_text() == "已有回归用例\n"
    assert not git(work, "diff", base, "--", "docs/bugs").stdout
    path.write_text(path.read_text().replace("- [ ] pick\n", "- [x] pick\n"))
    routed = payload(mdf(python_exe, *route))["result"]
    assert routed["next"] == "lint"
    assert routed["pending"] == expected[1:]


@pytest.mark.parametrize("source_problem", ["wrong_line", "short_sha", "missing_source", "parallel_roster"])
def test_invalid_pick_creates_no_delivery_branch(python_exe, tmp_path, source_problem):
    repo, base, fix, test = lines_with_fix(tmp_path, "hotfix")
    options = ["--pick-from", "support/1.2", "--pick-commit", fix]
    if source_problem == "short_sha":
        options[-1] = fix[:8]
    elif source_problem == "missing_source":
        options[1] = "support/1.3"
    elif source_problem == "parallel_roster":
        options[-1] = base
        options.extend(("--roster", "min-tdd"))
    result = mdf(python_exe, "start", "--repo", str(repo), "--kind", "bugfix", "--bug", BUG_ID, *options,
                 "--objectives-file", str(write_work_objectives(tmp_path)))
    assert error_of(result)["error"] == "invalid_pick"
    assert not git(repo, "branch", "--list", "bugfix/*", "qa/*", "dev/*").stdout


@pytest.mark.parametrize("kind", ["hotfix", "bugfix"])
def test_pick_rejects_unshared_fix_even_when_local_source_contains_it(python_exe, tmp_path, kind):
    repo, _base, fix, _test = lines_with_fix(tmp_path, kind, origin=True)
    kind_args = ("--version", "1.2.1") if kind == "hotfix" else ("--pick-from", "support/1.2")
    result = mdf(python_exe, "start", "--repo", str(repo), "--kind", kind, "--bug", BUG_ID, *kind_args,
                 "--pick-commit", fix, "--objectives-file", str(write_work_objectives(tmp_path)))
    assert error_of(result)["details"]["commit"] == fix
    assert not git(repo, "branch", "--list", "hotfix/*", "bugfix/*").stdout
