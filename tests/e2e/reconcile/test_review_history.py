"""多个历史版本保留同一 child 时不重复发布，也不丢失显式新增成果。"""
from pathlib import Path

import pytest

from mdf_test_support import git, payload
from support_reconcile import repository, change, spec_file, apply, call, proof
import json
from test_history import child
from mdf_core.foundation.yamlutil import read_frontmatter


@pytest.mark.parametrize("changed_child", [False, True])
def test_multiple_tags_do_not_archive_the_same_child_again(python_exe, tmp_path, changed_child):
    repo = repository(tmp_path)
    path = repo / "changes/unreleased/alpha/CHANGE.md"
    path.parent.mkdir(parents=True)
    path.write_text(child(["A"]))
    first = change(repo, "first")
    git(repo, "tag", "v1.3.0")
    if changed_child:
        path.write_text(child(["A", "B"]))
    second = change(repo, "second")
    git(repo, "tag", "v1.4.0")
    # 当前历史基线 1.2.0 的记录不参与本次两个后续版本。
    info = payload(call(python_exe, repo, "prepare", "--version", "1.3.0"))["result"]
    work = Path(info["worktree"])
    payload(apply(python_exe, work, spec_file(tmp_path, work, first)))
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(proof(work)))
    payload(call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence)))
    work = Path(payload(call(python_exe, repo, "prepare", "--version", "1.4.0"))["result"]["worktree"])
    result = apply(python_exe, work, spec_file(tmp_path, work, second), "1.4.0")
    if changed_child:
        assert result.returncode != 0, result.stdout
        assert not (work / "changes/1.4.0").exists()
        assert not git(work, "status", "--porcelain").stdout
    else:
        payload(result)
        assert not (work / "changes/1.4.0/alpha").exists()
        assert (work / "changes/1.4.0/external-work/CHANGE.md").exists()
        assert "A" not in read_frontmatter(work / "changes/1.4.0/CHANGE.md")[0]["release_notes"]["Changed"]


def test_explicit_new_change_is_kept_alongside_historical_snapshot(python_exe, tmp_path):
    repo = repository(tmp_path)
    path = repo / "changes/unreleased/alpha/CHANGE.md"
    path.parent.mkdir(parents=True)
    path.write_text(child(["A"]))
    head = change(repo)
    git(repo, "tag", "v1.3.0")
    work = Path(payload(call(python_exe, repo, "prepare", "--version", "1.3.0"))["result"]["worktree"])
    payload(apply(python_exe, work, spec_file(tmp_path, work, head)))
    assert (work / "changes/1.3.0/alpha/CHANGE.md").exists()
    assert (work / "changes/1.3.0/external-work/CHANGE.md").exists()
