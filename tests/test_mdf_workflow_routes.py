"""验证 Skill 的执行表、路由和副作用边界。

不拆分理由：路由契约按 intent 集中在单一文件，便于对照同一张执行表的
行断言；拆分会让同一 intent 的表格、决策树与文本约束分散到多文件。
"""

from __future__ import annotations

import re
import shlex
import unicodedata

from conftest import skill_dir

HEADER = "| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |"


def workflow(name: str) -> str:
    root = skill_dir("mdf")
    path = root / "SKILL.md" if name == "entry" else root / "references" / f"{name}.md"
    return path.read_text(encoding="utf-8")


def rows(text: str) -> list[list[str]]:
    return [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in text.splitlines()
        if re.match(r"^\| \d+ \|", line)
    ]


def compact(text: str) -> str:
    return "".join(text.split())


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def assert_branch_alignment(block, path):
    pattern = r"^(?P<prefix> +[├└]──── )(?P<condition>.*?) (?P<dash>─+)→ (?P<target>.+)$"
    branches = [
        (line, re.fullmatch(pattern, line))
        for line in block.splitlines() if re.match(r" +[├└]", line)
    ]
    assert branches and all(match for _, match in branches), path
    conditions, arrows, targets = set(), set(), set()
    longest = max(display_width(match["condition"]) for _, match in branches)
    has_main = bool(re.search(r"^\s*▼", block, re.MULTILINE))
    for index, (line, match) in enumerate(branches):
        conditions.add(display_width(line[:match.start("condition")]))
        arrows.add(display_width(line[:line.index("→")]))
        targets.add(display_width(line[:match.start("target")]))
        assert len(match["dash"]) == 4 + longest - display_width(match["condition"]), path
        corner = "└" if index == len(branches) - 1 and not has_main else "├"
        assert match["prefix"].lstrip().startswith(corner), path
    assert len(conditions) == len(arrows) == len(targets) == 1, path


def test_workflows_have_one_complete_table_and_matching_unicode_steps():
    root = skill_dir("mdf")
    documents = [root / "SKILL.md", *sorted((root / "references").glob("*.md"))]
    # 按文件职责识别范围，避免缺少执行表的流程从检查中消失。
    nonprocedural = {
        "repository-contract.md", "object-contract.md", "codewiki-contract.md",
        "delivery-contract.md", "common.md",
    }
    workflows = [p for p in documents if p.name not in nonprocedural]
    assert len(workflows) == 31
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
        diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
        boxes = re.findall(r"^│ (\d+) [A-Za-z][A-Za-z ]+│$", diagram, re.MULTILINE)
        assert boxes == numbers, path
        assert "▼" in diagram, path
        assert "┌" in diagram and "└" in diagram, path
        assert "+---" not in diagram and "---->" not in diagram, path
        assert re.search(r"[├└]──── ", diagram), path
        # 每个编号步骤都必须有分支，不能只画成功路径。
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
            sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in line) <= 120
            for line in text.splitlines()
        ), path


def test_archive_preview_is_terminal_and_apply_requires_non_preview():
    text = workflow("archive")
    table = rows(text)
    assert table[2][5] == "预览结束；否则 4"
    assert "不进入实际归档" in text
    assert "仅非预览调用授权运行" in text
    diagram = text.split("```text", 1)[1].split("```", 1)[0]
    assert re.search(r"预览成功 ─+→ \[展示预览并结束\]", diagram)
    assert "非预览" in diagram
    assert not re.search(r"预览成功 ─+→ 4", diagram)


def test_init_accepts_initializing_at_entry_before_readiness_gate():
    text = workflow("migrate")
    entry = text.split('<a id="s1"></a>', 1)[1].split('<a id="s2"></a>', 1)[0]
    assert "仅允许 initializing finding、" in entry
    assert "`manifest.schema` 与 `layout.migrate` finding，或 ready 无 finding" in entry
    assert "用户明确“结束初始化并启用正常工作流”确认" in compact(text)


def test_finish_updates_facts_before_preparing_materials():
    text = workflow("finish")
    prepare = text.split('<a id="s3"></a>', 1)[1].split('<a id="s4"></a>', 1)[0]
    assert prepare.index("references/fact-update.md") < prepare.index("- feature：")
    assert "delivery check --stage fact-update" in prepare
    assert "move-change" not in text
    assert "- feature：" in prepare
    assert "- bugfix：" in prepare
    assert "- release：" in prepare
    assert "- hotfix：" in prepare
    assert "材料不搬迁" in prepare
    assert "不要求 objectives、design、唯一 PRP 或 feature gate" in prepare
    assert "--scope full" not in prepare
    assert "release 的左端点为上一正式发布" in prepare


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


