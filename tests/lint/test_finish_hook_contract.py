"""主链 hook 的触发范围、补审补测与续办约束。"""
from conftest import skill_dir


def test_finish_hook_routes_before_fact_and_never_inside_gitflow():
    root = skill_dir("mdf") / "references"
    hook = (root / "hooks/pre-gitflow-finish.md").read_text()
    assert "verify branch → 本 hook → fact audit" in hook
    assert "verify smoke → 本 hook → fact update" in hook
    assert "无论 hook 成功或失败，都按实际改动处理" in hook
    assert "其他改动补审补测" in (root / "delivery-contract.md").read_text()
    assert "已执行（含失败）则不重跑" in hook
    assert "--after <before_head>" in hook
    assert "退勾 code-review、verify branch" in hook
    assert "不新增 objectives 项" in hook
    assert "独立文档维护、独立 fact audit、migrate 不触发" in hook
    for name in ("deliver", "next", "manual-feature", "fact-update", "fact-audit"):
        assert "hooks/pre-gitflow-finish.md" in (root / f"{name}.md").read_text(), name
    closeout = (root / "close-out.md").read_text()
    assert "不在本 intent 或 `finish-gitflow` 内补跑" in closeout
