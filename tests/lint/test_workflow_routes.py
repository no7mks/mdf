"""intent 文档的决策树、步骤表与路由约束。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from types import SimpleNamespace
import re
import shlex
import unicodedata
from conftest import skill_dir
from support_routes import *  # noqa: F403

def test_mdf_clarify_delegates_or_clarifies_until_shared_understanding():
    skill = skill_dir("mdf")
    clarify = (skill / "references" / "clarify.md").read_text(encoding="utf-8")
    create = (skill / "references" / "prp-create.md").read_text(
        encoding="utf-8"
    )
    review = (skill / "references" / "prp-review.md").read_text(
        encoding="utf-8"
    )
    migrate = (skill / "references" / "migrate.md").read_text(encoding="utf-8")
    start = (skill / "references" / "start.md").read_text(encoding="utf-8")
    assert "系统 `grilling` skill" in clarify
    assert "委托它对议题执行压力测试" in clarify
    assert "问法由 grilling 规定" in clarify
    assert "不可用时由本 intent 的步骤 3 本地澄清" in clarify
    assert "调用方只提供议题与必须落地的事实" in clarify
    assert "提问限制" not in clarify
    assert "一次一个问题" not in clarify
    assert "报告该失败并停止" in clarify
    assert "不可用时进入 3" in clarify
    assert "等待回答后更新已确认决定与剩余疑问" in clarify
    assert "不得把未回答视为同意" in clarify
    assert "无未决疑问及用户明确确认" in clarify
    assert "用户取消、暂停或关键事实无法获得时列出未决项并停止" in "".join(
        clarify.split()
    )
    assert "内部 clarify intent" in create
    assert "内部 clarify intent" in review and "内部 clarify intent" in migrate
    assert "内部 clarify intent" in start
    fix = (skill / "references" / "fix.md").read_text(encoding="utf-8")
    assert "内部执行 `references/clarify.md`" in fix
    assert "`--yolo` 时主 Agent 依据仓库证据与 Bug" in fix
    assert "不由 deliver 内部委托" in fix
    assert "未记录有效红灯不得改生产实现" in fix
    verify_fix = (skill / "references" / "bug-close.md").read_text(
        encoding="utf-8"
    )
    assert "只要求这些复现用例通过" in verify_fix
    assert "不调用 `$mdf code-review`" in verify_fix
    assert "导入错误、编译失败或环境故障不算有效红灯" in fix
    assert "明确确认才转" in review

def test_workflows_have_one_complete_table_and_matching_unicode_steps():
    root = skill_dir("mdf")
    documents = [root / "SKILL.md", *sorted((root / "references").glob("*.md"))]
    # 按文件职责识别范围，避免缺少执行表的流程从检查中消失。
    nonprocedural = {
            "repository-contract.md", "object-contract.md", "doc-structure.md", "html-materials.md",
            "project-rules.md",
    }
    workflows = [p for p in documents if p.name not in nonprocedural]
    assert len(workflows) == 51
    assert not (root / "intents").exists()
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        assert text.count(HEADER) == 1, path
        assert text.count("## 工作流（唯一执行契约）") == 1, path
        assert "```mermaid" not in text, path
        assert not re.search(r"^\d+\. \*\*", text, re.MULTILINE), path
        table = rows(text)
        numbers = [str(i) for i in range(1, len(table) + 1)]
        assert [row[0] for row in table] == numbers, path
        assert all(len(row) == 7 and all(row) for row in table), path
        assert all(row[2] in {"脚本", "Subagent", "约束"} for row in table), path
        if "树形：not-tree。" in text:
            assert "## 决策树" not in text and "## 选择树" not in text, path
        else:
            diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
            boxes = re.findall(r"^│ (\d+) [A-Za-z][A-Za-z ]+│$", diagram, re.MULTILINE)
            assert boxes == numbers, path
            assert "▼" in diagram, path
            assert "┌" in diagram and "└" in diagram, path
            assert "+---" not in diagram and "---->" not in diagram, path
            assert re.search(r"[├└]──── ", diagram), path
            blocks = re.split(r"^│ \d+ [A-Za-z][A-Za-z ]+│$", diagram,
                              flags=re.MULTILINE)[1:]
            assert all(re.search(r"[├└]──── ", block) for block in blocks), path
            for block in blocks:
                assert_branch_alignment(block, path)
        for target in re.findall(r"\]\(#([^)]*)\)", text):
            assert f'<a id="{target}"></a>' in text, (path, target)
        for target in re.findall(r"references/[a-z-]+\.md", text):
            assert (root / target).is_file(), (path, target)
        assert all(
            sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in line) <= 180
            for line in text.splitlines()
        ), path

def test_archive_preview_is_terminal_and_apply_requires_non_preview():
    text = workflow("archive")
    table = rows(text)
    assert table[2][5] == "预览结束；非预览 4"
    assert "不进入实际归档" in text
    assert "仅非预览调用授权运行" in text
    diagram = text.split("```text", 1)[1].split("```", 1)[0]
    assert re.search(r"预览成功 ─+→ \[展示预览并结束\]", diagram)
    assert "非预览" in diagram
    assert not re.search(r"预览成功 ─+→ 4", diagram)

def test_init_accepts_initializing_at_entry_before_readiness_gate():
    text = workflow("migrate")
    entry = text.split('<a id="s1"></a>', 1)[1].split('<a id="s2"></a>', 1)[0]
    assert "doctor finding 不是拒绝理由" in entry
    assert "全部 finding 记入盘点清单，由步骤 3 逐项处置" in entry
    assert "`path.symlink`）报告后停止" in entry
    assert "用户明确“结束初始化并启用正常工作流”确认" in compact(text)

def test_codewiki_requires_verified_close_and_recoverable_failure():
    update = workflow("codewiki-update")
    generate = workflow("codewiki-generate")
    recovery = workflow("codewiki-recovery")
    contract = workflow("codewiki-contract")
    for text in (update, generate):
        assert "references/codewiki-recovery.md" in text
        assert "关闭前先验收" in text
        assert "不得推进基线" in text
    assert "关闭后Wikidiff为空" in compact(update)
    assert "未写页面时只关闭会话并清理workspace" in compact(contract)
    assert "已部分写入时不调用 `close_session`" in recovery
    assert "不开始另一次增量更新" in recovery
    assert "用户指定的仓外备份位置" in compact(recovery)
    assert "取得针对具体源和目标的明确确认" in recovery
    assert "搬移后不得再调用该 session 的写入或关闭工具" in recovery
    assert "显式`$mdfcodewikigenerate`" in compact(recovery)
    assert "不重新路由回 update" in recovery
    assert "没有hack且无页时跳过写入" in compact(update)

def test_independent_intents_resolve_the_current_target_before_dispatch():
    dispatch = workflow("common").split("## 目标根", 1)[1]
    assert "本次调用" in dispatch
    assert "rev-parse --show-toplevel" in dispatch
    assert "REPO_ROOT" in dispatch
    assert "不使用空值或上次调用的变量" in dispatch
    assert "clarify 与 help 不要求 Git 仓库" in dispatch
    assert "init/bootstrap/migrate" in dispatch and "普通目录" in dispatch
    assert "upgrade 解析 Git 根" in dispatch
    assert "sync 解析 Git 根" in dispatch
    assert "不要求 manifest ready" in dispatch

def test_callers_do_not_prescribe_questioning_style():
    forbidden = (
        "一次只问一个问题",
        "一次只问一个消歧问题",
        "逐题",
        "按轮次",
        "提问限制",
        "按限制委托",
        "一次一个问题",
        "对每个非生态必需",
    )
    root = skill_dir("mdf")
    paths = [
        root.parents[1] / "README.md",
        root / "SKILL.md",
        *sorted((root / "references").glob("*.md")),
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, f"{path.name} contains {phrase!r}"

def test_planning_intents_use_shared_planning_workspace():
    for name in ("prp-create", "prp-review", "intake", "prp-split"):
        text = workflow(name)
        assert "planning ensure" in text
        assert "切换工作区" in text
    jot = workflow("jot")
    assert "planning ensure" in jot
    assert "切换工作区" in jot
    common = workflow("common")
    assert "`planning` 分支" in common
    assert "planning land" in common
    assert "### 切换工作区" in common

def test_initialization_and_init_have_explicit_reaudit_routes():
    shared = workflow("initialization")
    assert rows(shared)[6][6] == "全量无效返回补验；事实变化重审；其他停"
    assert rows(workflow("migrate"))[6][6] == "补验或事实变化 6；未确认则结束；否则停"
    assert "bootstrap 不调用 fact audit" in shared
    assert "用户明确“结束初始化并启用正常工作流”确认" in shared

def test_fact_audit_failure_returns_without_advancing_the_caller():
    text = workflow("fact-audit")
    assert "unverified" not in text
    assert rows(text)[6][6] == "报告未通过；独立结束，委托返回"
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert re.search(r"未通过且独立调用 ─+→ \[报告未通过并结束\]", diagram)
    assert re.search(r"未通过且内部委托 ─+→ \[返回未通过，调用方走失败分支\]", diagram)
    result = compact(text.split('<a id="s7"></a>', 1)[1])
    for condition in ("存在其他finding", "未确认warning", "未取得用户确认"):
        assert condition in result
    assert "阻断原因与待确认项" in result
    assert "不得推进依赖审阅通过的步骤" in result
    assert "不自行修复或自动重试" in result
    # 返回未通过仍允许 migrate 在当前审阅步骤修复；交付调用方继续使用失败出口。
    assert "可修复则重验" in rows(workflow("migrate"))[5][6]
    assert rows(workflow("fact-update"))[2][5] == "通过或仅结构则 4"
    assert rows(workflow("fact-update"))[2][6] == "其他未通过或验证失败则停"
    assert rows(workflow("close-out"))[3][6] == "未过则停止并交接"

def test_bug_create_checks_ready_without_blocking_stale_docs():
    text = workflow("bug-create")
    assert rows(text)[0][3] == "运行 `doctor`，核对已初始化"
    assert rows(text)[0][6] == "未就绪则停"
    assert "不将 `normal_workflows_allowed: true` 作为前置条件" in text
    assert "evidence.stale" in text
    assert "其他 findings 报告后停止" not in text

def test_fact_update_checks_ready_before_writes_without_blocking_stale_facts():
    text = workflow("fact-update")
    entry = text.split("### 范围与写入边界", 1)[1].split("支持用户独立调用", 1)[0]
    assert rows(text)[0][6] == "写入前停止并报告"
    assert '任何写入或提交前运行 `doctor --repo "$REPO_ROOT"`' in entry
    for field in ("is_git_root: true", "initialized: true", "state: ready"):
        assert field in entry
    assert "独立调用与主链委托均须满足" in entry
    assert "不写入、不提交" in entry
    assert "不将 `normal_workflows_allowed: true` 作为前置条件" in entry
    assert "事实及 evidence 问题由步骤 2–4 按范围处理" in entry
    assert "写入分支按 `common.md` 的归属规则检查" in entry
    assert "独立调用仅记录 `branch.invalid`" not in entry

def test_codewiki_commit_failure_does_not_rebuild_verified_output():
    for name in ("codewiki-generate", "codewiki-update"):
        text = workflow(name)
        final_step = rows(text)[-1]
        assert "仅提交失败停止" in final_step[6]
        diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
        assert re.search(r"仅提交失败 ─+→ \[保留已验收 Wiki，报告并停止\]", diagram)
        assert "MCP 失败或输出验收失败进入 recovery" in text
        assert "输出验收通过后仅 Git 暂存或提交失败时" in text
        assert "不得因此进入 recovery、搬移 Wiki 或重新生成" in text
        assert "同次续办先核对输出与 diff 未变且验收仍有效" in text
    assert "输出已验收且仅 Git 暂存或提交失败" in workflow("codewiki-recovery")

def test_tree_renders_diagram_in_fence_and_index_as_table():
    text = workflow("tree")
    table = rows(text)
    assert table[2][1] == "Render tree"
    assert table[2][2] == "约束"
    assert "text 围栏" in table[2][3] and "表格" in table[2][3]
    assert "text 围栏块" in text
    assert "不得放入围栏块" in text
    assert "不得改画成 json" in text
    assert "不得再展示 `index` JSON" in text
    assert "仍含表头与 `hidden:` 行" in text

def test_next_resumes_all_workflows_before_showing_blueprint():
    text = workflow("next")
    table = rows(text)
    assert table[0][5] == "在途 2；无在途 3"
    assert table[0][6] == "多候选则问；证据不足则阻塞"
    assert table[1][5] == "查看或不足则说明；可推进则执行"
    assert table[1][6] == "按原流程交接"
    assert table[2][1] == "Delegate"
    assert table[2][5] == "结束"
    assert "全部 MDF workflow" in text
    for name in (
        "init", "bootstrap", "migrate", "intake", "prp review", "CodeWiki",
        "clarify", "fix", "bug close",
    ):
        assert name in text
    assert "不得在识别前统一要求 manifest ready 或 clean" in text
    assert "draft PRP、open Bug 或待办事项本身不代表流程已启动" in text
    assert "也不把无法判定当作无在途而委托 tree" in text
    assert "列出候选并询问用户选择" in text
    assert "不能仅凭文件存在或历史 passed 判断阶段完成" in text
    assert "不重复执行其工作" in text
    assert "不重做已验收且仍有效的操作" in text
    assert "next 不代替方案确认、初始化启用确认或原流程要求的 Git 操作授权" in text
    assert "一次 next 只续办一个所选 intent" in text
    assert "用户仅要求查看时保持只读" in text
    assert "Gitflow 交付分支（含角色分支）" in text
    assert "问号蓝图" not in text
    assert "$mdf next?" in text
    assert "由选择树路由到 tree" in text
    assert "只委托 tree" in text
    assert "需要且通道未打开时先 `$mdf integrate`" in text
    assert "双端验收且确认不再改代码后才委托 code-review" in text

def test_next_dispatch_allows_non_git_and_delegated_continuation():
    entry = workflow("entry")
    common = workflow("common")
    assert "除 init/bootstrap/migrate/next 外" in common
    assert "允许续办尚未 Git 化的初始化与无需仓库的 clarify" in common
    assert "next 可委托识别出的在途流程" in entry
    assert "一次 next 只续办一个所选 intent" in workflow("next")
    assert "显式调用 next 委托下一阶段" in workflow("delivery-contract")

def test_help_catalog_is_grouped_and_read_only():
    text = workflow("help")
    for heading in ("起步", "规划", "交付", "维护"):
        assert f"#### {heading}" in text
    assert "不读取 `references/` 中的其他流程" in text
    assert "不调用 CLI" in text
    assert "不得改写" in text
    assert "$mdf help <intent>" in text
    assert "$mdf upgrade" in text
    assert "$mdf to <target>" in text
    assert "$mdf sync" in text
    assert "未知 intent：" in text

def test_to_resolves_planning_aliases_and_enters_worktree():
    text = workflow("to")
    table = rows(text)
    assert [row[1] for row in table] == [
        "Resolve target", "Ensure worktree", "Enter workspace",
    ]
    assert "planning ensure" in text
    assert "plan-mode" in text
    assert "to --repo" in text
    assert "develop" in text
    assert "切换工作区" in text
    assert "不创建新的交付分支" in text
    assert "空目标" in text

def test_common_banner_and_non_cursor_use_bound_worktrees():
    common = workflow("common")
    entry = workflow("entry")
    banner = "<logo_emoji> <main-repo-name>@<worktree-path>"
    assert "references/common.md" in entry and "s-banner" in entry
    for text in (common,):
        assert banner in text
        assert "不得在回复开头打印" in text
        assert "等待用户回复" in text
        assert "不再重复" in text
        assert "没有上一处横幅时不打印切换三行" in text
        assert "git 主工作区" in text
        assert "<main-repo-name>-worktrees/" in text
        assert "保留完整层级" in text
        assert "顶层 `logo`" in text
        assert "<branch>" not in text
        assert "worktree 或 branch 变化" not in text
        assert "每次回复只在第一行打印" not in text
        assert "不得在回复末尾再打印" not in text
    assert "禁止要求用户切换" in common
    assert "git -C <路径>" in common

def test_integrate_forces_goal_and_never_stops_poll():
    text = workflow("integrate")
    mode = next(line for line in text.splitlines() if line.startswith("| collab-mode |"))
    assert mode.split("|")[2].strip() == "不打开"
    assert (skill_dir("mdf") / "references/collab-mode.md").is_file()
    assert "同 worktree（同仓）" in text
    assert "跨 worktree（跨仓）" in text
    assert "不 init、不 poll、不 listen、不 send" in text
    assert "强制 Goal" in text
    assert "Goal 完成前，用户没让你停，永远不许停下来" in text
    assert "正在等待：对端 ack" in text
    assert "--kind courtesy" in text
    assert "--kind ack" in text
    assert "integrate init" in text
    assert "不得主动停止 poll" in text
    assert "一个 agent 只准 poll 本侧" in text
    assert "stdout 只打可读行" in text
    assert "正文单独成行" in text
    assert "不得再启动对端" in text
    assert "不得写入或修改对端仓库" in text
    assert "不得操作、启动或终止对端的进程或服务" in text
    assert "可以启动本侧联调所需的依赖" in text
    assert "不得改、操作、启动或终止对端" in text
    assert "15、30、45、60 秒" in text
    assert "60 秒为上限" in text
    assert "补覆盖" in text
    assert "delivery-contract.md" in text
    assert "正在等待：" in text
    assert "heartbeat" in text
    assert "每等待 1 分钟" in text
    assert "收口完成不是停止理由" in text or "都不是停止理由" in text
    assert "语义结束或用户停止时才停掉" not in text

def test_prettify_requires_structure_instead_of_suggestions():
    pretty = workflow("prettify")
    structure = workflow("doc-structure")
    assert "不得当作可选审阅" in pretty
    assert "必须按原文形态改写" in pretty
    assert "必须改写为" in pretty
    assert "必须按表组织" in structure
    assert "必须写成" in structure
    assert "不得当作可忽略建议" in structure

def test_upgrade_previews_then_confirms_before_replace():
    text = workflow("upgrade")
    table = rows(text)
    assert table[1][5] == "3"
    assert table[2][5] == "4"
    assert "拒绝则结束" in table[2][6]
    assert "http://10.1.5.65:8929/mars/mdf" in text
    assert "不读取 `references/common.md`" in text
    assert "AGENTS.md" in text
    assert "托管区块" in text
    assert "`agents`" in text
    assert "`history`" in text
    assert "提交摘要" in text
    assert "不 push" in text
    assert "提交本次路径" in text
    assert "不自动提交" not in text
    assert "重读" in text
    assert "建议用户运行 `$mdf migrate`" in text
    assert "`$mdf fact update --scope full`" in text
    assert "同会话" in text
    assert "提示在新会话" not in text
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert re.search(r"拒绝 ─+→ \[结束\]", diagram)

def test_codewiki_session_is_created_by_analyze_repo():
    for name in ("codewiki-generate", "codewiki-update"):
        text = workflow(name)
        assert "通过后建立 MCP session" not in text
        assert "再建立 MCP session" not in text
        assert "session 由 `analyze_repo` 创建" in text
        assert "不得另调建 session 工具" in text
        assert "调用 `analyze_repo` 创建 session" in text
    generate = workflow("codewiki-generate")
    assert "读取 workspace 的 `component_index.json`、`leaf_nodes.json`、`languages.json`、`summary.json`" in generate
    assert "save_module_tree` 并读取其写出的 `processing_order.json`" in generate
    assert rows(workflow("codewiki-recovery"))[4][2] == "约束"  # 搬移为确认后的文件操作

def test_init_dispatches_to_bootstrap_or_migrate():
    text = workflow("init")
    table = rows(text)
    assert table[0][5] == "2"
    assert table[1][3] == "内部执行 bootstrap 或 migrate"
    assert table[1][5] == "按选择树结束"
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert re.search(r"未就绪、无事实且符合契约 ─+→ \[内部执行 bootstrap 并返回\]", diagram)
    assert re.search(r"已有事实或已 ready ─+→ \[内部执行 migrate 并返回\]", diagram)
    assert "references/bootstrap.md" in text
    assert "references/migrate.md" in text
    assert "`$mdf init migrate`" in text
    migrate = workflow("migrate")
    assert re.search(r"未就绪、无事实且符合契约 ─+→ \[停止并提示 bootstrap\]", migrate.split(
        "```text\n", 1
    )[1].split("```", 1)[0])
    assert "或 init 依据公共分流规则的内部委托" in migrate
    assert "`$mdf init migrate`" in migrate

def test_init_entry_is_read_only_and_existing_git_runs_doctor():
    table = rows(workflow("init"))
    assert table[0][2] == "约束"
    assert table[0][3] == "只读判定分流"
    text = workflow("init")
    assert "转入前不写入 `.git/`" in text
    assert "内部执行 bootstrap 或 migrate" in text
    migrate = workflow("migrate")
    assert "入口一律运行 doctor" in migrate
    assert "可运行 doctor" not in migrate
    table = rows(migrate)
    assert table[0][2] == "约束"
    assert table[0][3] == "只读判定分流"

def test_jot_promote_revalidates_without_rewriting():
    jot = workflow("jot")
    assert "不重写对象" in jot
    assert "在步骤 7 已写入的 draft/open 上" in jot
    assert "Proposal 保持 `draft`，Bug 保持 `open`" in jot
    assert "回滚到\n步骤 7 完成状态" in jot
    table = rows(jot)
    assert (table[4][1], table[4][2]) == ("Clarify", "约束")
    assert "复验保留；校验恢复；land 失败留现场" == table[7][6]

def test_clarify_unavailable_facts_stop_like_cancel():
    table = rows(workflow("clarify"))
    assert "不可得" in table[2][6]
    assert "取消或不可得则停" in table[2][6] and "取消或失败则停" in table[1][6]
