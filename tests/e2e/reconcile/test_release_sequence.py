"""真实 Git 发布验证：三条发布顺序、固定 tag 和 PR 后续办。"""
import json

import pytest

from mdf_test_support import git, payload
from support_github_flow import has_ref
from support_reconcile import repository, change, prepare, spec_file, apply, call, proof
from test_channels import platform_for


@pytest.mark.parametrize("flow", ["github", "gitflow", "gitflow_hotfix", "support"])
@pytest.mark.parametrize("pr", [False, True])
def test_release_sequences_preserve_fixed_publication(python_exe, tmp_path, monkeypatch, flow, pr):
    repo = repository(tmp_path, github=not flow.startswith("gitflow"), pr=pr, remote=True)
    remote = tmp_path / "origin.git"
    platform = platform_for(repo, tmp_path, monkeypatch) if pr else None
    hotfix = flow in {"support", "gitflow_hotfix"}
    version = "1.2.1" if hotfix else "1.3.0"
    source = ("hotfix/" if hotfix else "release/") + version
    target = "support/1.2" if flow == "support" else "master"
    if flow == "support":
        git(repo, "branch", target, "v1.2.0")
        git(repo, "push", "origin", target)
    git(repo, "switch", "-c", source, target)
    head = change(repo)
    work = prepare(python_exe, repo, version, *(["--support", "1.2"] if flow == "support" else []))
    spec = spec_file(tmp_path, work, head)
    if hotfix:
        data = json.loads(spec.read_text())
        data["changes"][0]["release_notes"] = {"Fixed": ["修复维护线缺陷"]}
        spec.write_text(json.dumps(data))
    payload(apply(python_exe, work, spec, version))
    if flow == "support":
        assert not any(p.is_dir() for p in (work / "changes" / version).iterdir())
    candidate = git(work, "rev-parse", "HEAD").stdout.strip()
    if pr:
        from mdf_core.workspace.squash import record_analysis
        record_analysis(work, source, candidate, reason="验收夹具保留已定型提交")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(proof(work)))
    events = []
    from mdf_core.reconciliation import finish
    original = finish.tag_release

    def record_tag(repo, state, version, **kwargs):
        events.append({"source_merged": has_ref(remote, f"refs/heads/{target}") and
                       git(remote, "rev-list", f"refs/heads/{target}").stdout.split().count(candidate) > 0,
                       "candidate": state.get("release_head") or state.get("merge_commit")})
        return original(repo, state, version, **kwargs)

    monkeypatch.setattr(finish, "tag_release", record_tag)
    result = payload(call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence)))["result"]
    if pr:
        assert not result["completed"]
        if flow == "github":
            assert has_ref(remote, f"refs/tags/v{version}")
        elif flow.startswith("gitflow"):
            assert not has_ref(remote, f"refs/tags/v{version}")
        else:
            assert platform.pulls[0]["source"].startswith("pm/patch-record-")
            assert has_ref(remote, f"refs/tags/v{version}")
        platform.merge(1, tmp_path)
        result = payload(call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence)))["result"]
    assert result["completed"]
    assert events[0]["source_merged"] is (flow != "github")
    tag_head = git(remote, "rev-parse", f"v{version}^{{commit}}").stdout.strip()
    assert tag_head == (candidate if flow == "github" else result["merge_commit"])
    assert git(remote, "cat-file", "-t", f"v{version}").stdout.strip() == "tag"
    assert not has_ref(remote, f"refs/heads/{source}")
    if flow.startswith("gitflow"):
        git(repo, "merge-base", "--is-ancestor", result["merge_commit"], "develop")
    if flow == "support" and pr:
        assert "1.2.0" in git(repo, "show", "master:.mdf/manifest.yaml").stdout
        assert "1.2.1" in git(repo, "show", "master:CHANGELOG.md").stdout
