"""本地 merge 必须先确认远端实际接纳，才能发布或清理。"""
from mdf_test_support import *  # noqa: F403
from support_github_flow import error_of
from support_release_flow import prepared_release


@pytest.mark.parametrize("github", [False, True])
def test_failed_merge_push_routes_back_to_merge(python_exe, tmp_path, monkeypatch, github):
    repo, remote, work, _ = prepared_release(python_exe, tmp_path, monkeypatch, github=github)
    if github:
        payload(mdf(python_exe, "publish", "--repo", str(work)))
    hook = remote / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    failed = mdf(python_exe, "merge", "--repo", str(work))
    assert failed.returncode != 0
    route = payload(mdf(python_exe, "delivery", "route", "--repo", str(work)))["result"]
    assert route["next"] == "merge", route
    hook.unlink()
    merged = payload(mdf(python_exe, "merge", "--repo", str(work)))
    route = payload(mdf(python_exe, "delivery", "route", "--repo", str(work)))["result"]
    assert route["next"] == ("close-out" if github else "publish"), route
    target = "master"
    assert git(remote, "rev-parse", target).stdout.strip() == merged["merge_commit"]


@pytest.mark.parametrize("github", [False, True])
def test_remote_target_rollback_blocks_cleanup(python_exe, tmp_path, monkeypatch, github):
    repo, remote, work, _ = prepared_release(python_exe, tmp_path, monkeypatch, github=github)
    target = "master"
    before = git(remote, "rev-parse", target).stdout.strip()
    if github:
        payload(mdf(python_exe, "publish", "--repo", str(work)))
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    if not github:
        payload(mdf(python_exe, "publish", "--repo", str(work)))
    git(remote, "update-ref", f"refs/heads/{target}", before)
    git(remote, "update-ref", "-d", "refs/heads/release/1.3.0")
    failed = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    assert error_of(failed)["error"] == "merge_required"
    assert git(repo, "rev-parse", "refs/heads/release/1.3.0").stdout.strip()
    assert git(remote, "rev-parse", "refs/tags/v1.3.0").stdout.strip()


@pytest.mark.parametrize("github", [False, True])
def test_merge_push_response_loss_preserves_actual_merge_receipt(python_exe, tmp_path, monkeypatch, github):
    from mdf_core.foundation.errors import MDFError
    from mdf_core.workspace import gitflow
    from mdf_core.lifecycle.publish import merge_record_path
    import json
    _, remote, work, _ = prepared_release(python_exe, tmp_path, monkeypatch, github=github)
    if github:
        payload(mdf(python_exe, "publish", "--repo", str(work)))
    original = gitflow._git
    def lost_response(repo, *args, **kwargs):
        result = original(repo, *args, **kwargs)
        if args[:1] == ("push",):
            raise MDFError("push 成功后响应丢失", code="command_failed")
        return result
    monkeypatch.setattr(gitflow, "_git", lost_response)
    assert error_of(mdf(python_exe, "merge", "--repo", str(work)))["error"] == "command_failed"
    record = json.loads(merge_record_path(work, "release/1.3.0", "1.3.0").read_text())
    assert record["merge_commit"] == git(remote, "rev-parse", "master").stdout.strip()
    route = payload(mdf(python_exe, "delivery", "route", "--repo", str(work)))["result"]
    assert route["next"] == ("close-out" if github else "publish")
    monkeypatch.setattr(gitflow, "_git", original)
    if not github:
        payload(mdf(python_exe, "publish", "--repo", str(work)))
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
