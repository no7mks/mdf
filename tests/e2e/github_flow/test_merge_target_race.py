"""实际合入时再次核对 target，避免检查后的并发前进绕过增量验收。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import start_repo, commit, write_change
from support_github_flow import error_of
from support_pull import prepare


def test_local_target_race_returns_to_incremental_integration(python_exe, tmp_path, monkeypatch):
    from mdf_core.lifecycle.manual import STEPS
    from mdf_core.workspace import gitflow
    repo, _ = start_repo(tmp_path)
    obj = tmp_path / "manual.md"
    obj.write_text("# 目标\n\n" + "".join(f"- [{'x' if name == 'start' else ' '}] {name}\n" for name in STEPS))
    started = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature", "--manual", "--name", "race",
                          "--objectives-file", str(obj)))
    work = Path(started["worktree"])
    root = write_change(work, started["branch"], "race")
    change = root / "CHANGE.md"
    change.write_text(change.read_text().replace("change_kind: fix", "change_kind: feature"))
    objectives = root / "objectives.md"
    objectives.write_text(objectives.read_text().replace("[ ]", "[x]").replace("[x] consolidate", "[ ] consolidate"))
    commit(work)
    payload(mdf(python_exe, "consolidate", "--repo", str(work)))
    original = gitflow._merge
    advanced = []

    def race(merge_repo, source, target, *args):
        if target == "develop" and not advanced:
            git(repo, "checkout", "develop")
            (repo / "src/concurrent.py").write_text("concurrent = True\n")
            commit(repo)
            advanced.append(git(repo, "rev-parse", "HEAD").stdout.strip())
            git(repo, "checkout", "master")
        return original(merge_repo, source, target, *args)

    monkeypatch.setattr(gitflow, "_merge", race)
    assert error_of(mdf(python_exe, "merge", "--repo", str(work)))["error"] == "integration_required"
    pending = payload(mdf(python_exe, "incremental-integration", "--repo", str(work)))
    assert not pending["completed"] and pending["plan"]["verify"]["action"] == "smart"
    payload(mdf(python_exe, "verify", "--repo", str(work), "--scope", "smart", "--paths", "src/concurrent.py",
                "--report-file", str(root / "incremental-integration-verification-report.json")))
    commit(work)
    payload(mdf(python_exe, "consolidate", "--repo", str(work), "--incremental"))
    payload(mdf(python_exe, "incremental-integration", "--repo", str(work), "--complete",
                "--reviewed-head", git(work, "rev-parse", "HEAD").stdout.strip(), "--summary", "本轮增量验收通过"))
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    git(repo, "merge-base", "--is-ancestor", advanced[0], "develop")


def test_pr_target_race_cannot_publish_or_clean_up(python_exe, tmp_path, monkeypatch):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, "release")
    payload(mdf(python_exe, "pr", "--repo", str(work)))
    peer = tmp_path / "peer"
    git(tmp_path, "clone", "--branch", "master", str(remote), str(peer))
    (peer / "src/concurrent.py").write_text("concurrent = True\n")
    commit(peer)
    git(peer, "push")
    platform.merge(1, tmp_path)
    assert error_of(mdf(python_exe, "pr", "--repo", str(work)))["error"] == "target_not_integrated"
    assert error_of(mdf(python_exe, "publish", "--repo", str(work)))["error"] == "target_not_integrated"
    assert not git(remote, "for-each-ref", "refs/tags/v1.2.1").stdout
    assert git(remote, "for-each-ref", "refs/heads/release/1.2.1").stdout
