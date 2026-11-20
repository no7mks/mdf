"""四种发布环境通过新主链完成材料、对象状态、tag 与收尾。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import start_repo, commit
from support_github_flow import github_flow_repo
from support_pull import Platform, squash_pending


@pytest.mark.parametrize("github,pr", [(False, False), (False, True), (True, False), (True, True)])
def test_release_delivery_matrix(python_exe, tmp_path, monkeypatch, github, pr):
    repo, remote = github_flow_repo(tmp_path, origin=True, pr=pr) if github else start_repo(tmp_path)
    if pr and not github:
        path = repo / ".mdf/manifest.yaml"
        path.write_text(path.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
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
    obj = work / "changes/unreleased/1.3.0/objectives.md"
    before, after = obj.read_text().split("- [ ] catch-up", 1)
    obj.write_text(before.replace("[ ]", "[x]") + "- [ ] catch-up" + after)
    commit(work)
    squash_pending(work)
    sync = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    payload(mdf(python_exe, "catch-up", "--repo", str(work), "--complete", "--reviewed-head", sync["head"],
                "--summary", "同名远端同步与增量验收通过"))
    payload(mdf(python_exe, "consolidate", "--repo", str(work), "--release-date", "2026-11-20"))
    root = work / "changes/1.3.0"
    assert (root / "CHANGE.md").is_file()
    prp = work / "docs/proposals/archive/1.3" / PRP_NAME
    bug = work / "docs/bugs/archive/1.3" / BUG_NAME
    assert "status: released" in prp.read_text() and "released_in: 1.3.0" in prp.read_text()
    assert "status: closed" in bug.read_text() and "fixed_in: 1.3.0" in bug.read_text()
    release_head = git(work, "rev-parse", "HEAD").stdout.strip()
    if github:
        payload(mdf(python_exe, "publish", "--repo", str(work)))
    if pr:
        squash_pending(work)
        payload(mdf(python_exe, "pr", "--repo", str(work)))
        merged = platform.merge(1, tmp_path)
        payload(mdf(python_exe, "pr", "--repo", str(work)))
    else:
        merged = payload(mdf(python_exe, "merge", "--repo", str(work)))["merge_commit"]
    if not github:
        payload(mdf(python_exe, "publish", "--repo", str(work)))
    tag_head = git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip()
    assert tag_head == (release_head if github else merged)
    body = git(remote, "for-each-ref", "--format=%(contents)", "refs/tags/v1.3.0").stdout
    assert "交付可验证的服务健康能力" in body
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert not git(repo, "branch", "--list", "release/1.3.0").stdout.strip()
    assert not git(work, "branch", "--show-current").stdout.strip()


@pytest.mark.parametrize("github,pr", [(False, False), (False, True), (True, False), (True, True)])
@pytest.mark.parametrize("kind", ["feature", "bugfix"])
def test_unreleased_delivery_matrix(python_exe, tmp_path, monkeypatch, github, pr, kind):
    from support_delivery import write_change
    repo, remote = github_flow_repo(tmp_path, origin=True, pr=pr) if github else start_repo(tmp_path)
    if pr and not github:
        path = repo / ".mdf/manifest.yaml"
        path.write_text(path.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
        commit(repo)
        git(repo, "branch", "-f", "develop", "master")
        git(repo, "push", "origin", "--all")
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    from mdf_core.lifecycle import pull_finish
    identity = {"provider": "github", "host": "forge.invalid", "project": "team/project", "origin": str(remote)}
    monkeypatch.setattr(pull_finish, "origin", lambda *_: identity)
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    extra = ("--proposal", PRP_ID, "--roster", "solo") if kind == "feature" else ("--bug", BUG_ID)
    started = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", kind, *extra,
                          "--objectives-file", str(write_work_objectives(tmp_path))))
    work = Path(started["worktree"])
    slug = "service-health" if kind == "feature" else "bug-cd34"
    root = write_change(work, started["branch"], slug)
    path = root / "CHANGE.md"
    text = path.read_text().replace("change_kind: fix", f"change_kind: {kind}")
    if kind == "feature":
        text = text.replace("proposals: []", "proposals: [prp-0001]")
    text = text.replace("fixed: []", "fixed: [bug-CD34]")
    path.write_text(text)
    if kind == "bugfix":
        (root / "suites.json").write_text(json.dumps({"suites": ["billing"]}))
    payload(mdf(python_exe, "verify", "--scope", "branch", "--repo", str(work)))
    obj = root / "objectives.md"
    before, after = obj.read_text().split("- [ ] catch-up", 1)
    obj.write_text(before.replace("[ ]", "[x]") + "- [ ] catch-up" + after)
    commit(work)
    squash_pending(work)
    sync = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    payload(mdf(python_exe, "catch-up", "--repo", str(work), "--complete", "--reviewed-head", sync["head"],
                "--summary", "同名远端同步验收通过"))
    payload(mdf(python_exe, "consolidate", "--repo", str(work)))
    assert "status: fixed" in (work / "docs/bugs" / BUG_NAME).read_text()
    if kind == "feature":
        assert "status: implemented" in (work / "docs/proposals" / PRP_NAME).read_text()
    if pr:
        squash_pending(work)
        payload(mdf(python_exe, "pr", "--repo", str(work)))
        platform.merge(1, tmp_path)
    else:
        payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert not git(repo, "branch", "--list", started["branch"]).stdout.strip()
    assert not git(repo, "tag", "--list").stdout.strip()


@pytest.mark.parametrize("pr", [False, True])
def test_hotfix_slug_consolidation_keeps_versioned_materials_available(python_exe, tmp_path, monkeypatch, pr):
    repo, remote = start_repo(tmp_path)
    bug = repo / "docs/bugs" / BUG_NAME
    bug.write_text(bug.read_text().replace("status: open", "status: closed\nfixed_in: 1.2.1"))
    if pr:
        manifest = repo / ".mdf/manifest.yaml"
        manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
    commit(repo)
    git(repo, "branch", "-f", "develop", "master")
    git(repo, "push", "origin", "--all")
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    from mdf_core.lifecycle import pull_finish
    identity = {"provider": "github", "host": "forge.invalid", "project": "team/project", "origin": str(remote)}
    monkeypatch.setattr(pull_finish, "origin", lambda *_: identity)
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    started = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "hotfix", "--name", "fix-login",
                          "--version", "1.2.1", "--objectives-file", str(write_work_objectives(tmp_path))))
    work = Path(started["worktree"])
    payload(mdf(python_exe, "verify", "--scope", "branch", "--repo", str(work)))
    obj = work / "changes/unreleased/fix-login/objectives.md"
    before, after = obj.read_text().split("- [ ] catch-up", 1)
    obj.write_text(before.replace("[ ]", "[x]") + "- [ ] catch-up" + after)
    commit(work)
    squash_pending(work)
    sync = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    payload(mdf(python_exe, "catch-up", "--repo", str(work), "--complete", "--reviewed-head", sync["head"],
                "--summary", "同步验收通过"))
    change = json.dumps({"fixed": [BUG_ID], "body": "调用超时已修复。", "release_notes": {"Fixed": ["修复调用超时"]},
                         "evidence": {"tests": ["tests/test_service.py"], "commands": [], "artifacts": []}})
    payload(mdf(python_exe, "consolidate", "--repo", str(work), "--hotfix-change-json", change,
                "--release-date", "2026-11-20"))
    material = payload(mdf(python_exe, "delivery", "status", "--repo", str(work)))["result"]
    assert material["path"] == "changes/1.2.1" and material["delivery"]["version"] == "1.2.1"
    payload(mdf(python_exe, "consolidate", "--repo", str(work), "--incremental"))
    if pr:
        squash_pending(work)
        payload(mdf(python_exe, "pr", "--repo", str(work)))
        platform.merge(1, tmp_path)
    else:
        payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert "修复调用超时" in git(remote, "for-each-ref", "--format=%(contents)", "refs/tags/v1.2.1").stdout
