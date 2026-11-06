"""master 起点、目标选择与 feature 侧纳入 ODR。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import local_repo, start_repo, commit, write_changelog_release


def start_feature(python_exe, repo, tmp_path, *extra):
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                       "--from-master", "--proposal", PRP_ID, "--roster", "solo",
                       "--objectives-file", str(write_work_objectives(tmp_path)), *extra))
    return Path(data["worktree"])


def start_odr(python_exe, repo, tmp_path):
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "on-demand-release",
                       "--version", "1.3.0", "--feature", "feature/service-health",
                       "--objectives-file", str(write_release_objectives(tmp_path))))
    assert data["base"] == "master"
    assert data["roster"]["reviewers"] == 3
    return Path(data["worktree"])


def feature_change(work):
    root = work / "changes/unreleased/service-health"
    (root / "CHANGE.md").write_text(
        "---\nchange_kind: feature\nsource_branch: feature/service-health\nproposals: [prp-0001]\n"
        "fixed: []\nclosed: []\ndeferred: []\nadrs: []\nrelease_notes:\n  Added: [健康接口]\n"
        "breaking: false\nevidence:\n  tests: [tests/test_service.py]\n  commands: [\"true\"]\n  artifacts: []\n"
        "---\n\n# 交付\n\n## 结果\n\n健康接口已完成。\n\n"
        "## 已更新的当前文档\n\n- docs/user-guide/README.md\n\n## 已知偏差\n\n无。\n")
    commit(work)


def test_pending_target_blocks_finish_and_selection_is_persistent(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    git(repo, "checkout", "develop")
    (repo / "not-released.py").write_text("pending = True\n")
    commit(repo)
    work = start_feature(python_exe, repo, tmp_path)
    assert not (work / "not-released.py").exists()
    feature_change(work)
    failed = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    assert "target_pending" in failed.stderr
    payload(mdf(python_exe, "delivery", "target", "--repo", str(work), "--target", "develop"))
    commit(work)
    git(work, "merge", "--no-ff", "--no-edit", "develop")
    result = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert result["targets"] == ["develop"]
    from mdf_core.foundation.yamlutil import read_frontmatter
    assert read_frontmatter(repo / "docs/proposals" / PRP_NAME)[0]["status"] == "implemented"


def test_feature_enters_odr_checkpoint_then_publishes_and_backmerges(python_exe, tmp_path):
    repo, remote = start_repo(tmp_path)
    odr = start_odr(python_exe, repo, tmp_path)
    pending = payload(mdf(python_exe, "delivery", "checkpoint", "--repo", str(odr)))["result"]
    assert pending == {"ready": False, "pending": ["feature/service-health"], "features": ["feature/service-health"]}
    failed = mdf(python_exe, "release-closeout", "--repo", str(odr), "--release-date", "2026-11-06")
    assert "features_pending" in failed.stderr
    work = start_feature(python_exe, repo, tmp_path, "--target", "on-demand-release/1.3.0")
    feature_change(work)
    git(work, "merge", "--no-ff", "--no-edit", "on-demand-release/1.3.0")
    result = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert result["targets"] == ["on-demand-release/1.3.0"]
    assert payload(mdf(python_exe, "delivery", "checkpoint", "--repo", str(odr)))["result"]["ready"]
    assert 'status: "implemented"' in (odr / "docs/proposals" / PRP_NAME).read_text()
    write_changelog_release(odr, "1.3.0")
    commit(odr)
    published = payload(mdf(python_exe, "finish-gitflow", "--repo", str(odr)))
    assert published["targets"] == ["master", "develop"]
    git(repo, "merge-base", "--is-ancestor", "master", "develop")
    assert git(remote, "rev-parse", "master").stdout == git(repo, "rev-parse", "master").stdout
    assert git(repo, "rev-parse", "v1.3.0^{commit}").stdout == git(repo, "rev-parse", "master").stdout


def test_develop_catchup_prevents_odr_selection(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    start_odr(python_exe, repo, tmp_path)
    work = start_feature(python_exe, repo, tmp_path)
    git(repo, "checkout", "develop")
    (repo / "unreleased.py").write_text("pending = True\n")
    commit(repo)
    git(work, "merge", "--no-ff", "--no-edit", "develop")
    failed = mdf(python_exe, "delivery", "target", "--repo", str(work), "--target", "on-demand-release/1.3.0")
    assert "unreleased_dependency" in failed.stderr
    data = json.loads((work / "changes/unreleased/service-health/delivery.json").read_text())
    assert data["target"] is None


def test_manual_from_master_keeps_manual_contract(python_exe, tmp_path):
    from test_manual_feature import objectives
    repo = local_repo(tmp_path)
    obj = tmp_path / "manual.md"
    obj.write_text(objectives())
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature", "--manual",
                       "--name", "manual-work", "--from-master", "--target", "develop",
                       "--objectives-file", str(obj)))
    work = Path(data["worktree"])
    record = json.loads((work / "changes/unreleased/manual-work/delivery.json").read_text())
    assert record["manual"] and record["base_branch"] == "master" and record["target"] == "develop"
    assert (work / "changes/unreleased/manual-work/objectives.md").read_text() == objectives()


@pytest.mark.parametrize("mode", ["local", "pr"])
def test_odr_full_version_materials_and_publication(python_exe, tmp_path, monkeypatch, mode):
    from support_pull import Platform, squash_pending
    from mdf_core.lifecycle import pull_finish
    from mdf_core.foundation.yamlutil import read_frontmatter
    repo, remote = start_repo(tmp_path)
    # fixture 的未发布 Bug 在本次发布验证后关闭，避免无关待分类项。
    replace(repo / "docs/bugs" / BUG_NAME, "status: open", "status: closed\nfixed_in: 1.3.0")
    if mode == "pr":
        manifest = repo / ".mdf/manifest.yaml"
        manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
    commit(repo)
    git(repo, "branch", "-f", "develop", "master")
    git(repo, "push", "origin", "master", "develop")
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    identity = {"provider": "github", "host": "forge.invalid", "project": "team/project", "origin": str(remote)}
    monkeypatch.setattr(pull_finish, "origin", lambda *_: identity)
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    odr = start_odr(python_exe, repo, tmp_path)
    if mode == "pr":
        git(odr, "push", "origin", "on-demand-release/1.3.0")
    work = start_feature(python_exe, repo, tmp_path, "--target", "on-demand-release/1.3.0")
    feature_change(work)
    git(work, "merge", "--no-ff", "--no-edit", "on-demand-release/1.3.0")
    if mode == "pr":
        pull_finish.preflight(work, "feature/service-health")
        squash_pending(work)
        first = payload(mdf(python_exe, "pr", "--repo", str(work)))
        assert first["pull_request"]["target"] == "on-demand-release/1.3.0"
        assert "target_locked" in mdf(python_exe, "delivery", "target", "--repo", str(work), "--target", "develop").stderr
        platform.merge(1, tmp_path)
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert payload(mdf(python_exe, "delivery", "checkpoint", "--repo", str(odr)))["result"]["ready"]
    obj = odr / "changes/unreleased/1.3.0/objectives.md"
    obj.write_text(obj.read_text().replace("[ ]", "[x]"))
    commit(odr)
    seed_verify_branch(python_exe, odr)
    result = payload(mdf(python_exe, "release-closeout", "--repo", str(odr), "--release-date", "2026-11-06"))
    assert result["release_set"] == ["service-health"]
    root = odr / "changes/1.3.0"
    assert read_frontmatter(root / "CHANGE.md")[0]["change_kind"] == "on-demand-release"
    assert (root / "service-health/CHANGE.md").is_file()
    commit(odr)
    if mode == "pr":
        squash_pending(odr)
        second = payload(mdf(python_exe, "pr", "--repo", str(odr)))
        assert second["pull_request"]["target"] == "master"
        merged = platform.merge(2, tmp_path)
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(odr)))
    assert done["targets"] == ["master", "develop"]
    git(repo, "merge-base", "--is-ancestor", "master", "develop")
    if mode == "pr":
        assert done["completed"] and done["merge_commit"] == merged
        git(remote, "merge-base", "--is-ancestor", merged, "develop")
        assert len(platform.pulls) == 2
        assert payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo),
                           "--source", "on-demand-release/1.3.0"))["completed"]
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout == git(repo, "rev-parse", "master").stdout


def test_pending_target_cannot_catch_up_develop(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    work = start_feature(python_exe, repo, tmp_path)
    git(repo, "checkout", "develop")
    (repo / "pending.py").write_text("pending = True\n")
    commit(repo)
    before = git(work, "rev-parse", "HEAD").stdout
    failed = mdf(python_exe, "merge-no-ff", "--repo", str(work), "--commit", "develop")
    assert "target_pending" in failed.stderr
    assert git(work, "rev-parse", "HEAD").stdout == before


def test_odr_prevents_starting_same_prp_after_feature_cleanup(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    start_odr(python_exe, repo, tmp_path)
    work = start_feature(python_exe, repo, tmp_path, "--target", "on-demand-release/1.3.0")
    feature_change(work)
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    git(repo, "worktree", "remove", str(work))
    result = mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature", "--from-master",
                 "--proposal", PRP_ID, "--roster", "solo", "--objectives-file", str(write_work_objectives(tmp_path)))
    assert "proposal_started" in result.stderr
    assert not git(repo, "for-each-ref", "refs/heads/feature/service-health").stdout


def test_release_and_odr_share_version_namespace(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    start_odr(python_exe, repo, tmp_path)
    result = mdf(python_exe, "start", "--repo", str(repo), "--kind", "release", "--version", "1.3.0",
                 "--objectives-file", str(write_release_objectives(tmp_path)))
    assert "version_in_progress" in result.stderr


def test_odr_waits_for_all_selected_manual_features(python_exe, tmp_path):
    from test_manual_feature import objectives
    repo = local_repo(tmp_path)
    obj = tmp_path / "manual.md"
    obj.write_text(objectives())
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "on-demand-release",
                          "--version", "1.3.0", "--feature", "feature/first", "--feature", "feature/second",
                          "--objectives-file", str(write_release_objectives(tmp_path))))
    odr = Path(created["worktree"])
    for index, name in enumerate(("first", "second")):
        data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature", "--manual",
                           "--from-master", "--target", created["branch"], "--name", name,
                           "--objectives-file", str(obj)))
        work = Path(data["worktree"])
        root = work / "changes/unreleased" / name
        (root / "objectives.md").write_text(objectives(done=True))
        (root / "CHANGE.md").write_text(
            f"---\nchange_kind: feature\nsource_branch: feature/{name}\nproposals: []\n---\n")
        (work / f"{name}.py").write_text(f"{name} = True\n")
        commit(work)
        git(work, "merge", "--no-ff", "--no-edit", created["branch"])
        payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
        state = payload(mdf(python_exe, "delivery", "checkpoint", "--repo", str(odr)))["result"]
        assert state["ready"] == (index == 1)
        assert state["pending"] == ([] if index == 1 else ["feature/second"])


def test_source_argument_cannot_bypass_pending_odr(python_exe, tmp_path):
    repo, remote = start_repo(tmp_path)
    odr = start_odr(python_exe, repo, tmp_path)
    write_changelog_release(odr, "1.3.0")
    commit(odr)
    before = git(repo, "rev-parse", "master").stdout
    result = mdf(python_exe, "finish-gitflow", "--repo", str(odr),
                 "--source", "on-demand-release/1.3.0")
    assert result.returncode != 0
    assert git(repo, "rev-parse", "master").stdout == before
    assert git(remote, "rev-parse", "master").stdout == before


def test_checkpoint_requires_change_in_merged_feature(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    odr = start_odr(python_exe, repo, tmp_path)
    work = start_feature(python_exe, repo, tmp_path, "--target", "on-demand-release/1.3.0")
    git(odr, "merge", "--no-ff", "--no-edit", "feature/service-health")
    feature_change(odr)
    state = payload(mdf(python_exe, "delivery", "checkpoint", "--repo", str(odr)))["result"]
    assert not state["ready"] and state["pending"] == ["feature/service-health"]
    assert not (work / "changes/unreleased/service-health/CHANGE.md").exists()


def test_catchup_rejects_different_odr_target(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    start_odr(python_exe, repo, tmp_path)
    other = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "on-demand-release",
                        "--version", "1.4.0", "--feature", "feature/service-health",
                        "--objectives-file", str(write_release_objectives(tmp_path))))
    work = start_feature(python_exe, repo, tmp_path, "--target", "on-demand-release/1.3.0")
    before = git(work, "rev-parse", "HEAD").stdout
    result = mdf(python_exe, "merge-no-ff", "--repo", str(work), "--commit", other["branch"])
    assert "invalid_target" in result.stderr
    assert git(work, "rev-parse", "HEAD").stdout == before
