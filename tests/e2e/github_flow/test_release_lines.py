"""历史切点 release 的固定 SHA 冻结，以及 support/<major.minor> 维护线的惰性切出与发布。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from support_delivery import write_changelog_release
from support_github_flow import commit, error_of, github_flow_repo, has_ref
from test_local_flow import start


def tag_trunk(repo, name):
    git(repo, "tag", "-a", name, "-m", f"test: {name}")


def advance(repo, name="later.txt"):
    (repo / name).write_text("trunk 之后的提交\n")
    commit(repo, f"test: 推进 trunk {name}")
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def push_all(repo):
    git(repo, "push", "origin", "--all")
    git(repo, "push", "origin", "--tags")


def release_start(python_exe, repo, tmp_path, cut, version="1.3.0"):
    return mdf(python_exe, "start", "--repo", str(repo), "--kind", "release", "--version", version,
               "--from-commit", cut, "--objectives-file", str(write_release_objectives(tmp_path)))


def test_from_commit_freezes_cutpoint_even_when_trunk_has_not_advanced(python_exe, tmp_path):
    repo, _ = github_flow_repo(tmp_path, origin=True)
    tag_trunk(repo, "v1.2.0")
    cut = git(repo, "rev-parse", "HEAD").stdout.strip()
    data = payload(release_start(python_exe, repo, tmp_path, "HEAD"))
    work = Path(data["worktree"])
    identity = json.loads((work / "changes/unreleased/1.3.0/delivery.json").read_text())
    assert identity["frozen_cutpoint"] is True and identity["cutpoint_commit"] == cut
    assert identity["start_commit"] == cut


def test_frozen_release_ignores_later_trunk_and_blocks_catch_up(python_exe, tmp_path):
    repo, _ = github_flow_repo(tmp_path, origin=True)
    tag_trunk(repo, "v1.2.0")
    cut = git(repo, "rev-parse", "HEAD").stdout.strip()
    later = advance(repo)
    data = payload(release_start(python_exe, repo, tmp_path, cut))
    work = Path(data["worktree"])
    assert not (work / "later.txt").exists()
    blocked = mdf(python_exe, "merge-no-ff", "--repo", str(work), "--commit", "master")
    assert error_of(blocked)["error"] == "frozen_cutpoint"
    assert "release/1.3.0" not in git(work, "branch", "--contains", later).stdout


def test_local_conflict_recovery_tags_the_locked_release_head(python_exe, tmp_path):
    repo, _remote = github_flow_repo(tmp_path, origin=True)
    tag_trunk(repo, "v1.2.0")
    cut = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "src/service.py").write_text("trunk = True\n")
    commit(repo, "test: trunk 并行")
    push_all(repo)
    data = payload(release_start(python_exe, repo, tmp_path, cut))
    work = Path(data["worktree"])
    write_changelog_release(work, "1.3.0")
    (work / "src/service.py").write_text("release = True\n")
    commit(work)
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    failed = error_of(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert failed["error"] == "merge_conflict" and head in failed["details"]["recovery"]
    assert run(["git", "merge", "--no-ff", "--no-commit", head], cwd=repo).returncode != 0
    (repo / "src/service.py").write_text("trunk = True\nrelease = True\n")
    git(repo, "add", "src/service.py")
    git(repo, "commit", "-m", "chore: 解决发布冲突")
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert git(repo, "rev-parse", "v1.3.0^{commit}").stdout.strip() == head


def test_cutpoint_release_publishes_with_tag_on_release_head(python_exe, tmp_path):
    repo, remote = github_flow_repo(tmp_path, origin=True)
    tag_trunk(repo, "v1.2.0")
    cut = git(repo, "rev-parse", "HEAD").stdout.strip()
    later = advance(repo)
    push_all(repo)
    data = payload(release_start(python_exe, repo, tmp_path, cut))
    work = Path(data["worktree"])
    write_changelog_release(work, "1.3.0")
    commit(work)
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert git(repo, "rev-parse", "v1.3.0^{commit}").stdout.strip() == head
    assert head != git(repo, "rev-parse", "master").stdout.strip()
    git(repo, "merge-base", "--is-ancestor", head, "master")
    git(repo, "merge-base", "--is-ancestor", later, "master")
    assert git(remote, "rev-parse", "master").stdout == git(repo, "rev-parse", "master").stdout


@pytest.mark.parametrize("case", ["off_first_parent", "before_latest_tag", "unknown", "wrong_kind"])
def test_cutpoint_validation(python_exe, tmp_path, case):
    repo, _ = github_flow_repo(tmp_path, origin=True)
    tag_trunk(repo, "v1.2.0")
    if case == "off_first_parent":
        git(repo, "checkout", "-b", "side")
        side = advance(repo, "side.txt")
        git(repo, "checkout", "master")
        git(repo, "merge", "--no-ff", "-m", "test: 合并 side", "side")
        cut, code = side, "cutpoint_not_on_trunk"
    elif case == "before_latest_tag":
        first = git(repo, "rev-parse", "HEAD").stdout.strip()
        advance(repo)
        git(repo, "tag", "-d", "v1.2.0")
        tag_trunk(repo, "v1.2.0")
        cut, code = first, "cutpoint_before_latest_release"
    elif case == "unknown":
        cut, code = "0" * 40, "invalid_cutpoint"
    else:
        cut, code = "HEAD", "invalid_arguments"
    if case == "wrong_kind":
        result = mdf(python_exe, "start", "--repo", str(repo), "--kind", "hotfix", "--version", "1.2.1",
                     "--from-commit", cut, "--objectives-file", str(write_work_objectives(tmp_path)))
    else:
        result = release_start(python_exe, repo, tmp_path, cut)
    assert error_of(result)["error"] == code
    assert not has_ref(repo, "release/1.3.0")


def test_cutpoint_requires_github_flow(python_exe, tmp_path):
    from support_delivery import start_repo
    repo, _ = start_repo(tmp_path)
    result = release_start(python_exe, repo, tmp_path, "HEAD")
    assert error_of(result)["error"] == "invalid_arguments"


def test_first_release_has_no_previous_tag_requirement(python_exe, tmp_path):
    repo, _ = github_flow_repo(tmp_path, origin=True)
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace('latest_release: "1.2.0"', "latest_release: null"))
    commit(repo)
    data = payload(release_start(python_exe, repo, tmp_path, "HEAD", "0.1.0"))
    assert data["branch"] == "release/0.1.0"


def hotfix(python_exe, repo, tmp_path, *extra):
    return mdf(python_exe, "start", "--repo", str(repo), "--kind", "hotfix",
               "--objectives-file", str(write_work_objectives(tmp_path)), *extra)


def two_lines(repo):
    tag_trunk(repo, "v1.1.0")
    advance(repo, "one-two.txt")
    tag_trunk(repo, "v1.2.0")
    advance(repo, "after.txt")
    push_all(repo)


def test_multiple_lines_require_explicit_support(python_exe, tmp_path):
    repo, _ = github_flow_repo(tmp_path, origin=True)
    two_lines(repo)
    failed = error_of(hotfix(python_exe, repo, tmp_path, "--version", "1.2.1"))
    assert failed["error"] == "support_required" and failed["details"]["lines"] == ["1.1", "1.2"]
    assert not has_ref(repo, "hotfix/1.2.1")


def test_single_line_hotfix_uses_support_and_excludes_unpublished_trunk(python_exe, tmp_path):
    repo, _ = github_flow_repo(tmp_path, origin=True)
    assert error_of(hotfix(python_exe, repo, tmp_path, "--version", "1.2.1"))["error"] == "missing_release_tag"
    tag_trunk(repo, "v1.2.0")
    advance(repo, "unpublished.txt")
    push_all(repo)
    data = payload(hotfix(python_exe, repo, tmp_path, "--version", "1.2.1"))
    work = Path(data["worktree"])
    assert data["base"] == "support/1.2"
    assert not (work / "unpublished.txt").exists()
    manifest = git(repo, "show", "support/1.2:.mdf/manifest.yaml").stdout
    assert 'latest_release: "1.2.0"' in manifest


def test_support_branch_is_cut_lazily_and_syncs_trunk_config(python_exe, tmp_path):
    repo, _ = github_flow_repo(tmp_path, origin=True, pr=True)
    legacy = repo / ".mdf/manifest.yaml"
    keep = legacy.read_text()
    legacy.write_text(keep.replace("workflow:\n  model: github-flow\n  trunk: master\n", "").split("closeout:")[0])
    commit(repo, "test: 旧线 manifest 尚无 workflow 配置")
    legacy.write_text(keep)
    two_lines(repo)
    assert not has_ref(repo, "support/1.1")
    data = payload(hotfix(python_exe, repo, tmp_path, "--version", "1.1.1", "--support", "1.1"))
    work = Path(data["worktree"])
    assert data["base"] == "support/1.1"
    assert git(repo, "rev-parse", "support/1.1~1").stdout == git(repo, "rev-parse", "v1.1.0^{commit}").stdout
    manifest = git(repo, "show", "support/1.1:.mdf/manifest.yaml").stdout
    assert "workflow:\n  model: github-flow\n  trunk: master\n" in manifest
    assert "closeout:\n  mode: pr\n  provider: github\n" in manifest
    identity = json.loads((work / "changes/unreleased/1.1.1/delivery.json").read_text())
    assert identity["base_branch"] == "support/1.1" and identity["target"] == "support/1.1"
    assert not (work / "after.txt").exists() and not (work / "one-two.txt").exists()
    assert git(repo, "worktree", "list").stdout.count("mdf-support") == 0


def test_support_option_validation(python_exe, tmp_path):
    repo, _ = github_flow_repo(tmp_path, origin=True)
    two_lines(repo)
    assert error_of(hotfix(python_exe, repo, tmp_path, "--version", "1.1.1", "--support", "9.9"))["error"] == "missing_release_tag"
    assert error_of(hotfix(python_exe, repo, tmp_path, "--version", "1.2.1", "--support", "1.1"))["error"] == "version_line_mismatch"
    assert error_of(hotfix(python_exe, repo, tmp_path, "--version", "1.1.1", "--support", "one"))["error"] == "invalid_support"
    assert not has_ref(repo, "support/1.1")


def test_support_hotfix_publishes_to_support_only_and_never_merges_back(python_exe, tmp_path):
    repo, remote = github_flow_repo(tmp_path, origin=True)
    two_lines(repo)
    trunk_before = git(repo, "rev-parse", "master").stdout
    data = payload(hotfix(python_exe, repo, tmp_path, "--version", "1.1.1", "--support", "1.1"))
    work = Path(data["worktree"])
    write_changelog_release(work, "1.1.1")
    (work / "src/service.py").write_text("fixed = True\n")
    commit(work)
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert done["targets"] == ["support/1.1"] and done["tag"] == "v1.1.1"
    assert git(repo, "rev-parse", "v1.1.1^{commit}").stdout.strip() == head
    assert git(repo, "rev-parse", "master").stdout == trunk_before
    assert git(remote, "rev-parse", "master").stdout == trunk_before
    assert git(remote, "rev-parse", "support/1.1").stdout == git(repo, "rev-parse", "support/1.1").stdout
    git(repo, "merge-base", "--is-ancestor", head, "support/1.1")
