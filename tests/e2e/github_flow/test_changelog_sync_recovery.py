"""记录同步的写入边界与恢复。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from support_github_flow import error_of
from test_support_consolidate import prepare_hotfix, consolidate_hotfix


def test_sync_preserves_external_changelog_symlink(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    changelog = repo / "CHANGELOG.md"
    original = changelog.read_text()
    outside = tmp_path / "external-changelog.md"
    outside.write_text(original)
    changelog.unlink()
    changelog.symlink_to(outside)
    commit(repo)
    git(repo, "push", "origin", "master")
    result = mdf(python_exe, "sync-changelog", "--repo", str(work))
    assert outside.read_text() == original
    assert error_of(result)["error"] == "managed_symlink"


@pytest.mark.parametrize("initial_pr", [False, True])
def test_sync_policy_comes_from_remote_trunk(python_exe, tmp_path, initial_pr):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=initial_pr)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    manifest = repo / ".mdf/manifest.yaml"
    text = manifest.read_text()
    manifest.write_text(text.replace("mode: pr", "mode: local") if initial_pr else
                        text + "\ncloseout:\n  mode: pr\n  provider: github\n")
    commit(repo)
    git(repo, "push", "origin", "master")
    expected = "close-out" if initial_pr else "sync-changelog"
    assert payload(mdf(python_exe, "publish", "--repo", str(work)))["next_intent"] == expected
    for checkout in (repo, work):
        route = payload(mdf(python_exe, "delivery", "route", "--repo", str(checkout),
                            "--source", "hotfix/1.2.1"))["result"]
        assert route["next"] == expected
    result = mdf(python_exe, "sync-changelog", "--repo", str(work))
    if initial_pr:
        assert error_of(result)["error"] == "invalid_workflow"
    else:
        assert payload(result)["next_intent"] == "pr"
        assert error_of(mdf(python_exe, "finish-gitflow", "--repo", str(work)))["error"] == "changelog_sync_required"


def test_sync_pr_uses_actual_ci_entry(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    prepared = payload(mdf(python_exe, "sync-changelog", "--repo", str(work)))
    pm_work = Path(prepared["worktree"])
    head = git(pm_work, "rev-parse", "HEAD").stdout.strip()
    base = git(pm_work, "rev-parse", "origin/master").stdout.strip()
    entry = Path(__file__).resolve().parents[3] / "skills/mdf/assets/ci/review.py"
    git(pm_work, "checkout", "--detach", head)
    arguments = [python_exe, str(entry), "--repo", str(pm_work), "--source", prepared["source"],
                 "--head", head, "--policy-ref", base, "--backend", "codex"]
    result = run([*arguments, "--target", "master", "--output-dir", str(tmp_path / "ci-valid")])
    assert result.returncode == 0, result.stderr
    proof = json.loads((tmp_path / "ci-valid/changelog-sync.json").read_text())
    assert proof["decision"] == "pass" and proof["head"] == head
    for target in ("support/1.2", ""):
        result = run([*arguments, "--target", target, "--output-dir", str(tmp_path / "ci-target")])
        assert result.returncode != 0
    (pm_work / "untracked.txt").write_text("dirty\n")
    result = run([*arguments, "--target", "master", "--output-dir", str(tmp_path / "ci-dirty")])
    assert result.returncode != 0


def test_sync_preserves_crlf_and_rejects_chmod(python_exe, tmp_path):
    from mdf_core.workspace.pm import require_pm_diff
    from mdf_core.foundation.errors import MDFError
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    path = repo / "CHANGELOG.md"
    original = path.read_bytes().replace(b"\n", b"\r\n")
    path.write_bytes(original)
    commit(repo)
    git(repo, "push", "origin", "master")
    prepared = payload(mdf(python_exe, "sync-changelog", "--repo", str(work)))
    pm = Path(prepared["worktree"])
    changed = (pm / "CHANGELOG.md").read_bytes()
    assert changed.startswith(b"# Changelog\r\n\r\n")
    assert changed.endswith(original[original.index(b"## "):])
    (pm / "CHANGELOG.md").chmod(0o755)
    commit(pm)
    with pytest.raises(MDFError) as exc:
        require_pm_diff(pm, "origin/master", "HEAD", prepared["source"])
    assert exc.value.code == "pm_paths_forbidden"


@pytest.mark.parametrize("dirty", [False, True])
def test_sync_cleanup_preserves_unrelated_trunk_work(python_exe, tmp_path, monkeypatch, dirty):
    from support_pull import Platform, squash_pending
    from mdf_core.lifecycle import pull_finish
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    prepared = payload(mdf(python_exe, "sync-changelog", "--repo", str(work)))
    pm = Path(prepared["worktree"])
    (repo / "local-only.txt").write_text("无关工作\n")
    if not dirty:
        commit(repo)
    original = git(repo, "rev-parse", "HEAD").stdout
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    monkeypatch.setattr(pull_finish, "origin", lambda *_: {})
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    squash_pending(pm)
    payload(mdf(python_exe, "pr", "--repo", str(pm)))
    platform.merge(1, tmp_path)
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(pm)))
    git(work, "worktree", "remove", str(pm))
    payload(mdf(python_exe, "sync-changelog", "--repo", str(work), "--complete"))
    assert git(repo, "rev-parse", "HEAD").stdout == original
    assert (repo / "local-only.txt").read_text() == "无关工作\n"


@pytest.mark.parametrize("crlf", [False, True])
def test_synced_archive_links_use_published_tree(python_exe, tmp_path, crlf):
    from mdf_core.inspection.validate_links import collect_local_link_findings
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    (work / "support-only.txt").write_text("维护线文件\n")
    commit(work)
    from mdf_core.workspace.squash import record_analysis
    record_analysis(work, "hotfix/1.2.1", git(work, "rev-parse", "HEAD").stdout.strip(), reason="保留已验收历史")
    synced = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    payload(mdf(python_exe, "catch-up", "--repo", str(work), "--complete", "--reviewed-head", synced["head"],
                "--summary", "验收维护线文件"))
    change["body"] += "\n[维护线说明](../../support-only.txt)\n"
    consolidate_hotfix(python_exe, work, change)
    root = work / "changes/1.2.1/CHANGE.md"
    findings = []
    collect_local_link_findings(work, root, findings)
    assert not findings
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    if crlf:
        (repo / ".gitattributes").write_text("*.md text eol=crlf\n")
        commit(repo)
        git(repo, "push", "origin", "master")
    prepared = payload(mdf(python_exe, "sync-changelog", "--repo", str(work)))
    pm = Path(prepared["worktree"])
    findings = []
    collect_local_link_findings(pm, pm / "changes/1.2.1/CHANGE.md", findings)
    assert not findings
    payload(mdf(python_exe, "doctor", "--repo", str(pm)))
    # 未发布的改写不能借用 tag 的历史链接豁免。
    path = pm / "changes/1.2.1/CHANGE.md"
    path.write_text(path.read_text() + "\n[缺失](../../not-published.txt)\n")
    findings = []
    collect_local_link_findings(pm, path, findings)
    assert any(f.code == "link.broken" for f in findings)


def test_support_baseline_does_not_follow_parallel_trunk_release(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True, version="1.2.2")
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    path = repo / "CHANGELOG.md"
    path.write_text(path.read_text().replace("# Changelog", "# Changelog\n\n## [1.2.1]\n\n### Fixed\n\n- 主线修复。"))
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace('latest_release: "1.2.0"', 'latest_release: "1.2.1"'))
    commit(repo)
    git(repo, "tag", "-a", "v1.2.1", "-m", "主线独立发布")
    git(repo, "push", "origin", "master", "--tags")
    prepared = payload(mdf(python_exe, "sync-changelog", "--repo", str(work)))
    pm = Path(prepared["worktree"])
    assert 'previous_version: "1.2.0"' in (pm / "changes/1.2.2/CHANGE.md").read_text()
    from mdf_core.inspection.validate_release import validate_release_history
    from mdf_core.foundation.paths import load_manifest
    findings = []
    validate_release_history(pm, load_manifest(pm), findings)
    assert not findings
    payload(mdf(python_exe, "doctor", "--repo", str(pm)))


def test_active_sync_finishes_after_trunk_switches_to_local(python_exe, tmp_path, monkeypatch):
    from support_pull import Platform, squash_pending
    from mdf_core.lifecycle import pull_finish
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    prepared = payload(mdf(python_exe, "sync-changelog", "--repo", str(work)))
    pm = Path(prepared["worktree"])
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace("mode: pr", "mode: local").replace("provider: github", "provider: gitlab"))
    commit(repo)
    git(repo, "push", "origin", "master")
    assert payload(mdf(python_exe, "delivery", "route", "--repo", str(work)))["result"]["next"] == "sync-changelog"
    assert error_of(mdf(python_exe, "finish-gitflow", "--repo", str(work)))["error"] == "changelog_sync_required"
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    providers = []
    monkeypatch.setattr(pull_finish, "origin", lambda _repo, provider: providers.append(provider) or {})
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    squash_pending(pm)
    payload(mdf(python_exe, "pr", "--repo", str(pm)))
    platform.merge(1, tmp_path)
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", prepared["source"]))
    git(work, "worktree", "remove", str(pm))
    payload(mdf(python_exe, "sync-changelog", "--repo", str(work), "--complete"))
    assert set(providers) == {"github"}
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))


def test_completed_local_hotfix_stays_complete_after_pr_enabled(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
    commit(repo)
    git(repo, "push", "origin", "master")
    args = ("--repo", str(repo), "--source", "hotfix/1.2.1")
    assert payload(mdf(python_exe, "delivery", "route", *args))["result"]["state"] == "completed"
    payload(mdf(python_exe, "finish-gitflow", *args))
    synced = payload(mdf(python_exe, "sync-changelog", *args))
    assert synced["completed"] and synced["next_intent"] is None
    assert not git(repo, "branch", "--list", "pm/patch-record-1.2.1").stdout.strip()



def test_first_sync_freezes_one_remote_policy_snapshot(python_exe, tmp_path, monkeypatch):
    from mdf_core.workspace import changelog_sync
    from mdf_core.lifecycle.delivery_state import read_json
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    original = changelog_sync.git
    before = git(repo, "rev-parse", "origin/master").stdout.strip()
    fetches = []

    def advance_after_fetch(checkout, *args, **kwargs):
        result = original(checkout, *args, **kwargs)
        if args[0] == "fetch":
            fetches.append(args)
            if len(fetches) == 1:
                path = repo / ".mdf/manifest.yaml"
                path.write_text(path.read_text().replace("mode: pr", "mode: local"))
                commit(repo)
                original(remote, "fetch", str(repo), "refs/heads/master:refs/heads/master")
        return result

    monkeypatch.setattr(changelog_sync, "git", advance_after_fetch)
    payload(mdf(python_exe, "sync-changelog", "--repo", str(work)))
    data = read_json(changelog_sync.state_path(repo, "1.2.1"))
    assert data["settings"]["mode"] == "pr" and data["base"] == before
    assert len(fetches) == 1
