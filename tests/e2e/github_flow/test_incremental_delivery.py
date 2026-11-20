"""merge/pr 内部循环增量验收，并按交付类型重收敛材料。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import start_repo, commit, write_change
from support_github_flow import github_flow_repo, error_of
from support_pull import Platform, squash_pending


@pytest.mark.parametrize("github", [False, True])
def test_target_advancement_loops_inside_pr_without_resetting_baseline(python_exe, tmp_path, monkeypatch, github):
    repo, remote = github_flow_repo(tmp_path, origin=True, pr=True) if github else start_repo(tmp_path)
    if not github:
        manifest = repo / ".mdf/manifest.yaml"
        manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
        commit(repo)
        git(repo, "branch", "-f", "develop", "master")
        git(repo, "push", "origin", "--all")
    target = "master" if github else "develop"
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    from mdf_core.lifecycle import pull_finish
    identity = {"provider": "github", "host": "forge.invalid", "project": "team/project", "origin": str(remote)}
    monkeypatch.setattr(pull_finish, "origin", lambda *_: identity)
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature", "--proposal", PRP_ID,
                       "--roster", "solo", "--objectives-file", str(write_work_objectives(tmp_path))))
    work = Path(data["worktree"])
    root = write_change(work, data["branch"], "service-health")
    change = root / "CHANGE.md"
    change.write_text(change.read_text().replace("proposals: []", "proposals: [prp-0001]").replace("change_kind: fix", "change_kind: feature"))
    (root / "objectives.md").write_text((root / "objectives.md").read_text().replace("[ ]", "[x]"))
    payload(mdf(python_exe, "verify", "--scope", "branch", "--repo", str(work)))
    commit(work)
    squash_pending(work)
    payload(mdf(python_exe, "consolidate", "--repo", str(work)))
    peer = tmp_path / "peer"
    git(tmp_path, "clone", "--branch", target, str(remote), str(peer))
    accepted = []
    for index in range(2):
        (peer / "src/target.py").write_text(f"value = {index}\n")
        commit(peer)
        git(peer, "push")
        failed = error_of(mdf(python_exe, "pr", "--repo", str(work)))
        assert failed["error"] == "integration_required"
        pending = payload(mdf(python_exe, "incremental-integration", "--repo", str(work)))
        assert pending["incr_consolidate"]
        assert pending["plan"]["review"]["action"] == "focused"
        assert pending["plan"]["verify"]["action"] == "smart"
        if accepted:
            assert pending["plan"]["base"] == accepted[-1]
        early = mdf(python_exe, "incremental-integration", "--repo", str(work), "--complete",
                    "--reviewed-head", pending["head"], "--summary", "已审查")
        assert error_of(early)["error"] == "consolidation_required"
        report = root / "incremental-integration-verification-report.json"
        payload(mdf(python_exe, "verify", "--scope", "smart", "--repo", str(work), "--paths", "src/target.py",
                    "--report-file", str(report)))
        commit(work)
        payload(mdf(python_exe, "consolidate", "--repo", str(work), "--incremental"))
        head = git(work, "rev-parse", "HEAD").stdout.strip()
        payload(mdf(python_exe, "incremental-integration", "--repo", str(work), "--complete",
                    "--reviewed-head", head, "--summary", "incr-cr、verify smart、incr-fa 和 incr-consolidate 通过"))
        accepted.append(head)
        objectives = (root / "objectives.md").read_text()
        assert "- [x] verify branch" in objectives and "- [x] fact audit" in objectives
        assert "- [x] consolidate" in objectives
    squash_pending(work)
    payload(mdf(python_exe, "pr", "--repo", str(work)))
    platform.merge(1, tmp_path)
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