def test_finish_keeps_pending_closeout_on_the_release_path():
    text = workflow("finish")
    table = rows(text)
    assert table[3][5] == "已收口或 feature/bugfix→9；待收口→5"
    assert table[7][5] == "9"
    assert table[8][5] == "通过→10；feature/bugfix 前进→2"
    assert "其余前进或未过则停" in table[8][6]
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert "有写入" not in diagram and "无写入" not in diagram
    assert "preview" not in diagram and "预览" not in diagram
    assert "不提供预览模式" in text
    assert "仅预览或只读时" in text and "说明此入口不支持并停止" in text
    assert "--dry-run" not in text


def test_independent_intents_resolve_the_current_target_before_dispatch():
    dispatch = workflow("common").split("## 目标根", 1)[1]
    assert "本次调用" in dispatch
    assert "rev-parse --show-toplevel" in dispatch
    assert "REPO_ROOT" in dispatch
    assert "不使用空值或上次调用的变量" in dispatch
    assert "clarify 与 help 不要求 Git 仓库" in dispatch
    assert "init/bootstrap/migrate" in dispatch and "普通目录" in dispatch
    assert "upgrade 解析 Git 根" in dispatch
    assert "不要求 manifest ready" in dispatch


def test_start_clarifies_feature_objectives_before_branch():
    text = workflow("start")
    table = rows(text)
    assert table[0][5] == "feature 2；其他 3"
    assert "内部 clarify" in table[1][3]
    assert table[1][5] == "3"
    assert table[1][6] == "不写目标，停止"
    assert table[2][1] == "Confirm roster"
    assert table[2][2] == "约束"
    assert "member、strategy 与 models" in table[2][3]
    assert table[2][5] == "4"
    assert table[2][6] == "拒绝停止；未决留 3"
    assert table[3][1] == "Start branch"
    assert table[3][5] == "5"
    assert table[4][1] == "Switch worktree"
    assert table[4][2] == "约束"
    assert table[4][5] == "结束"
    assert table[4][6] == "留在 5 等待"
    assert "references/clarify.md" in text
    assert "assets/templates/objectives.md" in text
    assert "$mdf prp review" in text
    assert "qa_strategy" in text and "dev_strategy" in text
    assert "review_strategy" in text
    assert "未带的 intent 不写、不问、不提" in text
    assert "不得把沉默当作同意" in text
    assert "已锁定的 release 或 hotfix 上修复 Bug 不走本 intent" in text
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert re.search(r"其他种类通过 ─+→ 3 Confirm roster", diagram)
    assert re.search(r"feature 通过", diagram)
    assert re.search(r"3 Confirm roster", diagram)
    assert re.search(r"创建成功", diagram)
    assert re.search(r"4 Start branch", diagram)
    assert re.search(r"5 Switch worktree", diagram)


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
    assert "## 切换工作区" in common


def test_start_switches_agent_to_owner_worktree():
    text = workflow("start")
    assert "创建成功进入 5" in text
    assert "qa/dev 不在本步切换" in text
    assert "切换工作区" in text
    common = workflow("common")
    assert "move_agent_to_root" in common
    assert "move_agent_to_cloned_root" in common
    assert "New local worktree" in common
    assert "Create a new worktree" in common
    assert "File > Open Folder" in common
    assert "EnterWorktree" in common
    assert "git rev-parse --show-toplevel" in common
    assert "git branch --show-current" in common
    assert "不得再 `git worktree add`" in common
    assert "不得只在原根 `cd` 冒充已切换" in common


