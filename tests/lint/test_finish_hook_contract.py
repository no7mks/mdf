"""主链 hook 的触发范围、补审补测与续办约束。"""
from conftest import skill_dir


def test_finish_hook_routes_before_fact_and_never_inside_gitflow():
    root = skill_dir("mdf") / "references"
    hook = (root / "pre-gitflow-finish.md").read_text()
    assert "verify branch → 本 hook → fact audit" in hook
    assert "verify smoke → 本 hook → fact update" in hook
    assert "verify smart → 本 hook → fact audit/update" in hook
    assert "无论 hook 成功或失败，都按实际改动处理" in hook
    assert "其他改动补审补测" in (root / "delivery-contract.md").read_text()
    assert "已执行（含失败）则不重跑" in hook
    assert "--after <before_head>" in hook
    assert "退勾 code-review、验证及 fact" in hook
    assert "不新增 objectives 项" in hook
    assert "独立文档维护、独立 fact audit、migrate 不触发" in hook
    for name in ("deliver", "next", "manual-feature", "fact-update", "fact-audit"):
        assert "(pre-gitflow-finish.md)" in (root / f"{name}.md").read_text(), name
    adhoc = (root / "adhoc.md").read_text()
    assert "pre-gitflow-finish --repo <owner>" in adhoc
    assert "--after <before_head>" in adhoc
    closeout = (root / "close-out.md").read_text()
    assert "不在本 intent 或 `finish-gitflow` 内补跑" in closeout


def test_hook_workflows_are_separate_from_configuration():
    root = skill_dir("mdf") / "references"
    for name in ("post-gitflow-start", "pre-gitflow-finish"):
        workflow = (root / f"{name}.md").read_text()
        config = (root / "hooks" / f"{name}.md").read_text()
        assert "## 工作流（唯一执行契约）" in workflow
        assert f"hooks/{name}.md" in workflow
        assert "## 配置" in config
        assert "## 执行与实际改动" not in config
        assert f"../{name}.md" in config
        assert "失败" in workflow and "日志" in workflow
