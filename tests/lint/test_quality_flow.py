"""只读审查、主链小 loop 与工具验收阶段的权限和路由契约。"""
import re

from conftest import skill_dir
from support_routes import workflow, rows


def test_read_only_skips_repair_inside_one_review_chain():
    review = workflow("code-review")
    protocol = workflow("reviewer-protocol")
    skill = workflow("entry")
    readme = (skill_dir("mdf").parents[1] / "README.md").read_text(encoding="utf-8")
    kernel = review.split("## 审阅核与参数", 1)[1].split("## ", 1)[0]
    dispatch = review.split("### 派发", 1)[1].split("### ", 1)[0]
    assert "同一次审查走同一条链" in kernel
    assert "拒绝审查、不审查" in kernel
    assert "ceil(行数 / 1000)" in dispatch
    assert "没有 roster 且人数大于 1 时才切开" in dispatch
    assert ".mdf/modules.yaml" in dispatch and "不按行数切" in review
    assert "有账本但 roster 未冻结则停止" in dispatch
    assert "有账本但未冻结则停止" in review
    assert "不输出 diff 正文" in dispatch
    assert "不得因派发失败拒绝审查" in dispatch
    assert "单独 `--against` 只覆盖左端点，不因此跳过修复" in review
    assert "交付进入过步骤 3 或 4 后，步骤 5 不再重跑 review-context，也不回步骤 2" in review
    adhoc = workflow("code-review-adhoc")
    assert "不固定 1 人" in adhoc and "派 1 个严格只读 reviewer" not in adhoc
    assert "仍为 1 人" not in adhoc
    assert "人数仍按无 roster 的行数规则" in adhoc
    assert "未覆盖留在 2" in adhoc
    assert "不得写入尚未读完的 path" in protocol
    assert "incomplete 仅在 decision 为 error 时可以非空" in protocol
    assert "进入过 Repair 或 Record 后不重建" in protocol
    assert "证据不足或未完成时 needs-review" not in protocol
    assert "不按文件、模块或领域拆分" in review
    assert "指定为 1 的轮次不为冻结 roster 让路" in review
    assert "有 roster 时用冻结人数" not in review
    option = next(line for line in kernel.splitlines() if line.startswith("- `$mdf code-review --read-only`"))
    assert "不进入 Repair 与 Record" in option
    output = next(line for line in kernel.splitlines() if line.startswith("- `$mdf code-review --output"))
    assert "没有该参数则不写文件" in output
    table = rows(review)
    assert [row[1] for row in table] == ["Check", "Review", "Repair", "Record", "Report"]
    assert table[1][6] == "未覆盖留在2"
    assert table[1][5] == "只读5；可复用4；否则3"
    assert "未审查不得写入 incomplete" in review
    assert "未审查不是合法 decision" in protocol
    assert "派不出 subagent 时由主 Agent 审查" in protocol
    assert "--read-only`：跳过 Repair 与 Record" in skill
    assert "每 1000 行一人" in readme and "模块相近度" in readme
    assert "不派 subagent" not in kernel


def test_review_findings_are_reproduced_only_after_readonly_reports_are_complete():
    review = workflow("code-review")
    assert "reviewer 严格只读" in review
    assert "不修改实现、tests、配置或报告，不运行 tests" in review
    assert "reviewer 通过会话返回报告" in review
    assert "报告齐全前不修改审查对象" in review
    assert "由 main Agent 汇总去重，构建并运行 failing test" in review
    assert "reviewer 没有 failing test 不影响报告完整性，也不提前触发降级" in review
    assert "同一 finding 不因多份报告或续办重复降级" in review
    assert "亲自尝试构建并运行 failing test" not in review
    assert "main Agent 分派前用只读 measure_code.py" in review
    assert "不让 reviewer 执行脚本、运行 tests 或写入报告" in review
    assert "within_required_split_targets: true" in review
    assert "不能用迁入较宽松 module 后的目标替代原目标" in review
    assert "未发生拆分的文件不能仅因超过拆分目标被要求改写" in review


def test_verify_repair_requires_one_incremental_review_and_original_verification():
    verify = workflow("verify")
    assert "人工 feature 的 verify smoke 与 adhoc 的主链 smart" in verify
    assert "独立调用和 deliver 均执行" in verify
    assert "修绿后检查相对左端点的净变化" in verify
    assert "做 1 人增量审查" in verify
    assert "不改冻结 roster" in verify
    assert "不以 smart 代替 branch" in verify
    assert "不递归委托本 loop" in verify
    assert "沿用刚完成的通过报告" in verify
    assert "小 loop 未完成时不得勾选主链验证或进入 fact" in verify
    assert "不因此强制重开" not in verify


