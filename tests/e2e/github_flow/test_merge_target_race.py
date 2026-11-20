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
    assert git(repo, "rev-parse", "develop").stdout.strip() == advanced[0]
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


@pytest.mark.parametrize("kind", ["feature", "adhoc"])
@pytest.mark.parametrize("changed", ["source", "target"])
def test_local_merge_freezes_accepted_refs_before_merge(python_exe, tmp_path, monkeypatch, kind, changed):
    from mdf_core.workspace import gitflow
    repo, work, source = prepared_local_merge(python_exe, tmp_path, kind)
    before = git(repo, "rev-parse", "develop").stdout.strip()
    original = gitflow._merge
    advanced = []

    def race(merge_repo, incoming, target, *args):
        if not advanced:
            at = work if changed == "source" else repo
            if changed == "target":
                git(repo, "checkout", "develop")
            (at / "src/concurrent.py").write_text("concurrent = True\n")
            commit(at)
            advanced.append(git(at, "rev-parse", "HEAD").stdout.strip())
            if changed == "target":
                git(repo, "checkout", "master")
        return original(merge_repo, incoming, target, *args)

    monkeypatch.setattr(gitflow, "_merge", race)
    assert error_of(mdf(python_exe, "merge", "--repo", str(work)))["error"] == "integration_required"
    expected = before if changed == "source" else advanced[0]
    assert git(repo, "rev-parse", "develop").stdout.strip() == expected
    assert git(repo, "for-each-ref", f"refs/heads/{source}").stdout
    assert not git(repo, "for-each-ref", "refs/tags/").stdout.strip()


def prepared_local_merge(python_exe, tmp_path, kind):
    from mdf_core.lifecycle.manual import STEPS
    repo, _ = start_repo(tmp_path)
    extra = ["--work", "核对合并竞态"]
    if kind == "feature":
        obj = tmp_path / "manual.md"
        obj.write_text("# 目标\n\n" + "".join(f"- [{'x' if name == 'start' else ' '}] {name}\n" for name in STEPS))
        extra = ["--manual", "--objectives-file", str(obj)]
    started = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", kind, "--name", "race", *extra))
    work = Path(started["worktree"])
    root = write_change(work, started["branch"], "race")
    if kind == "feature":
        change = root / "CHANGE.md"
        change.write_text(change.read_text().replace("change_kind: fix", "change_kind: feature"))
    obj = root / "objectives.md"
    obj.write_text(obj.read_text().replace("[ ]", "[x]").replace("[x] consolidate", "[ ] consolidate"))
    commit(work)
    payload(mdf(python_exe, "consolidate", "--repo", str(work)))
    return repo, work, started["branch"]


@pytest.mark.parametrize("changed", ["source", "target", None])
@pytest.mark.parametrize("hook_name", ["pre-commit", "prepare-commit-msg", "commit-msg"])
def test_original_commit_hooks_cannot_bypass_merge_snapshot(python_exe, tmp_path, changed, hook_name):
    import shlex
    repo, work, source = prepared_local_merge(python_exe, tmp_path, "adhoc")
    before = git(repo, "rev-parse", "develop").stdout.strip()
    tree = git(repo, "rev-parse", "develop^{tree}").stdout.strip()
    concurrent = git(repo, "commit-tree", tree, "-p", before, "-m", "test: concurrent").stdout.strip()
    hooks = repo / ".git/custom-hooks"
    hooks.mkdir()
    git(repo, "config", "core.hooksPath", str(hooks))
    trace = repo / ".git/hook-trace"
    hook = hooks / hook_name
    body = "#!/bin/sh\nprintf '" + hook_name + "\\n' >> " + shlex.quote(str(trace)) + "\n"
    if changed:
        ref = f"refs/heads/{source}" if changed == "source" else "refs/heads/develop"
        body += f"git update-ref {shlex.quote(ref)} {concurrent}\n"
    hook.write_text(body)
    hook.chmod(0o755)
    result = mdf(python_exe, "merge", "--repo", str(work))
    assert trace.read_text() == hook_name + "\n"
    if changed:
        assert error_of(result)["error"] == "integration_required"
        assert git(repo, "rev-parse", "develop").stdout.strip() == (concurrent if changed == "target" else before)
    else:
        merged = payload(result)["merge_commit"]
        assert git(repo, "show", "-s", "--format=%P", merged).stdout.split() == [before, git(work, "rev-parse", "HEAD").stdout.strip()]


@pytest.mark.parametrize("kind", ["feature", "adhoc"])
def test_postcommit_advance_records_actual_merge_not_latest_target(python_exe, tmp_path, kind):
    repo, work, source = prepared_local_merge(python_exe, tmp_path, kind)
    expected_source = git(work, "rev-parse", "HEAD").stdout.strip()
    expected_target = git(repo, "rev-parse", "develop").stdout.strip()
    hook = repo / ".git/hooks/post-commit"
    hook.parent.mkdir(exist_ok=True)
    git(repo, "config", "core.hooksPath", str(hook.parent))
    hook.write_text("#!/bin/sh\n"
                    "before=$(git rev-parse HEAD)\n"
                    "after=$(git commit-tree HEAD^{tree} -p \"$before\" -m 'test: 后续提交')\n"
                    "git update-ref HEAD \"$after\" \"$before\"\n")
    hook.chmod(0o755)
    result = payload(mdf(python_exe, "merge", "--repo", str(work)))
    merged = result["merge_commit"]
    assert merged != git(repo, "rev-parse", "develop").stdout.strip()
    assert merged == git(repo, "rev-parse", "develop^").stdout.strip()
    assert git(repo, "show", "-s", "--format=%P", merged).stdout.split() == [expected_target, expected_source]
    record = json.loads((repo / ".git/mdf/merge" / source / "unversioned.json").read_text())
    assert record["merge_commit"] == merged and record["head"] == expected_source
