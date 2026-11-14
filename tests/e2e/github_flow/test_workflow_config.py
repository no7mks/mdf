"""workflow 配置：init 写入、manifest 校验、空闲态切换与 CI 触发分支。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from support_github_flow import commit, error_of, github_flow_repo, set_workflow


def _init(python_exe, repo, *extra):
    return mdf(python_exe, "init", "--repo", str(repo), "--latest-release", "none",
               *all_not_applicable_baselines(), *verification_args(), *extra)


def test_init_writes_workflow_block(python_exe, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# T\n", encoding="utf-8")
    init_git(repo)
    git(repo, "branch", "-m", "main")
    data = payload(_init(python_exe, repo, "--workflow", "github-flow", "--trunk", "main"))
    assert data["plan"]["workflow"] == {"model": "github-flow", "trunk": "main"}
    manifest = (repo / ".mdf/manifest.yaml").read_text(encoding="utf-8")
    assert "workflow:\n  model: github-flow\n  trunk: main\n" in manifest


def test_init_without_workflow_keeps_manifest_free_of_workflow(python_exe, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# T\n", encoding="utf-8")
    init_git(repo)
    git(repo, "branch", "-m", "master")
    data = payload(_init(python_exe, repo))
    assert data["plan"]["workflow"] == {"model": "gitflow", "trunk": "master"}
    assert "workflow:" not in (repo / ".mdf/manifest.yaml").read_text(encoding="utf-8")


def test_init_rejects_reserved_trunk(python_exe, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# T\n", encoding="utf-8")
    init_git(repo)
    assert error_of(_init(python_exe, repo, "--workflow", "github-flow", "--trunk", "develop"))["error"] == "invalid_workflow"


def test_init_rerun_cannot_silently_change_workflow(python_exe, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# T\n", encoding="utf-8")
    init_git(repo)
    git(repo, "branch", "-m", "master")
    payload(_init(python_exe, repo, "--workflow", "github-flow"))
    commit(repo)
    assert error_of(_init(python_exe, repo, "--workflow", "gitflow"))["error"] == "workflow_switch_required"
    payload(_init(python_exe, repo, "--workflow", "github-flow"))


def test_doctor_reports_invalid_workflow(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path)
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace("trunk: master", "trunk: develop"), encoding="utf-8")
    result = mdf(python_exe, "validate", "--repo", str(repo))
    codes = {item["code"] for item in json.loads(result.stdout)["findings"]}
    assert "manifest.workflow" in codes


@pytest.mark.parametrize("model", ["github-flow", "gitflow"])
@pytest.mark.parametrize("pr", [False, True])
def test_init_managed_block_limits_trunk_push_rule_to_github_flow_pr(python_exe, tmp_path, model, pr):
    repo = local_gitflow(tmp_path)
    agents = repo / "AGENTS.md"
    agents.write_bytes(agents.read_bytes() + b"\r\nCustom push rule.\r\n")
    options = ("--closeout-mode", "pr", "--closeout-provider", "github") if pr else ()
    payload(_init(python_exe, repo, "--workflow", model, *options))
    block, outside = agents.read_bytes().split(b"<!-- MDF:END -->")
    assert (b"$mdf trunk-pr" in block) == (model == "github-flow" and pr)
    assert outside.endswith(b"\r\nCustom push rule.\r\n")


def test_init_closeout_changes_refresh_block_and_preserve_other_settings(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path, trunk="main")
    manifest = repo / ".mdf/manifest.yaml"
    agents = repo / "AGENTS.md"
    manifest.write_text(manifest.read_text() + 'closeout:\n  mode: local\n  trivial_paths: ["docs/*"]\n')
    before = manifest.read_bytes(), agents.read_bytes()
    assert error_of(_init(python_exe, repo, "--closeout-mode", "pr"))["error"] == "invalid_closeout"
    assert (manifest.read_bytes(), agents.read_bytes()) == before

    payload(_init(python_exe, repo, "--closeout-mode", "pr", "--closeout-provider", "gitlab"))
    assert "$mdf trunk-pr" in agents.read_text()
    payload(_init(python_exe, repo))
    assert "$mdf trunk-pr" in agents.read_text()
    payload(_init(python_exe, repo, "--closeout-mode", "local"))
    assert "$mdf trunk-pr" not in agents.read_text()
    assert 'closeout:\n  mode: local\n  provider: gitlab\n  trivial_paths: ["docs/*"]\n' in manifest.read_text()
    payload(_init(python_exe, repo, "--closeout-mode", "pr"))
    assert "$mdf trunk-pr" in agents.read_text()


def test_switch_updates_trunk_push_rule_in_committed_block(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() + "closeout:\n  mode: pr\n  provider: gitlab\n")
    commit(repo)
    original = (repo / "AGENTS.md").read_text()
    switch = ("workflow", "switch", "--repo", str(repo), "--model")
    payload(mdf(python_exe, *switch, "github-flow"))
    assert "$mdf trunk-pr" in git(repo, "show", "HEAD:AGENTS.md").stdout
    payload(mdf(python_exe, *switch, "gitflow"))
    assert git(repo, "show", "HEAD:AGENTS.md").stdout == original


def test_switch_gitflow_to_github_flow_preserves_history_and_branches(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    before = git(repo, "rev-parse", "develop").stdout
    data = payload(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow"))
    assert data["changed"] and data["to"] == {"model": "github-flow", "trunk": "master"}
    assert git(repo, "rev-parse", "develop").stdout == before
    assert git(repo, "status", "--porcelain").stdout == ""
    assert "workflow:\n  model: github-flow\n  trunk: master\n" in (repo / ".mdf/manifest.yaml").read_text()
    again = payload(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow"))
    assert again["changed"] is False
    back = payload(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "gitflow"))
    assert back["to"]["model"] == "gitflow"
    assert (repo / ".mdf/manifest.yaml").read_text().count("workflow:") == 1


def local_gitflow(tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "-m", "master")
    git(repo, "branch", "develop")
    return repo


def test_switch_trunk_must_contain_old_history(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    git(repo, "checkout", "--orphan", "main")
    git(repo, "commit", "--allow-empty", "-m", "test: 孤立 trunk")
    result = mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow", "--trunk", "main")
    assert error_of(result)["error"] == "trunk_history_lost"


def test_switch_to_new_trunk_from_current_history(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    git(repo, "checkout", "-b", "main")
    data = payload(mdf(python_exe, "workflow", "switch", "--repo", str(repo),
                       "--model", "github-flow", "--trunk", "main"))
    assert data["from"]["trunk"] == "master" and data["to"]["trunk"] == "main"
    assert git(repo, "rev-parse", "--verify", "master").returncode == 0


def test_switch_requires_running_on_target_trunk(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    git(repo, "checkout", "develop")
    result = mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow")
    assert error_of(result)["error"] == "not_on_trunk"


@pytest.mark.parametrize("setup,detail", [
    ("branch", "feature/x"), ("planning", "planning"),
])
def test_switch_refuses_when_not_idle(python_exe, tmp_path, setup, detail):
    repo = local_gitflow(tmp_path)
    if setup == "branch":
        git(repo, "branch", detail)
    elif setup == "planning":
        git(repo, "checkout", "-b", "planning")
        (repo / "plan.txt").write_text("规划\n")
        commit(repo, "docs: 规划")
        git(repo, "checkout", "master")
    failed = error_of(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow"))
    assert failed["error"] == "workflow_not_idle"
    assert "workflow:" not in (repo / ".mdf/manifest.yaml").read_text()


def _finish_dir(repo):
    common = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    return common / "mdf" / "finish"


def test_obsolete_finish_files_do_not_block_switch(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    folder = _finish_dir(repo)
    (folder / "release").mkdir(parents=True)
    (folder / "integrate").mkdir()
    (folder / "sync" / "history").mkdir(parents=True)
    (folder / "release" / "1.2.0.json").write_text(json.dumps({"completed": False}))
    (folder / "integrate" / "1.2.0.json").write_text(json.dumps({"release_head": "abc"}))
    (folder / "sync" / "history" / "old.json").write_text(json.dumps({"completed": False}))
    data = payload(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow"))
    assert data["changed"] is True


def test_dirty_linked_worktree_blocks_switch(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    linked = tmp_path / "develop-wt"
    git(repo, "worktree", "add", str(linked), "develop")
    (linked / "dirty.txt").write_text("未提交\n")
    blocked = error_of(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow"))
    assert blocked["error"] == "workflow_not_idle"
    assert "workflow:" not in (repo / ".mdf/manifest.yaml").read_text()


def test_custom_trunk_and_support_stay_idle(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    git(repo, "branch", "support/1.2")
    git(repo, "branch", "main")
    git(repo, "checkout", "main")
    data = payload(mdf(python_exe, "workflow", "switch", "--repo", str(repo),
                       "--model", "github-flow", "--trunk", "main"))
    assert data["changed"] is True and data["to"]["trunk"] == "main"


def test_switch_to_gitflow_requires_develop(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path)
    failed = error_of(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "gitflow"))
    assert failed["error"] == "missing_branch"


@pytest.mark.parametrize("provider,expected", [
    ("github", "branches: [master, 'support/**']"),
    ("gitlab", '$CI_COMMIT_BRANCH == "master" || $CI_COMMIT_BRANCH =~ /^support\\/.*$/'),
])
def test_ci_follows_workflow(python_exe, tmp_path, provider, expected):
    repo = github_flow_repo(tmp_path)
    data = payload(mdf(python_exe, "workflow", "ci", "--repo", str(repo), "--provider", provider))
    assert data["branches"] == ["master", "support/**"]
    assert expected in data["content"]
    assert "develop" not in data["content"].split("mdf-review")[0] or provider == "github"


def test_ci_gitflow_keeps_develop_and_trunk(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    set_workflow(repo, "gitflow", "master")
    data = payload(mdf(python_exe, "workflow", "ci", "--repo", str(repo)))
    assert data["branches"] == ["develop", "master"]
    assert "branches: [develop, master]" in data["content"]


def _gitflow_main(tmp_path):
    repo = copy_fixture(tmp_path)
    set_workflow(repo, "gitflow", "main")
    init_git(repo)
    git(repo, "branch", "develop")
    return repo


def test_prepare_git_uses_requested_trunk(python_exe, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    created = payload(mdf(python_exe, "prepare-git", "--repo", str(plain), "--trunk", "main"))
    assert created["created"] is True and created["branch"] == "main"


def test_gitflow_main_planning_lands_on_trunk(python_exe, tmp_path):
    repo = _gitflow_main(tmp_path)
    ensured = payload(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))
    plan = Path(ensured["worktree"])
    assert ensured["branch"] == "planning"
    (plan / "plan.txt").write_text("规划\n")
    commit(plan, "docs: 规划")
    landed = payload(mdf(python_exe, "planning", "land", "--repo", str(plan)))
    assert landed["landed"] is True and landed["backmerged"] is True
    assert git(repo, "show", "main:plan.txt").stdout == "规划\n"
    assert git(repo, "merge-base", "--is-ancestor", "main", "develop").returncode == 0


def test_gitflow_main_odr_starts_from_trunk(python_exe, tmp_path):
    repo = _gitflow_main(tmp_path)
    git(repo, "checkout", "develop")
    feature = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature", "--from-master",
        "--proposal", PRP_ID, "--roster", "solo",
        "--objectives-file", str(write_work_objectives(tmp_path)),
    ))
    work = Path(feature["worktree"])
    record = json.loads((work / "changes/unreleased/service-health/delivery.json").read_text())
    assert record["base_branch"] == "main"
    odr = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "on-demand-release", "--version", "1.3.0",
        "--feature", "feature/service-health",
        "--objectives-file", str(write_release_objectives(tmp_path)),
    ))
    assert odr["base"] == "main"


def test_gitflow_main_pr_closeout_publishes_to_trunk(python_exe, tmp_path, monkeypatch):
    repo = _gitflow_main(tmp_path)
    remote = tmp_path / "origin.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    git(repo, "remote", "add", "origin", str(remote))
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() + "closeout:\n  mode: pr\n  provider: github\n", encoding="utf-8")
    commit(repo)
    git(repo, "branch", "-f", "develop", "main")
    git(repo, "push", "--all", "--set-upstream", "origin")
    git(repo, "remote", "set-head", "origin", "--auto")
    from support_pull import Platform, squash_pending
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    from mdf_core.lifecycle import pull_finish
    identity = {"provider": "github", "host": "forge.invalid", "project": "team/project", "origin": str(remote)}
    monkeypatch.setattr(pull_finish, "origin", lambda *_: identity)
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    started = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "release", "--version", "1.2.1",
        "--objectives-file", str(write_release_objectives(tmp_path)),
    ))
    work = Path(started["worktree"])
    from support_delivery import write_changelog_release
    write_changelog_release(work, "1.2.1")
    (work / "src/service.py").write_text("fixed = True\n")
    commit(work)
    pull_finish.preflight(work, "release/1.2.1")
    squash_pending(work)
    opened = payload(mdf(python_exe, "pr", "--repo", str(work)))
    assert opened["status"] == "waiting_for_merge"
    platform.merge(1, tmp_path)
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert done["completed"] is True
    assert "main" in done["targets"] and "master" not in done["targets"]
    assert git(remote, "rev-parse", "--verify", "refs/heads/main").returncode == 0
