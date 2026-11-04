"""hotfix slug 的版本约定、自动定版、归档与发布恢复。"""
import json
from pathlib import Path

import pytest

from mdf_test_support import BUG_ID, BUG_NAME, git, mdf, payload, seed_verify_branch, write_work_objectives
from support_delivery import commit, start_repo


def start(python_exe, tmp_path, repo, version=None):
    args = ["--version", version] if version else []
    result = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "hotfix", "--name", "fix-login",
        "--objectives-file", str(write_work_objectives(tmp_path)), *args,
    ))
    return Path(result["worktree"])


def resolve(python_exe, work, *extra):
    return mdf(python_exe, "delivery", "resolve-version", "--repo", str(work), *extra)


@pytest.mark.parametrize("version", [None, "1.2.1"])
def test_start_separates_slug_from_optional_version(python_exe, tmp_path, version):
    repo, _ = start_repo(tmp_path)
    work = start(python_exe, tmp_path, repo, version)
    data = payload(mdf(python_exe, "delivery", "status", "--repo", str(work)))["result"]
    assert data["path"] == "changes/unreleased/fix-login"
    assert data["delivery"]["branch"] == "hotfix/fix-login"
    assert data["delivery"].get("version") == version
    assert work == repo.parent / f"{repo.name}-worktrees/hotfix/fix-login"
    assert not git(work, "status", "--porcelain").stdout
    if version:
        assert payload(resolve(python_exe, work))["result"] == {"version": version, "tag": "v1.2.1"}


