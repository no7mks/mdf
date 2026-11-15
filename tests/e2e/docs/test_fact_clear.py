"""只有完整语义审阅才能建立 fact-audit clear commit。"""
import json
from pathlib import Path

import pytest

from mdf_test_support import git, mdf, payload
from mdf_core.workspace import clear_commits
from test_commit_fact_audit import commit, repository
from test_fact_inputs import report_files


def audit(python_exe, repo, base, *extra):
    return payload(mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", "branch", "--base", base, *extra))


def record(python_exe, tmp_path, repo, ctx):
    context_file, report_file = report_files(tmp_path, ctx)
    result = payload(mdf(python_exe, "fact-audit-report-check", "--repo", str(repo),
                         "--context-file", context_file, "--report-file", report_file))["result"]
    assert result["decision"] == "pass"
    return result


def update_facts(repo):
    for doc in (repo / "docs").rglob("*.md"):
        text = doc.read_text()
        if "path: src/service.py" in text:
            doc.write_text(text + "\n本轮更新内部常量。\n")


def test_fact_clear_reuses_same_tree_and_loads_on_dirty(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    git(repo, "branch", "develop", base)
    (repo / "src/service.py").write_text("VALUE = 2\n")
    update_facts(repo)
    head = commit(repo)
    first = audit(python_exe, repo, base)
    assert not first["skip_audit"]
    assert record(python_exe, tmp_path, repo, first["result"])["recorded"]
    git(repo, "commit", "--allow-empty", "-m", "test: 仅改历史")
    assert audit(python_exe, repo, base)["skip_audit"]
    assert not audit(python_exe, repo, base, "--force")["skip_audit"]
    (repo / "src/new.py").write_text("VALUE = 3\n")
    dirty = audit(python_exe, repo, base)
    assert dirty["clear_commit"] == dirty["result"]["against"] == head
    assert not dirty["skip_audit"] and dirty["result"]["paths"] == ["src/new.py"]
    assert not record(python_exe, tmp_path, repo, dirty["result"]).get("recorded")
    assert clear_commits.load(repo, "fact_audit") == head


def test_quick_and_explicit_against_do_not_move_branch_clear(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    assert not audit(python_exe, repo, base, "--quick")["skip_audit"]
    explicit = payload(mdf(python_exe, "fact-audit", "--repo", str(repo), "--against", base))
    assert not record(python_exe, tmp_path, repo, explicit["result"]).get("recorded")
    assert clear_commits.load(repo, "fact_audit") is None


def test_fact_audit_cannot_seed_clear_from_local_base(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    git(repo, "branch", "develop", base)
    (repo / "src/new.py").write_text("VALUE = 1\n")
    head = commit(repo)
    narrow = audit(python_exe, repo, head)["result"]
    assert not record(python_exe, tmp_path, repo, narrow).get("recorded")
    assert audit(python_exe, repo, base)["result"]["paths"] == ["src/new.py"]


def test_fact_audit_can_seed_clear_from_configured_delivery_start(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    git(repo, "checkout", "-b", "feature/unregistered")
    git(repo, "config", "branch.feature/unregistered.mdf-start-commit", base)
    (repo / "src/new.py").write_text("VALUE = 1\n")
    head = commit(repo)
    ctx = audit(python_exe, repo, base)["result"]
    assert record(python_exe, tmp_path, repo, ctx)["recorded"]
    assert clear_commits.load(repo, "fact_audit") == head


@pytest.mark.parametrize("base_kind", ["normal", "local"])
def test_fact_finding_discards_matching_clear(python_exe, tmp_path, base_kind):
    repo, base = repository(tmp_path)
    git(repo, "branch", "develop", base)
    (repo / "src/new.py").write_text("VALUE = 1\n")
    commit(repo)
    first = audit(python_exe, repo, base)["result"]
    assert record(python_exe, tmp_path, repo, first)["recorded"]
    (repo / "unrelated.txt").write_text("不在 fact scope\n")
    head = commit(repo)
    forced = audit(python_exe, repo, base if base_kind == "normal" else head, "--force")["result"]
    context_file, report_file = report_files(tmp_path, forced)
    report_path = Path(report_file)
    report = json.loads(report_path.read_text())
    report["decision"] = "changes_requested"
    report["findings"].append({"id": "F1", "path": "src/new.py", "line": 1, "priority": 2, "trigger": "读取常量",
                               "impact": "现有文档缺少说明", "evidence": "src/new.py:1"})
    report_path.write_text(json.dumps(report))
    payload(mdf(python_exe, "fact-audit-report-check", "--repo", str(repo),
                "--context-file", context_file, "--report-file", report_file))
    assert not audit(python_exe, repo, base)["skip_audit"]
