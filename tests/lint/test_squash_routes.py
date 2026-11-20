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
    assert "gitflow 的 `planning land` 在 local 和 PR mode" in squash
    assert "不可压或失败" in squash
    merge = workflow("merge")
    assert "references/squash.md" in merge
    assert "dry-run 建议由 Agent 裁定" in merge
    assert "squash" not in finish
    assert "references/squash.md" in contract
    assert "公开 `$mdf squash` 负责" in squash or "公开 `$mdf squash` 承担" in squash
    assert "dry-run 计划" in squash
    assert "$mdf squash" in workflow("help")
    assert "[--dry-run]" in workflow("help")
    converge = workflow("converge")
    assert "`$mdf squash`" in converge
    assert "询问、执行或委托" in converge
