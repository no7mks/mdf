"""MDF 入口工作流的文本契约测试。"""

from __future__ import annotations

from conftest import skill_dir


def skill_text(name: str) -> str:
    return (skill_dir(name) / "SKILL.md").read_text(encoding="utf-8")


def test_audit_contract_has_business_tiers_branch_bases_and_clean_start() -> (
    None
):
    audit = skill_text("mdf-audit")

    assert "release" in audit and "audit" in audit
    assert "change" in audit and "audit" in audit
    assert "develop...HEAD" in audit
    assert "master...HEAD" in audit
    assert "`clean` 必须为 `true`" in audit
    assert "浅模式" not in audit
    assert "深模式" not in audit


def test_finish_contract_requires_manual_commit_and_branch_closeout() -> None:
    finish = skill_text("mdf-finish")

    assert "不要自动 commit" in finish
    assert "feature、bugfix、hotfix" in finish
    assert "change audit" in finish
    assert "release" in finish and "audit" in finish
    assert "用户在成功后自行复查并 commit" in finish
    assert "停止" in finish
    assert "summary" in finish


def test_init_and_review_contract_cover_existing_paths_and_object_state() -> (
    None
):
    init = skill_text("mdf-init-repo")
    review = skill_text("mdf-review-doc")

    assert "完整写入方案" in init
    assert "明确确认" in init
    assert "再次显式调用" in init
    assert "$mdf-init-repo" in init
    assert "只接受一个 finding" in init
    assert "既有事实页在本次完全未改动" in init
    assert "canonical" in review
    assert "仓库相对路径" in review
    assert "立即转为" in review and "`draft`" in review
    assert "保留" in review and "`draft`" in review
    assert "closed 或 archive" in review
    assert "canonical 可以仍为 ready" in review
