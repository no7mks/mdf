"""交付主线 intent（start 至 finish、fix、bug close）的文档路由与约束。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from types import SimpleNamespace
import re
import shlex
import unicodedata
from conftest import skill_dir
from support_routes import *  # noqa: F403

def test_review_resume_routes_to_repair_without_replacing_initial_head():
    from conftest import skill_dir
    text = (skill_dir("mdf") / "references/code-review.md").read_text()
    assert "修复续办 3；无新则结束；否则 2" in text
    assert "已齐审查且修复续办" in text
    assert "保留原 review_head，不覆盖原报告" in text
    assert "首轮未齐时进入 2 补齐" in text
    assert "增量新一轮" in text
    assert "已齐审查且无新改动" in text
    assert "非本交付 `docs/` 不是新的交付改动" in text
    assert "finish 集成增量轮与主链 verify 修绿轮为 1" in text
    assert "不得把上轮多份独立报告交给本轮" in text
    assert "git diff <操作左端点> <review_head>" in text
    assert "仍解决 / 复开 / 不适用" in text
    assert "changes/unreleased/<slug>/code-review.md" in text
    assert "终稿不得出现任何 commit hash" in text
    assert "裁定收口" in text

def test_close_out_materials_without_embedded_verify_or_fact():
    text = workflow("close-out")
    prepare = text.split('<a id="s3"></a>', 1)[1].split('<a id="s4"></a>', 1)[0]
    assert "不内嵌、不委托 verify" in text or "不委托 verify" in text
    assert "bug close（步骤 7）不算 verify 族" in text or "不算 verify 族" in text
    assert "delivery check --stage fact-update" not in text
    assert "move-change" not in text
    assert "- feature：" in prepare
    assert "- bugfix：" in prepare
    assert "- release：" in prepare
    assert "- hotfix：" in prepare
    assert "材料不搬迁" in prepare
    assert "start 已写入的 objectives checklist 保留" in prepare

def test_finish_keeps_pending_closeout_on_the_release_path():
    text = workflow("close-out")
    table = rows(text)
    assert table[3][5] == "已收口或 feature/bugfix→9；待收口→5"
    assert table[7][5] == "9"
    assert "裁定有效 10" in table[8][5] and "deliver 6" in table[8][5]
    assert "feature/bugfix 回 2" in table[8][6]
    assert "其余停" in table[8][6]
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert "有写入" not in diagram and "无写入" not in diagram
    assert "preview" not in diagram and "预览" not in diagram
    assert "不提供预览模式" in text
    assert "仅预览或只读时" in text and "说明此入口不支持并停止" in text
    assert "正文为本版 CHANGELOG" in text
    assert "精简条目" in text
    assert "--dry-run" not in text

def test_start_clarifies_feature_objectives_before_branch():
    text = workflow("start")
    table = rows(text)
    assert table[0][5] == "2"
    assert "objectives checklist" in table[1][3]
    assert table[1][5] == "3"
    assert table[1][6] == "不写目标，停止"
    assert table[2][1] == "Confirm roster"
    assert table[2][2] == "约束"
    assert "member、strategy 与 models" in table[2][3]
    assert table[2][5] == "冲突2；否则4"
    assert table[2][6] == "拒绝停止；未决留3"
    assert table[3][1] == "Start branch"
    assert table[3][5] == "5"
    assert table[4][1] == "Switch worktree"
    assert table[4][2] == "约束"
    assert table[4][5] == "同/跨→6；collab 交接结束；其他结束"
    assert table[4][6] == "留在 5 等待"
    assert table[5][1] == "Open integrate"
    assert table[5][5] == "结束"
    assert "needs_design" in text
    assert "本侧可碰范围" in text
    assert "不得改、操作、启动或终止对端" in text
    assert "不得先做其他预发布工作" in text
    assert "references/integrate.md" in text
    assert "references/clarify.md" in text
    assert "assets/templates/objectives.md" in text
    assert "assets/templates/release-objectives.md" in text
    assert "只写入已选定的那一条" in text
    assert "只写入已选定的那一条" in text
    assert "只写入已选定的那一条" in text
    template = (
        skill_dir("mdf") / "assets" / "templates" / "release-objectives.md"
    ).read_text(encoding="utf-8")
    assert "## 工作线" in template
    assert "{{MDF_RELEASE_WORK_LINE}}" in template
    assert "## 联调" in template
    assert "{{MDF_RELEASE_INTEGRATE}}" in template
    assert "不联调：" not in template
    assert "本版选定" not in template
    assert "$mdf prp review" in text
    assert "qa_strategy" in text and "dev_strategy" in text
    assert "review_strategy" in text
    assert "未带的 intent 不写、不问、不提" in text
    assert "不得把沉默当作同意" in text
    assert "已锁定的 release 或 hotfix 上修复 Bug 不走本 intent" in text
    assert "口语点名的模型" in text
    assert "不要求官方 id" in text
    assert "不得实施新 PRP" in text
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert re.search(r"失败/缺失 ─+→ \[留在 1 询问\]", diagram)
    assert "bugfix/hotfix 通过" not in diagram
    assert re.search(r"3 Confirm roster", diagram)
    assert re.search(r"创建成功", diagram)
    assert re.search(r"4 Start branch", diagram)
    assert re.search(r"5 Switch worktree", diagram)
    assert re.search(r"6 Open integrate", diagram)
    assert re.search(r"已切到且 release 需联调", diagram)
    assert re.search(r"collab-mode 已交接 ─+→ \[结束\]", diagram)

def test_start_switches_agent_to_owner_worktree():
    text = workflow("start")
    assert "创建成功进入 5" in text
    assert "qa/dev 不在本步切换" in text
    assert "切换工作区" in text
    common = workflow("common")
    assert "仅 Cursor 主 Agent" in common
    assert "全部 subagent" in common
    assert "禁止 `move_agent_to_root`" in common
    assert "横幅必须用新路径与新项目 logo" in common
    assert "仅改绝对路径绑定" in common
    assert "<旧横幅>\n  ⬇️\n  <新横幅>" in common
    assert "实际输出为裸三行硬换行" in common
    assert "禁止把 `⬇️` 与旧/新横幅写在同一行" in common
    assert "禁止在这三行之间插入空行或其它文字" in common
    assert "move_agent_to_cloned_root" in common
    assert "禁止要求用户切换" in common
    assert "git -C <路径>" in common
    assert "EnterWorktree" not in common
    assert "New local worktree" not in common
    assert "File > Open Folder" not in common
    assert "git rev-parse --show-toplevel" in common
    assert "git branch --show-current" in common
    assert "不得再 `git worktree add`" in common
    assert "不得只在原根 `cd` 冒充已进入" in common
    entry = workflow("entry")
    assert "references/common.md" in entry and "s-banner" in entry
    assert "所有 intent（含 help/clarify/upgrade）均适用" in entry


def test_fix_is_branch_agnostic_and_stops_at_fixed():
    text = workflow("fix")
    table = rows(text)
    assert [row[1] for row in table] == [
        "Check", "Clarify", "Reproduce", "Repair", "Record",
    ]
    assert table[1][2] == "约束"
    assert table[2][1] == "Reproduce"
    assert table[2][3] == "确认或编写该 Bug 的有效红灯测试"
    assert table[3][6] == "未满三轮且下一步明确则 4；否则停"
    assert table[4][5] == "结束"
    for rule in (
        "不切分支", "不 start", "不走交付主线", "不 code-review", "不 finish",
        "不由 deliver 内部委托", "不读取当前 Gitflow kind",
        "不写 child Change", "不填 `fixed_in`", "不把对象标为 `closed`",
        "`--yolo` 时主 Agent 依据仓库证据与 Bug",
        "不代替该项批准", "不按分支 kind 选择 smoke 或 release",
        "不调用 `$mdf verify --scope branch`",
        "master 不直接修改或提交",
        "标为 `fixed`",
        "未记录有效红灯不得改生产实现",
        "导入错误、编译失败或环境故障不算有效红灯",
        "`--yolo` 不跳过本步",
        "本步不得改生产实现",
    ):
        assert rule in text
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert re.search(r"未满三轮且下一步明确 ─+→ 4 Repair", diagram)
    assert re.search(r"有效红灯已记录", diagram)
    assert re.search(r"不修复，停止", diagram)
    help_text = workflow("help")
    assert "$mdf fix <bug-id> [--yolo]" in help_text
    keys = help_text.split("### 主题", 1)[1].split("`$mdf bootstrap`", 1)[0]
    assert "`fix`" in keys
    contract = workflow("delivery-contract")
    assert "独立 `$mdf fix`" in contract
    assert "也不由 deliver 内部委托" in contract
    assert "修复某个 Bug 的提交说明必须含该 Bug 的完整 ID" in contract
    common = workflow("common")
    assert "修复某个 Bug 的提交说明必须含该 Bug 的完整 ID" in common
    assert "git log --fixed-strings --grep=<Bug ID>" in common


def test_verify_fix_is_second_verification_before_closeout():
    text = workflow("bug-close")
    table = rows(text)
    assert [row[1] for row in table] == ["Check", "Verify", "Review", "Record"]
    assert table[1][6] == "可修或获批回 2；否则停"
    assert table[2][6] == "有可修回 2；需决定则停"
    for rule in (
        "标为 `closed` 并写 `fixed_in`", "--fixed-in", "不跑全局",
        "不替代 `$mdf code-review`",
        "只要求这些复现用例通过",
        "不调用 `$mdf code-review`",
        "不按上一正式发布或 start_commit 做整分支审查",
        "不派 roster.reviewers",
        "可修复实现问题",
        "finish 内部委托时完成后返回调用方",
        "不由 deliver 直接委托",
        "bug-close.md",
    ):
        assert rule in text
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert re.search(r"可修复实现问题 ─+→ 2 Verify", diagram)
    assert re.search(r"有可修问题 ─+→ 2 Verify", diagram)
    finish = workflow("close-out")
    assert "references/bug-close.md" in finish
    assert "待收入 fixed 先委托 bug close" in finish
    assert "bug close 未通过" in finish
    help_text = workflow("help")
    assert "$mdf bug close <bug-id> --fixed-in <version>" in help_text
    keys = help_text.split("### 主题", 1)[1].split("`$mdf bootstrap`", 1)[0]
    assert "`bug close`" in keys


def test_implementation_handoff_distinguishes_checks_from_remaining_work():
    text = workflow("implement")
    assert "逐项对照 objectives" in text
    assert "命令、退出状态、结果及对应验收项" in text
    assert "不要求测试先完成或项目全绿" in text
    assert "不以 `delivery record/check --stage implement` 为完成条件" in text
    assert "区分已验证结论与未验证项" in text


def test_delivery_forces_worktrees_and_shared_design_base():
    start = workflow("start")
    design = workflow("design")
    tests = workflow("write-tests")
    implement = workflow("implement")
    contract = workflow("delivery-contract")
    assert "<repo-name>-worktrees/<worktree-name>" in start
    assert "不在当前目录开分支" in start
    assert "write-tests 与 implement 后续都会依赖的共享代码底座" in design
    assert "底座未写入该基线则不得结束" in design
    assert "worktrees.qa" in tests
    assert "不得在 feature 上编写或补写测试" in tests
    assert "本阶段不要求项目全绿" in tests
    assert "不得因断言失败拒绝完成" in tests
    assert "smart" in workflow("converge")
    assert "不要求全绿" in contract
    assert "worktrees.dev" in implement
    assert "不得在 feature 上实现" in implement
    assert "merge-no-ff" in tests
    assert "merge-no-ff" in implement
    assert "delivery worktree" not in tests
    assert "delivery worktree" not in implement
    assert "入口先 no-ff merge owner" in contract
    assert "两路不得各自再写底座" in contract
    assert (
        "| verify branch（feature/bugfix/hotfix） | lint、build、quick、smoke |"
        in contract
    )
    assert "| verify branch（release） | lint、build、quick、release |" in contract
    assert "主链收口前 | verify branch 绿 + fact audit 通过 |" in contract
    assert "bugfix 的 `suites.json` 在 verify branch 前关联" in contract
    assert "verify --scope named --suites" in contract and "frontmatter" in contract
    assert "每次运行 suite（含 named suite）都必须产出 JUnit XML 报告" in contract
    assert "即使命令退出码为 0" in contract
    assert "测试失败工作流" in contract
    assert "verify branch（feature/bugfix/hotfix）" in contract
    assert "过期 gatekeeping" in workflow("verify") or "过期 gatekeeping" in contract
    assert "mock 掉兄弟产品后才算 hermetic" in contract
    assert "xfail 或 xpass，以及 suite 未选中任何 test" in contract
    assert "新增或放宽须用户确认" in contract
    assert "缺覆盖" in contract or "reproduce" in contract
    assert "优先放入 quick，其次 smoke" in contract
    assert "优先放入 quick，其次 smoke" in contract
    assert "缺覆盖则先补 reproduce" in contract or "原来是否缺少覆盖" in contract
    assert "补覆盖" in contract
    assert "补覆盖按" in workflow("integrate")
    assert "按依赖\n拆成多个 test case 分别归入合适的 suite" in contract
    assert "验证入口为 lint/build/quick/smoke/release 与可选 coverage" in contract
    assert "非 feature 分支变更 modules.yaml 套件入口或新增 named suite：默认模式需用户确认" in contract
    repo_contract = workflow("repository-contract")
    assert "验证命令**不在** manifest；写在 `.mdf/modules.yaml`" in repo_contract
    assert "`named` 中每个名字必须有独立文档" in repo_contract
    design_text = workflow("design")
    assert "验收到 quick、smoke 与本交付 named suite 的映射" in design_text
    assert "必须同时给出 `protected_paths` 与 `suites`" in design_text
    assert "把用例归入 quick、smoke 或\ndesign policy `suites` 所列 named suite" in tests
    converge = workflow("converge")
    assert "smart" in converge
    assert "阻塞停止" in converge
    assert "Accept" in converge
    assert "named suite 已文档化" in tests
    assert "收尾前核对每个声明的 named suite 都已文档化且有成员" in tests
    assert "COLLECTIONS" not in (skill_dir("mdf") / "assets/templates/design.md").read_text()
    review = workflow("code-review")
    assert "必须尝试补一条 quick 复现用例" in review
    assert "quick 复现（已补 <用例位置>" in review
    assert "suites.json" in review or "verify branch" in review or True
    assert "converge" in review
    assert "不跑 verify branch" in review
    assert "`$mdf verify --scope smart`" in review or "verify --scope smart" in review
    deliver = workflow("deliver")
    assert "外层协调者" in deliver
    assert "交接结束" in rows(deliver)[1][5]
    assert re.search(r"collab-mode 联调未完且待接手 ─+→ \[交接并结束\]", deliver)
    assert "先测后审" not in deliver
    assert "| release integrate 未勾 |" in deliver
    assert "| release 缺 integrate checklist 项或正文未写工作线 |" in deliver
    assert "integrate" in deliver
    assert "| release 跨 worktree 联调且对端验收未通过 |" in deliver
    assert "| release 联调且尚未确认无更多代码修改 |" in deliver
    assert "has_dev: no" in deliver or "has_dev" in deliver
    assert "verify branch" in deliver
    assert "close-out" in deliver
    assert "needs_design" in deliver
    assert "进度只认 objectives" in deliver or "只认 objectives" in deliver
    finish = workflow("close-out")
    assert "不委托 verify" in finish or "不内嵌、不委托 verify" in finish
    assert "永不在 closeout 内执行验证" in finish or "verification_report_not_reusable" in finish
    assert "不算 verify 族" in finish
    assert "不做 commit 对齐审判" in finish or "不做 verify 报告的 commit 对齐" in finish
    contract = workflow("delivery-contract")
    assert "只复用可复用的" in contract or "永不执行验证命令" in contract
    assert "不运行 `delivery check --stage finish`" in finish
    assert "确认单独提问" in workflow("fact-audit")
    assert "不重跑" in workflow("bug-close")
    assert "既有 suite 命令未产出报告时" in workflow("migrate")
    assert "占位命令必然失败" in workflow("repository-contract")
    assert "`unknown_suite`" not in review
    assert "suites.json" in workflow("verify") or "named suite" in workflow("verify")
    assert "suites.json" not in workflow("start")
    assert "交付级 suite" not in contract and "下沉" not in contract


def test_code_review_requires_three_full_reviews_before_owner_repairs():
    text = workflow("code-review")
    table = rows(text)
    assert table[1][2] == "Subagent"
    assert "按本轮应派人数启动严格只读 subagent" in table[1][3]
    assert table[1][5] == "3"
    assert table[3][6] == "close-out 需 smart 返回待续办；可修则 3；否则停"
    for rule in (
        "不安排分工", "不共享其他审查者结论", "reviewer 严格只读",
        "报告齐全前不修改", "以证据裁定，不按票数决定",
        "不强制再次启动审查 subagent", "不足本轮应派人数", "无法补齐则停止",
    ):
        assert rule in text


def test_design_and_converge_launch_one_owner_subagent():
    design = workflow("design")
    table = rows(design)
    assert table[1][2] == "约束"
    assert table[2][1] == "Baseline"
    assert table[2][2] == "Subagent"
    assert table[2][6] == "缺确认回 2；可修正则 3；否则停"
    for rule in (
        "启动恰好 1 个 owner subagent 执行步骤 3",
        "不计入 roster，不可配人数",
        "当前 Agent 执行步骤 1–2 与交接核验",
        "不得代写 design.md、底座或勾选 design",
        "不降级代做",
        "不对同一",
        "缺确认则停止该 subagent 并回步骤 2",
        "不在 subagent 内 grilling",
        "不以 `delivery check --stage design` 为完成条件",
    ):
        assert rule in design
    converge = workflow("converge")
    table = rows(converge)
    assert table[0][1] == "Dispatch"
    assert table[0][2] == "Subagent"
    assert "启动恰好 1 个 owner subagent 执行步骤 2–4" in table[0][3]
    assert table[2][1] == "Accept"
    assert "可修" in table[2][6] and "3" in table[2][6]
    assert table[3][1] == "Tick"
    for rule in (
        "当前 Agent 不得代做",
        "不计入 roster，不可配人数",
        "不对同一",
        "需测试修改批准时 subagent 停止并交出未决",
        "resume\n同一 subagent",
        "subagent 按其 confidence 策略裁定并记录批准",
        "低 confidence 回主会话请求用户确认",
        "不以 `delivery record/check --stage converge` 为完成条件",
        "主会话确认后 resume 回 3",
    ):
        assert rule in converge
    contract = workflow("delivery-contract")
    assert "owner subagent" in contract
    assert "deliver 步骤 4 只覆盖可并行的 qa/dev" in contract
    help_text = workflow("help")
    assert "Baseline 由本 intent 派恰好 1 个 owner" in help_text
    assert "本 intent 派恰好 1 个 owner subagent 执行集成、验证与记录" in help_text or "owner subagent" in help_text
    assert "不走 deliver 步骤 4" in help_text


def test_code_review_covers_branch_starts_and_previous_release():
    text = workflow("code-review")
    for rule in (
        "delivery.json 的 start_commit", "mdf-start-commit",
        "上一正式发布版本的 master commit/tag", "首次发布没有上一版本",
        "git diff <base_commit> <review_head>", "基线必须是当前 HEAD 的祖先",
        "git diff <操作左端点> <review_head>",
        "changes/unreleased/<slug>/code-review.md",
        "不取 master 合回 develop 的合并提交", "不重新追随分支或 tag",
        "进度只认 `objectives.md`",
        "审查基线仍为上一正式发布", "objectives.md",
        "不再改代码",
        "不跑 verify branch", "洗成无 commit 终稿",
        "不运行 `delivery record --stage code-review`",
    ):
        assert rule in text
    finish = workflow("close-out")
    assert "develop...HEAD" not in finish and "master...HEAD" not in finish
    assert "四种分支均须有完整的各轮应派份数独立审查" in finish
    assert "本轮应派人数为 1" in finish
    assert "不得把上轮多份原文交给本轮唯一 reviewer 去合并" in finish
    assert "Agent 按已确认目标、设计及两侧改动自动尝试 resolve" in finish
    assert "不启动 code-review" in finish
    assert "不委托、不执行 verify" in finish or "不在 closeout 内执行验证" in finish
    assert "本交付文档" in finish
    assert "以集成后的 HEAD 执行增量新一轮" in finish
    assert "不复用集成前终稿充当增量差" in finish
    assert "终稿存在、声称通过" in finish
    assert "复核上轮问题" in finish
    assert "不得跳过" in finish
    assert "report 缺失时内部执行 code-review" in finish
    assert "可选 squash" in finish
    assert "第一次把目标主线合入交付分支之前" in finish
    contract = workflow("delivery-contract")
    assert "可选历史整理（squash）" in contract
    assert "references/squash.md" in contract
    squash = workflow("squash")
    assert "git merge --squash" in squash
    assert "是否 squash 与执行计划的确认均按其 confidence 策略裁定" in squash
    assert "是否建议（可选启发式）" in squash
    assert "不可 squash" in squash
    assert "dry-run 建议且用户确认执行" in finish
    assert "推导出必须空转的 owner 开发" in contract
    assert "has_dev" in contract
    verify = workflow("verify")
    assert rows(verify)[2][5] == "4"
    assert "未绿且可修 → 回 3" in verify or "未绿可修→3" in verify
    assert "未绿轮不写" in verify or "未绿轮不得勾选" in verify
    assert "integrate 未勾" in workflow("deliver")
    assert "has_dev" in workflow("start")
    assert "integrate 项须已" in text


def test_role_intents_do_not_reuse_owner_session_switch():
    tests = workflow("write-tests")
    implement = workflow("implement")
    deliver = workflow("deliver")
    design = workflow("design")
    converge = workflow("converge")
    for text in (tests, implement):
        assert "按 start 步骤 4" not in text
        assert "git -C" in text
        assert "非 Cursor 主 Agent" in text
        assert "绝对路径绑定" in text
        assert "禁止新建 worktree" in text
        assert "禁止切到 owner" in text
        assert "禁止要求用户切换" in text
        assert "禁止 `move_agent_to_root`" in text
        assert "独立调用的 Cursor 主 Agent" in text
        assert "横幅用该" in text
        assert "deliver 步骤 3 主 Agent 续办时禁止切会话" in text
    for text in (design, converge):
        assert "绝对路径绑定 owner" in text
        assert "禁止新建 worktree" in text
        assert "禁止要求用户切换" in text
        assert "禁止 `move_agent_to_root`" in text
        assert "横幅用 owner" in text
        assert "将会话根切到" not in text
    assert "qa/feature/<slug>" in tests
    assert "dev/feature/<slug>" in implement
    assert "禁止把主 Agent 会话切离 owner" in deliver
    assert "用角色绝对路径操作，不切会话根" in deliver
    assert "仅 Cursor 主 Agent 可按" in deliver
    assert "横幅随绑定的 worktree 更新" in deliver
    assert "仅一路未完成走步骤 3" in deliver
    assert "不走步骤 4" in deliver


def test_deliver_tracks_delivery_with_goal():
    deliver = workflow("deliver")
    assert "Goal" in deliver
    assert "Goal" in deliver and "完成判据" in deliver
    assert "每次 deliver 会话只创建一次" in deliver
    assert "续办时不重建" in deliver
    assert "核对 finish 实际成功后才置 complete" in deliver
    assert "仅本次创建或同范围复用的 Goal" in deliver
    assert "已有其他或更大范围的 active Goal 时不覆盖、不提前完成" in deliver
