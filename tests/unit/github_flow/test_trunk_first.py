"""support/* hotfix 的 Trunk-First 处置：校验、可达性核验与 CHANGE.md 记录。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from support_github_flow import commit, github_flow_repo

load_core_module()
from mdf_core.foundation.errors import MDFError  # noqa: E402
from mdf_core.foundation.yamlutil import parse_yaml  # noqa: E402
from mdf_core.lifecycle import support_line as sl  # noqa: E402


def code_of(call):
    with pytest.raises(MDFError) as caught:
        call()
    return caught.value.code


def test_every_fixed_bug_needs_exactly_one_disposition():
    assert code_of(lambda: sl.normalize_trunk_fixes([], ["bug-AAAA"])) == "trunk_first_required"
    assert code_of(lambda: sl.normalize_trunk_fixes(
        [{"bug_id": "bug-AAAA", "trunk_disposition": "backported"}] * 2, ["bug-AAAA"])) == "invalid_closeout_spec"
    assert code_of(lambda: sl.normalize_trunk_fixes(
        [{"bug_id": "bug-BBBB", "trunk_disposition": "backported"}], ["bug-AAAA"])) == "trunk_first_required"
    assert sl.normalize_trunk_fixes(None, []) == []


@pytest.mark.parametrize("raw", ["x", [1], [{"bug_id": "a"}], [{"bug_id": "a", "trunk_disposition": "x", "extra": "y"}]])
def test_malformed_trunk_fixes_are_rejected(raw):
    assert code_of(lambda: sl.normalize_trunk_fixes(raw, [])) == "invalid_closeout_spec"


def test_backported_requires_commit_reachable_from_trunk(tmp_path):
    repo = github_flow_repo(tmp_path)
    (repo / "fix.txt").write_text("trunk fix\n")
    commit(repo, "fix: trunk 先修复")
    fix = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-b", "side")
    (repo / "side.txt").write_text("未进 trunk\n")
    commit(repo, "fix: 仅在侧枝")
    side = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "master")
    ok = sl.verify_trunk_first(repo, [{"bug_id": "bug-AAAA", "trunk_disposition": "backported", "source_commit": fix}], "1.2.1")
    assert ok[0]["released_in"] == "1.2.1"
    bad = [{"bug_id": "bug-AAAA", "trunk_disposition": "backported", "source_commit": side}]
    assert code_of(lambda: sl.verify_trunk_first(repo, bad, "1.2.1")) == "trunk_first_required"
    short = [{"bug_id": "bug-AAAA", "trunk_disposition": "backported", "source_commit": fix[:8]}]
    assert code_of(lambda: sl.verify_trunk_first(repo, short, "1.2.1")) == "trunk_first_required"


@pytest.mark.parametrize("disposition", ["trunk_not_affected", "urgent_support_first"])
def test_exceptions_need_non_empty_reason(tmp_path, disposition):
    repo = github_flow_repo(tmp_path)
    bug = "bug-CD34" if disposition == "urgent_support_first" else "bug-AAAA"
    item = {"bug_id": bug, "trunk_disposition": disposition}
    assert code_of(lambda: sl.verify_trunk_first(repo, [item], "1.2.1")) == "trunk_first_required"
    assert code_of(lambda: sl.verify_trunk_first(repo, [{**item, "reason": "  "}], "1.2.1")) == "trunk_first_required"
    assert sl.verify_trunk_first(repo, [{**item, "reason": "旧线独有缺陷"}], "1.2.1")[0]["reason"] == "旧线独有缺陷"


def test_urgent_support_first_rejects_missing_or_closed_trunk_bug(tmp_path):
    repo = github_flow_repo(tmp_path)
    missing = {"bug_id": "bug-ZZZZ", "trunk_disposition": "urgent_support_first", "reason": "线上阻断"}
    assert code_of(lambda: sl.verify_trunk_first(repo, [missing], "1.2.1")) == "trunk_first_required"
    path = repo / "docs/bugs/bug-CD34-unreleased-timeout.md"
    path.write_text(path.read_text().replace("status: open", "status: closed"), encoding="utf-8")
    commit(repo, "fix: 关闭 bug")
    closed = {"bug_id": "bug-CD34", "trunk_disposition": "urgent_support_first", "reason": "线上阻断"}
    assert code_of(lambda: sl.verify_trunk_first(repo, [closed], "1.2.1")) == "trunk_first_required"


def test_support_hotfix_cannot_edit_bug_sources_and_can_cite_trunk_bugs(tmp_path):
    repo = github_flow_repo(tmp_path)
    git(repo, "branch", "support/1.2")
    git(repo, "checkout", "-b", "hotfix/1.2.1")
    bug = repo / "docs/bugs/bug-CD34-unreleased-timeout.md"
    bug.write_text(bug.read_text().replace("尚未发布", "已改写"), encoding="utf-8")
    commit(repo, "docs: 篡改 bug")
    folder = repo / "changes/unreleased/1.2.1"
    folder.mkdir(parents=True)
    (folder / "delivery.json").write_text(
        json.dumps({"branch": "hotfix/1.2.1", "base_branch": "support/1.2", "slug": "1.2.1"}),
        encoding="utf-8")
    commit(repo, "docs: 记录 hotfix 基线")
    assert code_of(lambda: sl.forbid_bug_edits(repo, "hotfix/1.2.1")) == "bug_source_forbidden"
    git(repo, "checkout", "HEAD~1", "--", "docs/bugs/bug-CD34-unreleased-timeout.md")
    bug.unlink()
    commit(repo, "docs: 删除工作区 bug")
    change = folder / "CHANGE.md"
    change.write_text("---\nfixed: [bug-CD34]\n---\n\n# 修复\n", encoding="utf-8")
    from mdf_core.inspection.validate_records import validate_record_references
    from mdf_core.foundation.errors import Finding
    findings: list[Finding] = []
    validate_record_references(repo, findings)
    assert not any(item.code == "change.record_missing" for item in findings)


def test_unknown_disposition_is_rejected(tmp_path):
    repo = github_flow_repo(tmp_path)
    item = {"bug_id": "bug-AAAA", "trunk_disposition": "later"}
    assert code_of(lambda: sl.verify_trunk_first(repo, [item], "1.2.1")) == "trunk_first_required"


def test_rendered_records_round_trip_through_frontmatter_parser():
    fixes = [
        {"bug_id": "bug-AAAA", "trunk_disposition": "backported", "source_commit": "a" * 40, "released_in": "1.2.1"},
        {"bug_id": "bug-BBBB", "trunk_disposition": "urgent_support_first", "reason": "线上阻断", "released_in": "1.2.1"},
    ]
    parsed = parse_yaml("a: 1\n" + sl.render_trunk_fixes(fixes) + "b: 2\n")
    assert parsed["trunk_fixes"] == fixes and parsed["b"] == 2
    assert sl.render_trunk_fixes([]) == ""
