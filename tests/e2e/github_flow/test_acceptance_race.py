"""增量验收和 PR 提交须保持本轮已审查的固定 SHA。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from support_github_flow import error_of
from support_release_flow import prepared_release


def test_pr_cannot_adopt_source_commit_after_integration_acceptance(python_exe, tmp_path, monkeypatch):
    from mdf_core.lifecycle import target_integration
    _, remote, work, platform = prepared_release(python_exe, tmp_path, monkeypatch, pr=True)
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    payload(mdf(python_exe, "pr", "--repo", str(work)))
    before = git(remote, "rev-parse", "release/1.3.0").stdout.strip()
    original = target_integration.require_integrated

    def race(repo, source, target):
        accepted = original(repo, source, target)
        (work / "src/concurrent.py").write_text("unreviewed = True\n")
        commit(work)
        return accepted

    monkeypatch.setattr(target_integration, "require_integrated", race)
    result = mdf(python_exe, "pr", "--repo", str(work))
    assert result.returncode != 0
    assert error_of(result)["error"] in {"pull_state_changed", "integration_required"}
    assert git(remote, "rev-parse", "release/1.3.0").stdout.strip() == before
    assert len(platform.pulls) == 1


@pytest.mark.parametrize("complete", [False, True])
def test_integration_cannot_accept_new_head_after_building_plan(python_exe, tmp_path, monkeypatch, complete):
    from mdf_core.lifecycle import target_integration
    _, _, work, _ = prepared_release(python_exe, tmp_path, monkeypatch)
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    if complete:
        (work / "src/reviewed.py").write_text("reviewed = True\n")
        commit(work)
        planned = payload(mdf(python_exe, "incremental-integration", "--repo", str(work)))
        assert not planned["completed"]
    reviewed = git(work, "rev-parse", "HEAD").stdout.strip()
    original = target_integration.build_plan
    concurrent = []

    def race(*args, **kwargs):
        plan = original(*args, **kwargs)
        (work / "src/concurrent.py").write_text("unreviewed = True\n")
        commit(work)
        concurrent.append(git(work, "rev-parse", "HEAD").stdout.strip())
        return plan

    monkeypatch.setattr(target_integration, "build_plan", race)
    extra = ["--complete", "--reviewed-head", reviewed, "--summary", "A 的增量验收通过"] if complete else []
    result = mdf(python_exe, "incremental-integration", "--repo", str(work), *extra)
    assert result.returncode != 0
    assert error_of(result)["error"] == "integration_required"
    state = json.loads(target_integration.state_path(work, "release/1.3.0").read_text())
    assert state.get("accepted_head") != concurrent[0]


@pytest.mark.parametrize("hook_name", ["pre-commit", "prepare-commit-msg", "commit-msg"])
def test_merge_hook_cannot_add_unreviewed_content(python_exe, tmp_path, monkeypatch, hook_name):
    repo, remote, work, _ = prepared_release(python_exe, tmp_path, monkeypatch, github=False)
    before = git(repo, "rev-parse", "master").stdout.strip()
    hooks = repo / ".git/test-hooks"
    hooks.mkdir()
    git(repo, "config", "core.hooksPath", str(hooks))
    hook = hooks / hook_name
    hook.write_text("#!/bin/sh\nprintf 'hook_added = True\\n' > src/hook_added.py\ngit add src/hook_added.py\n")
    hook.chmod(0o755)
    result = mdf(python_exe, "merge", "--repo", str(work))
    assert result.returncode != 0
    assert git(repo, "rev-parse", "master").stdout.strip() == before
    assert (repo / "src/hook_added.py").read_text() == "hook_added = True\n"
    assert git(repo, "diff", "--cached", "--name-only").stdout.strip()
    assert not git(remote, "for-each-ref", "refs/tags/v1.3.0").stdout


def test_pr_merge_cannot_add_content_outside_accepted_source(python_exe, tmp_path, monkeypatch):
    from support_release_flow import analyze_history
    _, remote, work, platform = prepared_release(python_exe, tmp_path, monkeypatch, github=False, pr=True)
    analyze_history(work)
    payload(mdf(python_exe, "pr", "--repo", str(work)))
    platform.merge(1, tmp_path)
    platform_work = tmp_path / "platform-1"
    (platform_work / "src/unreviewed.py").write_text("unreviewed = True\n")
    git(platform_work, "add", "src/unreviewed.py")
    git(platform_work, "commit", "--amend", "--no-edit")
    git(platform_work, "push", "--force", "origin", "master")
    platform.pulls[0]["merge_commit"] = git(platform_work, "rev-parse", "HEAD").stdout.strip()
    result = mdf(python_exe, "pr", "--repo", str(work))
    assert result.returncode != 0
    assert error_of(result)["error"] == "invalid_pull_merge"
    result = mdf(python_exe, "publish", "--repo", str(work))
    assert result.returncode != 0
    assert not git(remote, "for-each-ref", "refs/tags/v1.3.0").stdout



def test_merge_preserves_postcommit_without_symlink_privilege(python_exe, tmp_path, monkeypatch):
    import shlex
    repo, _, work, _ = prepared_release(python_exe, tmp_path, monkeypatch, github=False)
    hooks = repo / ".git/test-hooks"
    hooks.mkdir()
    git(repo, "config", "core.hooksPath", str(hooks))
    marker = repo / ".git/post-commit-ran"
    hook = hooks / "post-commit"
    hook.write_text("#!/bin/sh\nprintf 'done\\n' > " + shlex.quote(str(marker)) + "\n")
    hook.chmod(0o755)
    (hooks / "sample.sample").write_text("inactive hook sample\n")

    def denied(*args, **kwargs):
        raise PermissionError("没有创建 symlink 的权限")

    monkeypatch.setattr(Path, "symlink_to", denied)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    assert marker.read_text() == "done\n"
