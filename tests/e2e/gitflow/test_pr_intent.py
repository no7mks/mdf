"""pr 与 close-out 的独立完成边界。"""
from pathlib import Path

import pytest

from mdf_test_support import git, mdf, payload
from support_pull import prepare
from support_delivery import start_repo, commit


@pytest.mark.parametrize("kind", ["feature", "release", "hotfix", "adhoc"])
def test_pr_merge_returns_before_publication_or_cleanup(python_exe, tmp_path, monkeypatch, kind):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, kind)
    from mdf_core.lifecycle.delivery_state import locate
    text = (locate(work)[0] / "objectives.md").read_text()
    assert ("- [x] pr" if kind == "adhoc" else "- [ ] pr") in text
    assert "- [ ] close-out" not in text
    assert "- close-out（pr merged 后必须续办；不设 checkbox）" in text
    if kind == "adhoc":
        status = payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]
        assert status["next_step"] == "pr" and not status["completed"]
    before = git(remote, "show-ref").stdout
    rejected = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    assert rejected.returncode != 0 and "pr_not_merged" in rejected.stderr
    assert platform.pulls == [] and git(remote, "show-ref").stdout == before
    first = payload(mdf(python_exe, "pr", "--repo", str(work)))
    assert first["operation"] == "pr" and not first["completed"]
    waiting = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    assert waiting.returncode != 0 and "pr_not_merged" in waiting.stderr
    if kind == "adhoc":
        status = payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]
        assert status["next_step"] == "pr"
    merged = platform.merge(1, tmp_path)
    before = git(remote, "show-ref").stdout
    for _ in range(2):
        result = payload(mdf(python_exe, "pr", "--repo", str(repo), "--source", first["source"]))
        assert result["completed"] and result["status"] == "merged"
        assert result["merge_commit"] == merged and result["next_intent"] == "close-out"
        assert git(remote, "show-ref").stdout == before
        assert git(work, "branch", "--show-current").stdout.strip() == first["source"]
        assert not git(remote, "for-each-ref", "refs/tags/v1.2.1").stdout
    if kind == "adhoc":
        status = payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]
        assert status["next_step"] == "close-out" and not status["completed"]
    finished = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert finished["completed"] and finished["remote_deleted"]
    assert not git(work, "branch", "--show-current").stdout.strip()
    if kind == "adhoc":
        import json
        from mdf_core.lifecycle.publish import state_path
        status = payload(mdf(python_exe, "adhoc-status", "--repo", str(work), "--slug", "service-health"))["result"]
        assert status["completed"] and status["next_step"] is None
        path = state_path(repo, first["source"])
        state = json.loads(path.read_text())
        state["completed"] = False
        path.write_text(json.dumps(state))
        interrupted = mdf(python_exe, "adhoc-status", "--repo", str(work), "--slug", "service-health")
        assert interrupted.returncode != 0 and "adhoc_not_finished" in interrupted.stderr


@pytest.mark.parametrize("mode", ["local", "pr"])
@pytest.mark.parametrize("kind", ["manual", "adhoc"])
def test_start_uses_mode_specific_tail_and_pr_rejects_local(python_exe, tmp_path, mode, kind):
    repo, _ = start_repo(tmp_path)
    if mode == "pr":
        manifest = repo / ".mdf/manifest.yaml"
        manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
        commit(repo)
        git(repo, "branch", "-f", "develop", "master")
    args = ["--kind", "adhoc", "--work", "更新文档"]
    if kind == "manual":
        from conftest import skill_dir
        obj = tmp_path / "manual.md"
        text = (skill_dir("mdf") / "assets/templates/manual-objectives.md").read_text()
        for marker in ("GOALS_AND_NON_GOALS", "DELIVERY_CONSTRAINTS", "ACCEPTANCE_CRITERIA"):
            text = text.replace("{{MDF_" + marker + "}}", "本次仅更新文档，保留现有行为。")
        obj.write_text(text)
        args = ["--kind", "feature", "--manual", "--objectives-file", str(obj)]
    result = payload(mdf(python_exe, "start", "--repo", str(repo), "--name", "test-tail", *args))
    work = Path(result["worktree"])
    text = (work / "changes/unreleased/test-tail/objectives.md").read_text()
    if mode == "pr":
        assert "- [ ] pr" in text and "- [ ] close-out" not in text
        assert text.index("- [ ] pr") < text.index("- close-out（pr merged 后必须续办；不设 checkbox）")
    else:
        assert "- [ ] close-out" in text and "- [ ] pr" not in text
        result = mdf(python_exe, "pr", "--repo", str(work))
        assert result.returncode != 0 and "invalid_closeout" in result.stderr
