"""公开 `$mdf squash`（含 dry-run 建议与定型）的路由与契约。"""
from __future__ import annotations

from support_routes import workflow


def test_squash_plans_and_closeout_uses_dry_run_then_execute():
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
    assert "不得改写已确认 message" in squash
    assert "展示建议并结束" in squash
    assert "references/squash.md" in finish
    assert "dry-run" in finish and "--dry-run" not in finish
    assert "[委托 squash 后继续本步]" in finish
    assert "dry-run 建议且用户确认执行" in finish
    assert "公开 `$mdf squash` 负责" in contract or "公开 `$mdf squash` 承担" in contract
    assert "$mdf squash" in workflow("help")
    assert "[--dry-run]" in workflow("help")
    converge = workflow("converge")
    assert "`$mdf squash`" in converge
    assert "询问、执行或委托" in converge