def test_every_objectives_template_places_lint_before_code_review():
    root = skill_dir("mdf") / "assets/templates"
    for path in root.glob("*objectives.md"):
        text = path.read_text()
        assert text.index("- [ ] lint") < text.index("- [ ] code-review"), path
    assert "lint 已勾、code-review 未勾" in workflow("deliver")
    assert "references/lint.md" in workflow("manual-feature")
    assert "references/lint.md" in workflow("adhoc")


def test_lint_tools_and_coverage_have_separate_responsibilities():
    lint = workflow("lint")
    assert rows(lint)[1][2] == "脚本"
    assert "内置代码规模检查与项目 lint command" in lint
    assert "MDF 不要求启用" in lint
    assert "文档长度、结构与事实一致性留在 fact audit" in lint
    converge = workflow("converge")
    assert "仅 feature/release 实际进入本 intent" in converge
    assert "未配置时记录未配置" in converge
    assert "沿用 has_dev: no 等既有 converge 跳过规则" in converge
    assert "修复后重跑 smart 与 coverage" in converge


def test_verify_loop_is_in_the_numbered_workflow_and_has_a_final_tick():
    table = rows(workflow("verify"))
    assert [row[1] for row in table] == [
        "Resolve modules", "Select", "Run", "Record", "Recheck", "Tick",
    ]
    assert "主链绿 5" in table[3][5]
    assert "非主链按实际结果返回" in table[3][5]
    assert "无新业务改动且报告匹配 6" in table[4][5]
    assert "修复改业务或报告不符 3" in table[4][5]
    assert "必要复审完成" in table[5][3]


def test_resume_context_survives_child_report_finalization():
    verify = workflow("verify")
    assert "objectives 的非 checklist 备注" in verify
    assert "步骤 6 完成小 loop 后才清理" in verify
    assert "新会话恢复先按备注重跑原验证" in verify
    assert "不得删除 objectives 中父 verify" in workflow("code-review")
    assert "不按首个退勾项提前重开审查" in workflow("next")
    assert "完成后才返回 Select" in workflow("deliver")
    assert "推进操作左端点并更新、提交续办备注" in verify
    assert "更新实际命令基准" in verify
    assert "报告被覆盖/不匹配时，回 3 重跑原验证范围" in verify
    assert "不能把子流程的部分验证冒充原主链结果" in verify


def test_one_reviewer_covers_all_incremental_partitions_and_waits_for_green():
    review = workflow("code-review")
    assert "本轮只有 1 人时覆盖整个本轮 diff" in review
    assert "不受冻结 partition 切片限制" in review
    assert "来源 verify 的草稿仍待修绿时，返回原 verify 修绿；不得提前派审查" in review


def test_lint_failures_have_an_explicit_authorized_retry_path():
    lint = workflow("lint")
    assert "树形：not-tree。" not in lint
    table = rows(lint)
    assert table[1][5] == "成败均 3"
    assert "可修且已修 2" in table[2][5]
    assert "无授权则报告失败" in table[2][6]
    assert "Git 根、module、适用 objectives" in table[0][4]


def test_closeout_never_runs_nested_smart_to_finish_review():
    review = workflow("code-review")
    assert "close-out 委托且本轮修复需要 smart" in review
    assert "不运行 verify，不洗终稿、不勾选" in review
    assert "由主链外恢复原修复窗" in workflow("close-out")
    assert "close-out 返回「待主链外续办」" in workflow("deliver")


def test_all_public_commands_have_a_discoverable_help_topic():
    help_text = workflow("help")
    topic_index = help_text.split("主题键：", 1)[1].split('- `$mdf bootstrap`', 1)[0]
    topics = set(re.findall(r"`([^`]+)`", topic_index))
    routes = re.findall(r"[├└]──── (.+?) ─+→ references/[a-z-]+\.md", workflow("entry"))
    for route in routes:
        for command in route.split(" / "):
            canonical = re.split(r"\s+(?:\[|<|--)", command, maxsplit=1)[0]
            canonical = {"next?": "tree", "next？": "tree"}.get(canonical, canonical)
            assert canonical in topics, command