def test_implementation_handoff_distinguishes_checks_from_remaining_work():
    text = workflow("implement")
    assert text.index("逐项对照 objectives") < text.index("delivery record")
    assert "命令、退出状态、结果及对应验收项" in text
    assert "不要求测试先完成或项目全绿" in text
    assert "不记录通过的 implement gate" in text
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
    assert "不得因断言失败拒绝记录 gate" in tests
    assert "全绿由 converge 负责" in tests
    assert "不要求全绿" in contract
    assert "worktrees.dev" in implement
    assert "不得在 feature 上实现" in implement
    assert "merge-no-ff" in tests
    assert "merge-no-ff" in implement
    assert "delivery worktree" not in tests
    assert "delivery worktree" not in implement
    assert "入口先 no-ff merge owner" in contract
    assert "两路不得各自再写底座" in contract
    assert "全局 quick ∪ design policy `suites` 声明的交付 suite" in contract
    assert "关联 ≥1 个**已有**交付 suite" in contract
    assert "只跑了 quick" in contract
    assert "非 feature 分支变更 `verification.suites` 或新增交付 suite 名，一律需用户确认" in contract
    repo_contract = workflow("repository-contract")
    assert "`quick` 必须存在；`full` 隐含为全部项，不得声明" in repo_contract
    design_text = workflow("design")
    assert "验收到 quick 与本交付 suite 的映射" in design_text
    assert "suites" in design_text
    assert "按 design 把用例写入全局 quick 或 design policy `suites` 所列交付 suite" in tests
    converge = workflow("converge")
    assert "只跑 quick 或未声明/未跑本交付 suite 不得记录全绿" in converge
    assert "缺 suite 停并提示 `$mdf write-tests`" in converge
    assert "阻塞停止" in converge
    assert "missing_delivery_suite ────→ [停止，提示 $mdf write-tests]" in converge
    assert "返回 `missing_delivery_suite` 表示 design 声明的 suite 尚未写入" in converge
    assert "suite key 已建" in tests
    assert "记录 gate 前核对每个声明的\nkey 都已存在且非空" in tests
    assert "分层后 `delivery verify` / `project-verify` 证据必须含 `suites`，缺失视为过期" in contract
    assert "不得带 `suites`" in design_text
    assert "COLLECTIONS" not in (skill_dir("mdf") / "assets/templates/design.md").read_text()
    review = workflow("code-review")
    assert "必须尝试补一条 quick 复现用例" in review
    assert "quick 复现（已补 <用例位置>" in review
    assert "changes/unreleased/<slug>/suites.json" in review
    assert "`missing_delivery_suite`（缺 `suites.json`）时回步骤 1 补关联" in review
    assert "`unknown_suite`" in review and "询问用户是否新建" in review
    assert "suites.json" not in workflow("start")
    assert "交付级 suite" not in contract and "下沉" not in contract


def test_initialization_and_init_have_explicit_reaudit_routes():
    shared = workflow("initialization")
    assert rows(shared)[6][6] == "事实变化 5；其他保留现场停止"
    assert rows(workflow("migrate"))[6][6] == "事实变化 6；未确认则结束；否则停"
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
    assert rows(workflow("fact-update"))[2][6] == "停止并报告"
    assert rows(workflow("finish"))[3][6] == "未过则停止并交接"


def test_fact_update_checks_ready_before_writes_without_blocking_stale_facts():
    text = workflow("fact-update")
    entry = text.split("### 范围与写入边界", 1)[1].split("支持用户独立调用", 1)[0]
    assert rows(text)[0][6] == "写入前停止并报告"
    assert '任何写入或提交前运行 `doctor --repo "$REPO_ROOT"`' in entry
    for field in ("is_git_root: true", "initialized: true", "state: ready"):
        assert field in entry
    assert "独立调用与 finish 委托均须满足" in entry
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


def test_documented_archive_commands_work_from_outside_target(python_exe, tmp_path):
    from mdf_test_support import PRP_NAME, copy_fixture, git, init_git, mdf, payload, replace

    commands = re.findall(r'`(archive --repo [^`]+)`', workflow("archive"))
    assert len(commands) == 2
    repo = copy_fixture(tmp_path)
    proposal = repo / "docs/proposals" / PRP_NAME
    replace(proposal, "status: ready\ndepends_on: []",
            "status: rejected\ndepends_on: []\nreject-reason: wont-do")
    init_git(repo)
    for index, command in enumerate(commands):
        argv = [arg.replace("$REPO_ROOT", str(repo)).replace("$RELEASE_EPOCH", "1.2")
                for arg in shlex.split(command)]
        result = payload(mdf(python_exe, *argv, cwd=tmp_path))
        assert result["dry_run"] is (index == 0)
        assert result["validation"]["finding_count"] == 0
        if index == 0:
            assert proposal.is_file()
            assert not git(repo, "status", "--porcelain").stdout
        else:
            assert not proposal.exists()
            assert (repo / "docs/proposals" / "archive" / "1.2" / PRP_NAME).is_file()


def test_next_resumes_all_workflows_before_showing_blueprint():
    text = workflow("next")
    table = rows(text)
    assert table[0][5] == "feature/在途 2；无在途 3"
    assert table[0][6] == "多候选则问；证据不足则阻塞"
    assert table[1][5] == "交接并结束"
    assert table[1][6] == "不足则说明；失败按原流程交接"
    assert table[2][1] == "Delegate"
    assert table[2][5] == "结束"
    assert "全部 MDF workflow" in text
    for name in ("init", "bootstrap", "migrate", "intake", "prp review", "CodeWiki", "clarify"):
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
    assert "feature 交付步骤" in text
    assert "问号蓝图" not in text
    assert "$mdf next?" in text
    assert "由选择树路由到 tree" in text
    assert "只委托 tree" in text


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
    assert "未知 intent：" in text


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


