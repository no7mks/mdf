"""受保护 trunk 的 workflow 切换、CI 检查与首次 push 审计。"""
import importlib.util
from types import SimpleNamespace

from mdf_core.foundation.errors import MDFError
from mdf_core.integrations import forge
from mdf_test_support import *  # noqa: F403
from support_github_flow import commit, error_of, has_ref


def _repo(tmp_path):
    repo = copy_fixture(tmp_path)
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() + "closeout:\n  mode: pr\n  provider: github\n")
    init_git(repo)
    git(repo, "branch", "-m", "master")
    git(repo, "branch", "develop")
    remote = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "origin", "master", "develop")
    return repo, remote


def _switch(python_exe, repo, target):
    return mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow", "--trunk", target)


def _audit(python_exe, repo, branch, before, after, *pulls):
    evidence = repo.parent / "switch-evidence.json"
    evidence.write_text(json.dumps({"pull_requests": pulls}))
    return payload(mdf(python_exe, "audit-push", "--repo", str(repo), "--branch", branch,
                       "--before", before, "--after", after, "--evidence-file", str(evidence)))["result"]


def _pull(repo, source, target, number):
    return {"id": number, "url": f"https://forge.invalid/pull/{number}", "state": "merged", "source": source,
            "target": target, "head": git(repo, "rev-parse", "HEAD^2").stdout.strip(),
            "merge_commit": git(repo, "rev-parse", "HEAD").stdout.strip()}


@pytest.mark.parametrize("target", ["master", "main"])
def test_switch_pr_prepares_and_audits_protected_trunk(python_exe, tmp_path, target):
    repo, remote = _repo(tmp_path)
    if target != "master":
        git(repo, "checkout", "-b", target)
        assert error_of(_switch(python_exe, repo, target))["error"] == "workflow_target_not_synced"
        git(repo, "push", "origin", target)
    base = git(repo, "rev-parse", target).stdout.strip()
    prepared = payload(_switch(python_exe, repo, target))
    source, head = prepared["source"], prepared["commit"]
    assert source == "codex/workflow-switch" and prepared["target"] == target and prepared["base"] == base
    assert git(repo, "branch", "--show-current").stdout.strip() == source
    assert git(repo, "rev-parse", target).stdout.strip() == base
    assert git(remote, "rev-parse", target).stdout.strip() == base
    assert not has_ref(remote, f"refs/heads/{source}")
    assert _audit(python_exe, repo, target, base, head)["commits"][0]["reason"] == "direct_trunk_commit"
    if target == "main":
        assert _audit(python_exe, repo, target, "0" * 40, head)["verdict"] == "needs-review"

    runner_path = skill_dir("mdf") / "assets/ci/review.py"
    spec = importlib.util.spec_from_file_location("workflow_switch_ci", runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    args = SimpleNamespace(repo=str(repo), output_dir=str(tmp_path / "ci"), source=source, target=target,
                           head=head, policy_ref=base)
    assert runner.run(args) == 0
    report = json.loads((tmp_path / "ci" / "workflow-switch.json").read_text())
    assert report == {"source": source, "target": target, "head": head, "base": base, "decision": "pass"}
    (repo / "unexpected.txt").write_text("附带改动\n")
    git(repo, "add", "unexpected.txt")
    git(repo, "commit", "--amend", "--no-edit")
    args.head = git(repo, "rev-parse", "HEAD").stdout.strip()
    with pytest.raises(MDFError, match="只含 workflow"):
        runner.run(args)
    git(repo, "reset", "--hard", head)

    git(repo, "checkout", target)
    assert payload(_switch(python_exe, repo, target))["commit"] == head
    git(repo, "merge", "--no-ff", "--no-edit", source)
    proof = _pull(repo, source, target, 1)
    merged = proof["merge_commit"]
    assert _audit(python_exe, repo, target, base, merged)["verdict"] == "needs-review"
    accepted = _audit(python_exe, repo, target, base, merged, proof)
    assert accepted["verdict"] == "pass" and accepted["policy_ref"] == base
    assert accepted["commits"][0]["reason"] == "platform_merge"
    wrong_source = {**proof, "source": "feature/not-a-switch"}
    assert _audit(python_exe, repo, target, base, merged, wrong_source)["verdict"] == "violation"

    git(repo, "checkout", "-b", "support/1.2")
    (repo / "support.txt").write_text("维护线\n")
    commit(repo)
    git(repo, "checkout", target)
    git(repo, "merge", "--no-ff", "--no-edit", "support/1.2")
    support = _pull(repo, "support/1.2", target, 2)
    result = _audit(python_exe, repo, target, base, "HEAD", proof, support)
    assert result["verdict"] == "violation"
    assert [item["reason"] for item in result["commits"]] == ["platform_merge", "support_merge_forbidden"]


def test_switch_pr_checks_origin_develop_even_without_local_branch(python_exe, tmp_path):
    repo, _ = _repo(tmp_path)
    git(repo, "checkout", "develop")
    git(repo, "commit", "--allow-empty", "-m", "test: 远端 develop 未发布")
    git(repo, "push", "origin", "develop")
    git(repo, "checkout", "master")
    git(repo, "branch", "-D", "develop")
    failed = error_of(_switch(python_exe, repo, "master"))
    assert failed["error"] == "develop_history_lost"
    assert failed["details"]["branch"] == "origin/develop"
    assert not has_ref(repo, "refs/heads/codex/workflow-switch")


@pytest.mark.parametrize("old_model", ["gitflow", "github-flow"])
def test_audit_accepts_workflow_backmerge_into_develop(python_exe, tmp_path, old_model):
    repo, _ = _repo(tmp_path)
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() + f"workflow:\n  model: {old_model}\n  trunk: master\n")
    commit(repo)
    git(repo, "branch", "-f", "develop", "HEAD")
    git(repo, "push", "origin", "master", "develop")
    git(repo, "checkout", "-b", "main")
    git(repo, "push", "origin", "main")
    switch = payload(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "gitflow", "--trunk", "main"))
    git(repo, "checkout", "main")
    git(repo, "merge", "--no-ff", "--no-edit", switch["source"])
    merged = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "push", "origin", "main")
    git(repo, "checkout", "develop")
    before = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "merge", "--no-ff", "--no-edit", "main")
    assert _audit(python_exe, repo, "develop", before, "HEAD")["verdict"] == "needs-review"
    evidence = tmp_path / "backmerge-evidence.json"
    evidence.write_text(json.dumps({"sources": {"main": merged}}))
    result = payload(mdf(python_exe, "audit-push", "--repo", str(repo), "--branch", "develop",
                         "--before", before, "--after", "HEAD", "--evidence-file", str(evidence)))["result"]
    assert result["verdict"] == "pass"
    assert result["commits"][0]["reason"] == "trunk_backmerge"


