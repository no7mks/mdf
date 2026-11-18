"""按 manifest 渲染 AGENTS.md 的 MDF 托管 block。"""

from mdf_core.foundation.constants import MDF_BLOCK_END, MDF_BLOCK_START
from mdf_core.foundation.errors import MDFError
from mdf_core.workspace.merge_policy import config
from mdf_core.workspace.workflow_policy import GITHUB_FLOW, parse_workflow

DIRECT_CHANGE_RULE = "- 直接在 {branch} 上改动时，按事项创建 `changes/unreleased/<slug>/`，至少留存 `CHANGE.md`。"
CHECKOUT_RULE = (
    "- github-flow：主工区永远只 checkout 主 branch（`workflow.trunk`）。\n"
    "  - ❌ 不得 checkout 任何其他 branch。\n\n"
)
TRUNK_PUSH_RULE = (
    "- 当 manifest 使用 `github-flow` 和 PR mode 时，推送 `workflow.trunk` 前先 fetch `origin`，检查本地独有 commit。\n"
    "  - 有本地独有 commit 时停止直接 push，提示用户运行 `$mdf trunk-pr`。\n"
    "  - 已确认 `$mdf sync` 的 PR 计划时，按该计划接管并续办。\n\n"
)


def block_span(text: str) -> tuple[int, int] | None:
    starts, ends = text.count(MDF_BLOCK_START), text.count(MDF_BLOCK_END)
    if starts == 0 and ends == 0:
        return None
    if starts == 1 and ends == 1:
        start, end = text.index(MDF_BLOCK_START), text.index(MDF_BLOCK_END)
        if start < end:
            return start, end + len(MDF_BLOCK_END)
    raise MDFError("AGENTS.md 的 MDF 标记格式错误或重复", code="invalid_managed_block")


def _eol(text: str, template: str) -> str:
    return text.replace("\n", "\r\n") if "\r\n" in template else text


def render_block(template: str, manifest: dict) -> str:
    rule, checkout = _eol(TRUNK_PUSH_RULE, template), _eol(CHECKOUT_RULE, template)
    block = template.strip().replace(rule, "", 1).replace(checkout, "", 1)
    workflow = parse_workflow(manifest)
    develop_change = DIRECT_CHANGE_RULE.format(branch="develop")
    trunk_change = DIRECT_CHANGE_RULE.format(branch="`workflow.trunk`")
    if workflow["model"] != GITHUB_FLOW:
        return block.replace(trunk_change, develop_change, 1)
    block = block.replace(develop_change, trunk_change, 1)
    block = block.replace(MDF_BLOCK_END, checkout + MDF_BLOCK_END, 1)
    if config(manifest)["mode"] != "pr":
        return block
    return block.replace(MDF_BLOCK_END, rule + MDF_BLOCK_END, 1)
