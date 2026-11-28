"""历史快照、纯外部区间补账与未发布净增量。"""
import json

import pytest

from mdf_test_support import git, payload
from support_delivery import commit
from support_github_flow import error_of
from support_reconcile import repository, change, prepare, spec_file, apply, call
from mdf_core.reconciliation.history import document
from mdf_core.foundation.yamlutil import read_frontmatter


def child(notes):
    return document({"change_kind": "feature", "source_branch": "feature/alpha", "proposals": [], "fixed": [],
                     "closed": [], "deferred": [], "adrs": [], "breaking": False,
                     "release_notes": {"Changed": notes}, "evidence": {"tests": [], "commands": [], "artifacts": []}},
                    "\n# Change\n\n## 结果\n\n参见 release_notes。\n\n## 已更新的当前文档\n\n无。\n\n## 已知偏差\n\n无。\n")


@pytest.mark.parametrize("github", [True, False])
def test_external_release_without_change_and_idempotence(python_exe, tmp_path, github):
    repo = repository(tmp_path, github=github)
    released = change(repo)
    git(repo, "tag", "v1.3.0")
    change(repo, "future")
    work = prepare(python_exe, repo)
    spec = spec_file(tmp_path, work, released)
    result = payload(apply(python_exe, work, spec))["result"]
    assert result["recorded"] and not result["publication_completed"]
    root = work / "changes/1.3.0/CHANGE.md"
    meta, _ = read_frontmatter(root)
    assert meta["record_mode"] == "post_hoc" and meta["release_commit"] == released
    assert (work / "changes/1.3.0/external-work/CHANGE.md").is_file()
    assert not (work / "changes/1.3.0/delivery.json").exists()
    assert not (work / "changes/1.3.0/objectives.md").exists()
    assert (work / "src/future.py").exists()
    reconciliation = (work / "changes/1.3.0/release-reconciliation.md").read_text()
    assert "当前工作区的审阅不作为历史发布快照的验收" in reconciliation
    assert json.loads(spec.read_text())["fact"]["commit"] in reconciliation
    before = git(work, "rev-parse", "HEAD").stdout
    assert payload(apply(python_exe, work, spec))["result"]["already_recorded"]
    assert git(work, "rev-parse", "HEAD").stdout == before
    assert git(repo, "cat-file", "-t", "v1.3.0").stdout.strip() == "commit"


@pytest.mark.parametrize("current", ["same", "added", "ambiguous"])
def test_snapshot_isolation_and_unreleased_remainder(python_exe, tmp_path, current):
    repo = repository(tmp_path)
    path = repo / "changes/unreleased/alpha/CHANGE.md"
    path.parent.mkdir(parents=True)
    historical = child(["A"])
    path.write_text(historical)
    released = change(repo)
    git(repo, "tag", "v1.3.0")
    if current != "same":
        path.write_text(child(["A", "B"]) if current == "added" else child(["重新解释 A 与 B"]))
        commit(repo)
    work = prepare(python_exe, repo)
    spec = spec_file(tmp_path, work, released)
    before = git(work, "rev-parse", "HEAD").stdout
    result = apply(python_exe, work, spec)
    if current == "ambiguous":
        assert error_of(result)["error"] == "ambiguous_release"
        assert not (work / "changes/1.3.0").exists()
        assert git(work, "rev-parse", "HEAD").stdout == before
        assert not git(work, "status", "--porcelain").stdout
        return
    payload(result)
    assert (work / "changes/1.3.0/alpha/CHANGE.md").read_text() == historical
    remainder = work / "changes/unreleased/alpha/CHANGE.md"
    if current == "same":
        assert not remainder.parent.exists()
    else:
        assert read_frontmatter(remainder)[0]["release_notes"] == {"Changed": ["B"]}
        from mdf_core.lifecycle.closeout_render import aggregate_release_changes
        assert aggregate_release_changes(work, ["alpha"])[0]["Changed"] == ["B"]


def test_missing_interval_evidence_preserves_worktree(python_exe, tmp_path):
    repo = repository(tmp_path)
    released = change(repo)
    git(repo, "tag", "v1.3.0")
    work = prepare(python_exe, repo)
    spec = spec_file(tmp_path, work, released, [git(repo, "rev-parse", "v1.2.0").stdout.strip()])
    assert error_of(apply(python_exe, work, spec))["error"] == "invalid_reconciliation"
    assert not git(work, "status", "--porcelain").stdout


def test_version_tag_does_not_silently_replace_explicit_commit(python_exe, tmp_path):
    repo = repository(tmp_path)
    change(repo)
    git(repo, "tag", "v1.3.0")
    later = change(repo, "later")
    failed = call(python_exe, repo, "inspect", "--version", "1.3.0", "--commit", later)
    assert error_of(failed)["error"] == "tag_conflict"


def test_snapshot_preserves_binary_crlf_and_executable_evidence(python_exe, tmp_path):
    repo = repository(tmp_path)
    folder = repo / "changes/unreleased/alpha"
    folder.mkdir(parents=True)
    (folder / "CHANGE.md").write_bytes(child(["A"]).replace("\n", "\r\n").encode())
    (folder / "evidence.bin").write_bytes(bytes(range(256)))
    (folder / "check.sh").write_bytes(b"#!/bin/sh\r\nexit 0\r\n")
    (folder / "check.sh").chmod(0o755)
    released = change(repo)
    git(repo, "tag", "v1.3.0")
    work = prepare(python_exe, repo)
    payload(apply(python_exe, work, spec_file(tmp_path, work, released)))
    before = git(repo, "rev-parse", f"{released}:changes/unreleased/alpha").stdout.strip()
    after = git(work, "rev-parse", "HEAD:changes/1.3.0/alpha").stdout.strip()
    assert before == after
    assert not (work / "changes/unreleased/alpha").exists()


def test_evolved_object_blocks_before_any_archive(python_exe, tmp_path):
    repo = repository(tmp_path)
    path = repo / "changes/unreleased/alpha/CHANGE.md"
    path.parent.mkdir(parents=True)
    path.write_text(child(["A"]).replace("proposals: []", 'proposals: ["prp-0001"]'))
    released = change(repo)
    git(repo, "tag", "v1.3.0")
    proposal = repo / "docs/proposals/prp-0001-service-health.md"
    proposal.write_text(proposal.read_text() + "\n新的未发布目标。\n")
    commit(repo)
    work = prepare(python_exe, repo)
    spec = spec_file(tmp_path, work, released)
    assert error_of(apply(python_exe, work, spec))["error"] == "ambiguous_release"
    assert not (work / "changes/1.3.0").exists()
    assert not git(work, "status", "--porcelain").stdout
