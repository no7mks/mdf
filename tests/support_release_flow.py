"""经真实 catch-up 与 consolidate 准备版本交付，供入口和事务回归使用。"""
from pathlib import Path

from mdf_test_support import (
    BUG_NAME, git, mdf, payload, replace, seed_verify_branch, write_release_objectives, write_unreleased_change,
)
from support_delivery import commit, start_repo
from support_github_flow import github_flow_repo
from support_pull import Platform


def analyze_history(work):
    from mdf_core.workspace.squash import check
    from squash_execute import execute
    plan = check(work)
    if not plan["noop"]:
        plan.update(start_commit=plan["floor"], segments=[{"tip": plan["old_tip"], "message": "test: 整理交付历史"}])
        execute(work.resolve(), plan, False, [])


def prepared_release(python_exe, tmp_path, monkeypatch, *, github=True, pr=False, consolidate=True):
    repo, remote = (github_flow_repo(tmp_path, origin=True, pr=pr, previous_release=True) if github
                    else start_repo(tmp_path, previous_release=True))
    if pr and not github:
        manifest = repo / ".mdf/manifest.yaml"
        manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
    write_unreleased_change(repo, "service-health")
    replace(repo / "docs/bugs" / BUG_NAME, "status: open", "status: closed\nfixed_in: 1.3.0")
    commit(repo)
    if not github:
        git(repo, "branch", "-f", "develop", "master")
    git(repo, "push", "origin", "--all")
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    from mdf_core.lifecycle import pull_finish
    identity = {"provider": "github", "host": "forge.invalid", "project": "team/project", "origin": str(remote)}
    monkeypatch.setattr(pull_finish, "origin", lambda *_: identity)
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    started = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "release", "--version", "1.3.0",
                          "--objectives-file", str(write_release_objectives(tmp_path))))
    work = Path(started["worktree"])
    seed_verify_branch(python_exe, work)
    objective = work / "changes/unreleased/1.3.0/objectives.md"
    before, after = objective.read_text().split("- [ ] catch-up", 1)
    objective.write_text(before.replace("[ ]", "[x]") + "- [ ] catch-up" + after)
    commit(work)
    analyze_history(work)
    sync = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    payload(mdf(python_exe, "catch-up", "--repo", str(work), "--complete", "--reviewed-head", sync["head"],
                "--summary", "同名远端无新增内容，增量验收通过"))
    if consolidate:
        payload(mdf(python_exe, "consolidate", "--repo", str(work), "--release-date", "2026-11-20"))
    return repo, remote, work, platform