def test_auto_version_uses_largest_reachable_semver_and_stays_fixed(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    for tag in ["v1.2.9", "v1.2.11-rc.1", "v3.0.0+build", "4.0.0"]:
        git(repo, "tag", tag)
    git(repo, "tag", "-a", "v1.2.10", "-m", "test: 正式发布")
    git(repo, "checkout", "develop")
    (repo / "development.txt").write_text("尚未发布\n")
    commit(repo)
    git(repo, "tag", "v9.0.0")
    git(repo, "checkout", "master")
    work = start(python_exe, tmp_path, repo)
    result = payload(resolve(python_exe, work))["result"]
    assert result == {"version": "1.2.11", "tag": "v1.2.11"}
    commit(work)
    git(repo, "tag", "v1.3.0", "master")
    assert payload(resolve(python_exe, work))["result"] == result
    assert "hotfix_version_changed" in resolve(python_exe, work, "--version", "1.3.1").stderr


def test_missing_tag_requires_explicit_version_without_partial_write(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    work = start(python_exe, tmp_path, repo)
    assert "missing_release_tag" in resolve(python_exe, work).stderr
    assert not git(work, "status", "--porcelain").stdout
    assert payload(resolve(python_exe, work, "--version", "1.2.1"))["result"]["tag"] == "v1.2.1"


def hotfix_input():
    return json.dumps({
        "body": "修复登录超时。", "fixed": [BUG_ID], "release_notes": {"Fixed": ["修复登录超时"]},
        "evidence": {"tests": ["tests/test_service.py"], "commands": [], "artifacts": []},
    })


def closeout(python_exe, work, *extra):
    return mdf(python_exe, "release-closeout", "--repo", str(work), "--release-date", "2026-11-04",
               "--hotfix-change-json", hotfix_input(), *extra)


@pytest.mark.parametrize("pr_mode", [False, True])
def test_closeout_auto_version_archives_slug_and_keeps_real_source(python_exe, tmp_path, monkeypatch, pr_mode):
    repo, remote = start_repo(tmp_path)
    bug = repo / "docs/bugs" / BUG_NAME
    bug.write_text(bug.read_text().replace("status: open", "status: closed\nfixed_in: 1.2.1"))
    if pr_mode:
        manifest = repo / ".mdf/manifest.yaml"
        manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
    commit(repo)
    git(repo, "tag", "v1.2.0")
    git(repo, "push", "origin", "master")
    work = start(python_exe, tmp_path, repo)
    seed_verify_branch(python_exe, work)
    before = git(work, "status", "--porcelain").stdout
    assert payload(closeout(python_exe, work, "--dry-run"))["summary"]["version"] == "1.2.1"
    assert git(work, "status", "--porcelain").stdout == before
    result = payload(closeout(python_exe, work))
    assert result["version"] == "1.2.1"
    archived = work / "changes/1.2.1"
    data = json.loads((archived / "delivery.json").read_text())
    assert data["slug"] == "fix-login" and data["version"] == "1.2.1"
    assert "source_branch: hotfix/fix-login" in (archived / "CHANGE.md").read_text()
    assert not (work / "changes/unreleased/fix-login").exists()
    assert (archived / "verification-report.json").is_file()
    commit(work)
    if pr_mode:
        from mdf_core.reviewing.context import context
        status = payload(mdf(python_exe, "delivery", "status", "--repo", str(work)))["result"]
        assert status["path"] == "changes/1.2.1"
        review = context(work, "hotfix/fix-login", "HEAD", "master")
        assert "changes/1.2.1/CHANGE.md" in review["artifacts"]
        payload(mdf(python_exe, "verify", "--scope", "branch", "--repo", str(work)))
        assert not (work / "changes/unreleased/fix-login").exists()
        commit(work)
        from support_pull import Platform, squash_pending
        from mdf_core.lifecycle import pull_finish
        from mdf_core.lifecycle.publish import state_path
        platform = Platform()
        platform.repo, platform.remote = repo, remote
        identity = {"provider": "github", "host": "forge.invalid", "project": "team/project", "origin": str(remote)}
        monkeypatch.setattr(pull_finish, "origin", lambda *_: identity)
        monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
        squash_pending(work)
        first = payload(mdf(python_exe, "pr", "--repo", str(work)))
        merged = platform.merge(1, tmp_path)
        done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", first["source"]))
        assert done["completed"] and done["tag"] == "v1.2.1"
        state = json.loads(state_path(repo, first["source"]).read_text())
        back = state["backmerge"]
        review = context(Path(back["worktree"]), back["source"], "HEAD", "master")
        assert review["publication"]["source"] == "hotfix/fix-login"
        assert review["publication"]["merge_commit"] == merged
    else:
        done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
        assert done["tag"] == "v1.2.1"
        tagged = git(repo, "rev-parse", "v1.2.1").stdout
        payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", "hotfix/fix-login"))
        assert git(repo, "rev-parse", "v1.2.1").stdout == tagged
        git(repo, "worktree", "remove", str(work))
        payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", "hotfix/fix-login"))
        assert git(repo, "rev-parse", "v1.2.1").stdout == tagged


def test_bug_close_requires_frozen_hotfix_version(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    work = start(python_exe, tmp_path, repo)
    bug = work / "docs/bugs" / BUG_NAME
    bug.write_text(bug.read_text().replace("status: open", "status: fixed"))
    commit(work)
    args = ["bug", "close", BUG_ID, "--repo", str(work), "--fixed-in", "1.2.1"]
    assert "missing_hotfix_version" in mdf(python_exe, *args).stderr
    payload(resolve(python_exe, work, "--version", "1.2.1"))
    commit(work)
    assert "invalid_fixed_in" in mdf(python_exe, *args[:-1], "1.2.2").stderr
    assert payload(mdf(python_exe, *args))["fixed_in"] == "1.2.1"


def test_pr_publishes_slug_with_frozen_version_and_resumes_after_source_removal(python_exe, tmp_path, monkeypatch):
    from support_pull import prepare
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, hotfix_name="fix-login")
    first = payload(mdf(python_exe, "pr", "--repo", str(work)))
    merged = platform.merge(1, tmp_path)
    result = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", first["source"]))
    assert result["completed"] and result["tag"] == "v1.2.1"
    assert git(remote, "rev-parse", "v1.2.1^{commit}").stdout.strip() == merged
    git(remote, "merge-base", "--is-ancestor", merged, "develop")
    assert payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", first["source"]))["completed"]
