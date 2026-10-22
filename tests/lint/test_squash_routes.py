"""公开 `$mdf squash`（含 dry-run 建议与定型）的路由与契约。"""
from __future__ import annotations

from support_routes import workflow


def test_squash_plans_and_closeout_dry_run_before_heuristic():
    squash = workflow("squash")
    finish = workflow("close-out")
    contract = workflow("delivery-contract")
    assert "--dry-run" in squash
    assert "git reset --soft" in squash
    assert "git restore --source=" in squash
    assert "git merge --squash" in squash
    assert "reset --hard" in squash
    assert "已推送分支上改写" in squash
    assert "几段与切法" in squash
    assert "不得改写已定型 message" in squash
    assert "展示建议并结束" in squash
    assert "不逐次请求用户确认" in squash
    assert "planning land" in squash and "所有模式" in squash
    assert "不可压或失败" in squash
    assert "references/squash.md" in finish
    assert "dry-run" in finish and "--dry-run" not in finish
    assert "先内部执行" in finish and "dry-run" in finish
    assert "地板取 dry-run 计划" in finish or "计划中的地板" in contract
    assert "[委托 squash 后继续本步]" in finish
    assert "dry-run 建议且 Agent 裁定" in finish
    assert "不逐次确认" in finish
    assert "references/squash.md" in contract
    assert "公开 `$mdf squash` 负责" in squash or "公开 `$mdf squash` 承担" in squash
    assert "dry-run 计划" in squash
    assert "$mdf squash" in workflow("help")
    assert "[--dry-run]" in workflow("help")
    converge = workflow("converge")
    assert "`$mdf squash`" in converge
    assert "询问、执行或委托" in converge