def test_code_review_requires_three_full_reviews_before_owner_repairs():
    text = workflow("code-review")
    table = rows(text)
    assert table[1][2] == "Subagent"
    assert "按 roster.reviewers 启动独立 subagent" in table[1][3]
    assert table[1][5] == "3"
    assert table[3][6] == "缺 suite 则 1；可修则 3；否则停"
    for rule in (
        "不安排分工", "不共享其他审查者结论", "subagent 只读审查",
        "全部审查结果返回前不修改", "以证据裁定，不按票数决定",
        "不强制再次启动审查 subagent", "不足 roster.reviewers 个", "无法补齐则停止",
    ):
        assert rule in text


def test_code_review_covers_branch_starts_and_previous_release():
    text = workflow("code-review")
    for rule in (
        "delivery.json 的 start_commit", "mdf-start-commit",
        "上一正式发布版本的 master commit/tag", "首次发布没有上一版本",
        "git diff <base_commit> <review_head>", "基线必须是当前 HEAD 的祖先",
        "git diff <previous_final_head> <review_head>",
        "changes/unreleased/<slug>/code-review.md",
        "不取 master 合回 develop 的合并提交", "不重新追随分支或 tag",
        "bugfix/hotfix/release 不要求 feature 的 design/converge gate",
        "按当前分支执行所需 suite", "最终 final_head",
    ):
        assert rule in text
    finish = workflow("finish")
    assert "develop...HEAD" not in finish and "master...HEAD" not in finish
    assert "四种分支均须有完整且有效的 roster.reviewers 份独立审查" in finish
    assert "Agent 按已确认目标、设计及两侧改动自动尝试 resolve" in finish
    assert "都以集成后的 HEAD 执行增量新一轮" in finish
    assert "不复用集成前报告" in finish
    assert "复核上轮问题" in finish
    assert "证据缺失或过期时内部执行 code-review" in finish


def test_role_intents_do_not_reuse_owner_session_switch():
    tests = workflow("write-tests")
    implement = workflow("implement")
    deliver = workflow("deliver")
    for text in (tests, implement):
        assert "按 start 步骤 4" not in text
        assert "git -C" in text
        assert "move_agent_to_root" in text
        assert "禁止 `move_agent_to_cloned_root`" in text
        assert "deliver 步骤 3 主 Agent 续办时禁止切会话" in text
        assert "禁止切到 owner" in text
    assert "qa/feature/<slug>" in tests
    assert "dev/feature/<slug>" in implement
    assert "禁止把主 Agent 会话切离 owner" in deliver
    assert "仅一路未完成走步骤 3" in deliver
    assert "不走步骤 4" in deliver


def test_deliver_tracks_delivery_with_goal():
    deliver = workflow("deliver")
    assert "锁定一次交付及 owner worktree，创建 Goal" in deliver
    assert "objective 写明交付标识与完成判据" in deliver
    assert "每次 deliver 会话只创建一次" in deliver
    assert "续办时不重建" in deliver
    assert "核对 finish 实际成功后才置 complete" in deliver
    assert "完成 Goal 并报告" in deliver


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
    assert rows(workflow("codewiki-recovery"))[4][2] == "脚本"  # 移出为文件操作


def test_init_dispatches_to_bootstrap_or_migrate():
    text = workflow("init")
    table = rows(text)
    assert table[0][5] == "2"
    assert table[1][3] == "内部执行 bootstrap 或 migrate"
    assert table[1][5] == "结束"
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert re.search(r"未就绪的新项目 ─+→ \[内部执行 bootstrap 并返回\]", diagram)
    assert re.search(r"已有事实或已 ready ─+→ \[内部执行 migrate 并返回\]", diagram)
    assert "references/bootstrap.md" in text
    assert "references/migrate.md" in text
    assert "`$mdf init migrate`" in text
    migrate = workflow("migrate")
    assert re.search(r"未就绪的新项目 ─+→ \[停止并提示 bootstrap\]", migrate.split(
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
    assert "必须运行 doctor" in migrate
    assert "可运行 doctor" not in migrate
    table = rows(migrate)
    assert table[0][2] == "约束"
    assert table[0][3] == "只读判定分流"


def test_jot_promote_revalidates_without_rewriting():
    jot = workflow("jot")
    assert "不重写对象" in jot
    assert "在步骤 7 已写入的 draft/open 上" in jot
    assert "Proposal 转为 `ready`；Bug 保持 `open`" in jot
    assert "回滚到\n步骤 7 完成状态" in jot
    table = rows(jot)
    assert (table[4][1], table[4][2]) == ("Clarify", "约束")
    assert "首次保留；二次回滚停止" in table[7][6]


def test_clarify_unavailable_facts_stop_like_cancel():
    table = rows(workflow("clarify"))
    assert "不可得" in table[2][6]
    assert "取消或不可得则停" in table[2][6] and "取消或失败则停" in table[1][6]
