"""同一 hotfix slug 在 local/PR mode 的连续发布与恢复。"""
import json
from pathlib import Path

import pytest

from mdf_test_support import BUG_NAME, git, mdf, payload, seed_verify_branch, write_work_objectives
from mdf_test_support import finish_delivery
from support_delivery import commit, start_repo
from support_pull import Platform, squash_pending


def interrupt_publication(monkeypatch, pr_mode):
    from mdf_core.foundation.errors import MDFError
    if pr_mode:
        from mdf_core.lifecycle import pull_publish
        original = pull_publish.tag_release

        def interrupted(*args):
            original(*args)
            raise MDFError("模拟 tag 发布后中断", code="test_interruption")
        monkeypatch.setattr(pull_publish, "tag_release", interrupted)
    else:
        from mdf_core.workspace import gitflow
        original = gitflow._git

        def interrupted(repo, *args, **kwargs):
            result = original(repo, *args, **kwargs)
            if args and args[0] == "push":
                raise MDFError("模拟发布 push 响应丢失", code="test_interruption")
            return result
        monkeypatch.setattr(gitflow, "_git", interrupted)


@pytest.mark.parametrize("pr_mode", [False, True])
@pytest.mark.parametrize("auto_version", [False, True])
def test_reuse_hotfix_slug_publishes_new_version_and_preserves_first_release(
    python_exe, tmp_path, monkeypatch, pr_mode, auto_version,
):
    repo, remote = start_repo(tmp_path)
    bug = repo / "docs/bugs" / BUG_NAME
    bug.write_text(bug.read_text().replace("status: open", "status: closed\nfixed_in: 1.2.1"))
    if pr_mode:
        manifest = repo / ".mdf/manifest.yaml"
        manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
    commit(repo)
    git(repo, "branch", "-f", "develop", "master")
    git(repo, "push", "origin", "master", "develop")
    git(repo, "tag", "v1.2.0")
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    from mdf_core.lifecycle import pull_finish
    identity = {"provider": "github", "host": "forge.invalid", "project": "team/project", "origin": str(remote)}
    monkeypatch.setattr(pull_finish, "origin", lambda *_: identity)
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    released = {}
    source = "hotfix/fix-login"
    for index, version in enumerate(("1.2.1", "1.2.2"), 1):
        args = [] if index == 2 and auto_version else ["--version", version]
        created = payload(mdf(
            python_exe, "start", "--repo", str(repo), "--kind", "hotfix", "--name", "fix-login",
            "--objectives-file", str(write_work_objectives(tmp_path)), *args,
        ))
        work = Path(created["worktree"])
        if not args:
            resolved = payload(mdf(python_exe, "delivery", "resolve-version", "--repo", str(work)))
            assert resolved["result"]["version"] == version
            commit(work)
        (work / "hotfix-result.txt").write_text(f"release = {index}\n")
        commit(work)
        seed_verify_branch(python_exe, work)
        change = json.dumps({
            "body": f"第 {index} 次修复。", "release_notes": {"Fixed": [f"第 {index} 次修复"]},
            "evidence": {"tests": ["tests/test_service.py"], "commands": [], "artifacts": []},
        })
        payload(mdf(python_exe, "release-closeout", "--repo", str(work), "--release-date", "2026-11-04",
                    "--hotfix-change-json", change))
        commit(work)
        if pr_mode:
            squash_pending(work)
            opened = payload(mdf(python_exe, "pr", "--repo", str(work)))
            assert opened["status"] == "waiting_for_merge"
            assert len(platform.pulls) == index
            merged = platform.merge(index, tmp_path)
        if index == 2:
            with monkeypatch.context() as patch:
                interrupt_publication(patch, pr_mode)
                interrupted = finish_delivery(python_exe, "finish-gitflow", "--repo", str(work))
                assert "test_interruption" in interrupted.stderr
        done = payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work)))
        assert done["tag"] == f"v{version}"
        head = git(remote, "rev-parse", f"v{version}^{{commit}}").stdout.strip()
        if pr_mode:
            assert done["completed"] and head == merged
            git(remote, "merge-base", "--is-ancestor", head, "develop")
        released[version] = head
        for previous, expected in released.items():
            assert git(remote, "rev-parse", f"v{previous}^{{commit}}").stdout.strip() == expected
        git(repo, "worktree", "remove", str(work))
        identity_args = ["--pull", str(index)] if pr_mode else ["--version", version]
        resumed = payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(repo), "--source", source, *identity_args))
        assert resumed["tag"] == f"v{version}"
    assert released["1.2.1"] != released["1.2.2"]
