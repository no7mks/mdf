"""验证 Skill 的执行表、路由和副作用边界。"""

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
        "delivery-contract.md",
    }
    workflows = [p for p in documents if p.name not in nonprocedural]
    assert len(workflows) == 29
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
        if path.stem == "common":
            assert "## 决策树" not in text
        else:
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
    text = workflow("init")
    entry = text.split('<a id="s1"></a>', 1)[1].split('<a id="s2"></a>', 1)[0]
    assert "仅允许 initializing finding，或 ready 无 finding" in entry
    assert "用户明确“结束初始化并启用正常工作流”确认" in compact(text)


def test_finish_updates_facts_before_moving_materials():
    text = workflow("finish")
    prepare = text.split('<a id="s3"></a>', 1)[1].split('<a id="s4"></a>', 1)[0]
    assert prepare.index("references/fact-update.md") < prepare.index("move-change")
    assert "delivery check --stage fact-update" in prepare
    assert "- feature：" in prepare
    assert "- bugfix：" in prepare
    assert "- release：" in prepare
    assert "- hotfix：" in prepare
    assert "不要求 `docs/specs`、唯一 PRP 或 feature gate" in prepare


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
    assert table[3][5] == "已收口或 feature/bugfix 9；待收口 5"
    assert table[7][5] == "9"
    assert table[8][5] == "10"
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert "有写入" not in diagram and "无写入" not in diagram
    assert "preview" not in diagram and "预览" not in diagram
    assert "不提供预览模式" in text
    assert "仅预览或只读时" in text and "说明此入口不支持并停止" in text
    assert "--dry-run" not in text


def test_independent_intents_resolve_the_current_target_before_dispatch():
    entry = workflow("entry")
    dispatch = entry.split("### 目标与按需读取", 1)[1]
    assert "本次调用" in dispatch
    assert "rev-parse --show-toplevel" in dispatch
    assert "REPO_ROOT" in dispatch
    assert "不使用空值或上次调用的变量" in dispatch
    assert "clarify 与 help 不要求 Git 仓库" in dispatch
    assert "init/bootstrap" in dispatch and "普通目录" in dispatch
    assert "upgrade 解析 Git 根" in dispatch
    assert "不要求 manifest ready" in dispatch


def test_start_clarifies_feature_objectives_before_branch():
    text = workflow("start")
    table = rows(text)
    assert table[0][5] == "feature 2；其他 3"
    assert "内部 clarify" in table[1][3]
    assert table[1][5] == "3"
    assert table[1][6] == "不写目标，停止"
    assert "references/clarify.md" in text
    assert "assets/templates/objectives.md" in text
    assert "$mdf prp review" in text
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert re.search(r"其他种类通过 ─+→ 3 Start branch", diagram)
    assert re.search(r"feature 通过", diagram)


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
    assert "始终从基线建立相邻 worktree" in start
    assert "不在当前目录开分支" in start
    assert "write-tests 与 implement 后续都会依赖的共享代码底座" in design
    assert "底座未写入该基线则不得结束" in design
    assert "delivery worktree --role qa" in tests
    assert "不得在 feature 上编写或补写测试" in tests
    assert "delivery worktree --role dev" in implement
    assert "不得在 feature 上实现" in implement
    assert "不另开 worktree" not in tests
    assert "不另开 worktree" not in implement
    assert "始终从该设计基线建立或复用" in contract
    assert "两路不得各自再写底座" in contract


def test_initialization_and_init_have_explicit_reaudit_routes():
    shared = workflow("initialization")
    assert rows(shared)[6][6] == "事实变化 5；其他保留现场停止"
    assert rows(workflow("init"))[6][6] == "事实变化 6；其他保留现场停止"
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
    # 返回未通过仍允许 init 在当前审阅步骤修复；交付调用方继续使用失败出口。
    assert "可修复则重验" in rows(workflow("init"))[5][6]
    assert rows(workflow("fact-update"))[2][6] == "停止并报告"
    assert rows(workflow("finish"))[3][6] == "停止并交接"


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
    assert "事实及 evidence 问题由步骤 2–3 按范围处理" in entry
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
    assert table[0][5] == "有在途 2；无在途 3"
    assert table[0][6] == "澄清或报告阻塞"
    assert table[1][5] == "交接并结束"
    assert table[1][6] == "说明阻塞与操作后结束"
    assert "全部 MDF workflow" in text
    for name in ("init", "bootstrap", "intake", "prp review", "CodeWiki", "clarify"):
        assert name in text
    assert "不得在识别前统一要求 manifest ready 或 clean" in text
    assert "draft PRP、open Bug 或待办事项本身不代表流程已启动" in text
    assert "不把无法判定当作无在途而退回蓝图" in text
    assert "列出候选并询问用户选择" in text
    assert "不能仅凭文件存在或历史 passed 判断阶段完成" in text
    assert "不重复执行其工作" in text
    assert "不重做已验收且仍有效的操作" in text
    assert "next 不代替方案确认、初始化启用确认或原流程要求的 Git 操作授权" in text
    assert "一次 next 只续办一个所选 intent" in text
    assert "用户仅要求查看时保持只读" in text
    assert "仅确认没有在途流程时进入本分支" in text


def test_next_dispatch_allows_non_git_and_delegated_continuation():
    entry = workflow("entry")
    assert "除 init/bootstrap/next 外" in entry
    assert "允许续办尚未 Git 化的初始化与无需仓库的 clarify" in entry
    assert "next 可委托识别出的在途流程" in entry
    assert "显式 next 可按 `references/next.md` 委托续办" in workflow("common")
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
    assert "同会话" in text
    assert "提示在新会话" not in text
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert re.search(r"拒绝 ─+→ \[结束\]", diagram)