def test_first_audit_collects_forge_evidence_for_new_trunk(python_exe, tmp_path, monkeypatch):
    repo, _ = _repo(tmp_path)
    git(repo, "checkout", "-b", "main")
    git(repo, "push", "origin", "main")
    prepared = payload(_switch(python_exe, repo, "main"))
    git(repo, "checkout", "main")
    git(repo, "merge", "--no-ff", "--no-edit", prepared["source"])
    proof = _pull(repo, prepared["source"], "main", 1)
    raw = {"number": 1, "html_url": proof["url"], "merged": True, "merge_commit_sha": proof["merge_commit"],
           "head": {"sha": proof["head"], "ref": proof["source"], "repo": {"full_name": "test/project"}},
           "base": {"ref": "main", "repo": {"full_name": "test/project"}}}

    def api(self, endpoint):
        if endpoint == self.endpoint + "/1":
            return raw
        assert "state=closed&base=main&" in endpoint
        return [raw]

    monkeypatch.setattr(forge, "origin", lambda repo, provider: {"provider": provider, "project": "test/project"})
    monkeypatch.setattr(forge.Forge, "api", api)
    git(repo, "remote", "set-url", "origin", str(tmp_path / "unavailable.git"))
    result = payload(mdf(python_exe, "audit-push", "--repo", str(repo), "--branch", "main",
                         "--before", prepared["base"], "--after", "HEAD", "--collect-evidence"))["result"]
    assert result["verdict"] == "pass"
    assert result["commits"][0]["reason"] == "platform_merge"
