"""公开 `$mdf squash`（执行-only）的路由与契约。"""
from __future__ import annotations

from support_routes import workflow


def test_squash_is_public_execution_only_and_closeout_delegates():
    squash = workflow("squash")
    finish = workflow("close-out")
    contract = workflow("delivery-contract")
    assert "git reset --soft" in squash
    assert "git restore --source=" in squash
    assert "git merge --squash" in squash
    assert "reset --hard" in squash
    assert "已推送分支上改写" in squash
    assert "起草 message" in squash
    assert "不改已确认 message" in squash or "不得改写已确认 message" in squash
    assert "references/squash.md" in finish
    assert "[委托 squash 后继续本步]" in finish
    assert "执行由公开 `$mdf squash` 承担" in contract
    assert "$mdf squash" in workflow("help")
    converge = workflow("converge")
    assert "`$mdf squash`" in converge
    assert "询问、执行或委托" in converge
