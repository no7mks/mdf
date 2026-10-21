"""deliver intent 的持续推进、subagent 分派与 worktree 核验约束。"""
from conftest import skill_dir
from mdf_test_support import *  # noqa: F403


def workflow(name):
    return (skill_dir("mdf") / "references" / f"{name}.md").read_text()


def deliver_contract():
    return workflow("deliver") + workflow("deliver-policy")


def test_deliver_continues_within_scope_and_preserves_evidence():
    text = deliver_contract()
    for rule in (
        "只完成当前一个交付", "阶段完成 ─", "2 Select",
        "不结束 deliver", "需要用户决定时暂停", "已有有效确认继续适用",
        "步骤 5 必须取得 close-out 的实际成功结果", "不会被 close-out 删除的主 worktree",
        "不重放已经发生的发布操作", "release/hotfix 包含 close-out 规定的 tag 与发版推送",
        "角色已集成并清理时读取 owner 的两路证据",
        "尚未存在本次交付时委托", "references/start.md",
        "不可恢复的死硬阻塞仍停止", "位置参数至多一个", "自动分辨",
        "已有在途交付则报告错误并停止", "不续办、不重新 start",
        "不 start、不改绑", "记入本次剩余开发工作",
                "--qa-strategy", "--dev-strategy", "--review-strategy",
        "--write-tests-model", "--implement-model", "--code-review-model",
        "--roster", "已有交付再带 `--roster` 则停止", "原样转交细项",
        "不得把其他 intent 的模型写入本路任务",
        "口语描述", "可多个模型", "现场解析",
    ):
        assert rule in text
    for name, key in (
        ("write-tests", "write-tests"),
        ("implement", "implement"),
        ("code-review", "code-review"),
    ):
        body = workflow(name)
        assert f"含 `{key}`" in body
        assert "不得写入其他 intent 的模型" in body
        assert "按口语描述现场解析" in body
        assert "可多个模型" in body
    assert "不新增 deliver CLI、交付阶段 gate 或统一 workflow 状态文件" in text
    for name in ("start", "design", "write-tests", "implement", "converge", "code-review", "close-out"):
        assert f"references/{name}.md" in text
    for name in ("start", "design", "write-tests", "implement", "converge", "code-review"):
        assert "deliver 内部委托时完成后返回调用方" in workflow(name)
    assert "默认 deliver 不进入本 intent" in workflow("close-out")
    assert "低 confidence 返回 deliver 步骤 6" in workflow("close-out")
    assert "yolo 无 confidence 限制" in workflow("close-out")
    assert "直接执行本步骤" in workflow("close-out")
    assert "不得将普通 next 自动升级为 deliver" in workflow("next")
    help_text = workflow("help")
    assert "$mdf deliver" in help_text
    assert "$mdf deliver --stop-at close-out" in help_text
    assert "$mdf deliver --yolo" in help_text
    assert "$mdf deliver prp-0001" in help_text


def test_deliver_until_is_exclusive_and_checked_before_every_dispatch():
    text = deliver_contract()
    for rule in (
        "`--until <intent>` 与 `--stop-at <intent>` 是同一个 option",
        "exclusive，不执行该 intent", "默认 `--until close-out`",
        "不准备 close-out 材料、不执行其集成或 Gitflow",
        "`--yolo` 未显式指定 until 时无截止点；显式 until 仍生效",
        "缺值、未知 intent、重复指定", "写入或 start 之前完成解析",
        "多词 intent 须作为单个值传入", "不适用该路径的 intent 报参数错误",
        "可选阶段未启用时仍保留其顺序位置", "每次 Select、内部委托和并行分派前先核边界",
        "until implement 时可完成 write-tests，不启动 implement",
        "人工与 adhoc 的替代选择表同样受边界约束",
        "已到或超过截止点则只核验并报告", "until start 时仅解析与只读检查",
        "到 until 仅表示本次范围完成，不声称交付已收口",
        "不勾选被排除 intent", "不自动调用 next 或另开 deliver 越过截止点",
    ):
        assert rule in text
    table = text.split("| 交付路径 |", 1)[1].split("\n\n", 1)[0]
    assert "start（联调时内部 integrate）→ design → write-tests / implement → converge" in table
    assert "code-review → verify → fact audit → 必要时 fact update（内部 fact audit）→ close-out" in table
    assert "多词 intent 须作为单个值传入" in text
    assert "until fact update 可完成前置 audit，需要 update 时先停住" in text
    assert "audit 无须修复时也在 update 的顺序位置停住" in text
    assert "不把到达截止点当作 fact 已通过，不代勾 fact" in text
    for name in ("manual-feature", "adhoc", "adhoc-close-out", "close-out"):
        assert "until" in workflow(name), name


def test_deliver_decisions_use_confidence_without_low_score_fallback():
    text = deliver_contract()
    for rule in (
        "所有 deliver 默认启用本策略", "独立 intent 与普通 next 不受影响",
        "默认用 Jev `score` 计算 confidence", "有限数，范围 `[0,1]`",
        "无 Jev、认证/调用失败或结果缺失、越界、非有限数",
        "由主 Agent 计算并记录 confidence",
        "Jev 有效评分低于阈值时不得改用主 Agent 重新打高分",
        "`confidence >= 0.8` 自动确认", "`confidence < 0.8` 进入步骤 6",
        "无法形成有效评分时也进入步骤 6", "新证据、范围或方案变化时重新评分",
        "subagent 的新 decision 同样适用", "`--yolo` 无 confidence 限制：不要求评分",
        "内部 clarify、manual slug、squash、Gitflow 收口与收尾删除 worktree",
        "人工实际工作仍须由用户完成并显式勾选", "不增加固定 Gitflow 确认关口",
        "不覆盖用户明令禁止、关键事实缺失、外部条件与验收要求",
    ):
        assert rule in text
    for name in ("start", "design", "implement", "converge", "clarify", "squash", "close-out"):
        assert "confidence 策略" in workflow(name), name
    assert "非 yolo 的 deliver decision 请求用户确认" in workflow("common")


def test_deliver_policy_is_inherited_before_nested_intents_and_decisions():
    policy = workflow("deliver-policy")
    deliver = workflow("deliver")
    assert "references/deliver-policy.md" in deliver
    assert "references/deliver-policy.md" in workflow("common")
    for rule in (
        "边界包括嵌套 intent", "禁止用父 intent 包装来执行被排除的 intent",
        "until integrate 允许 start 建树", "until verify 也排除 converge、code-review",
        "manual 的 until fact audit 允许 fact update 对齐并提交事实页",
        "不把该返回当作失败，不重试或换另一入口继续",
        "所选 decision 满足目标与约束的 confidence", "不拿偏好或质量分替代",
        "低 confidence 不得交给其普通用户询问循环或强行自裁定",
        "子 intent/subagent 向 deliver 步骤 6 交出未决与精确 resume 位置",
    ):
        assert rule in policy
    assert "不打开通道或启动 poll" in workflow("start")
    assert "不进入 Audit、不自勾 fact update" in workflow("fact-update")
    assert "until write-tests 时两路都不分派" in policy
    assert "用原始分数比较，不四舍五入抬过阈值" in policy
    assert "任一路到 until" in deliver
    assert "先等其他已派写入者完成或暂停到可交接点" in deliver
    assert "deliver 自动确认记录评分、来源与依据" in workflow("fact-audit")
    assert "用户确认后 resume 同一 subagent" in deliver
    assert "端点、方案或范围已变化则重新评分" in deliver
    assert "只拒绝 squash 等可选操作时按原 intent 跳过" in deliver
    assert "步骤 3 的 Gitflow 关口" not in deliver
    assert "不排除 converge 内部的 smart" not in policy
    assert "close-out 尚未实际完成" in deliver
    assert "全勾但 Git 未完成也续办" in deliver


def test_deliver_public_contract_has_no_obsolete_mode():
    root = skill_dir("mdf")
    paths = [root / "SKILL.md", *sorted((root / "references").rglob("*.md"))]
    repo = root.parent.parent
    paths += [repo / "README.md", repo / "GLOSSARY.md"]
    paths += list((repo / "docs/system/interfaces").glob("mdf-cli*.md"))
    for path in paths:
        assert "--auto-pilot" not in path.read_text(), path
    for name in ("entry", "help"):
        path = root / "SKILL.md" if name == "entry" else root / "references/help.md"
        body = path.read_text()
        assert "deliver [<target>] [--until <intent>] [--yolo]" in body
        assert "--stop-at" in body


def test_deliver_requires_independent_subagents_and_verified_worktrees():
    text = workflow("deliver")
    for rule in (
        "必须分别交给 subagent，不由主 Agent 串行代做",
        "两路已有一条运行时", "不得重复创建执行者",
        "worktrees.qa", "worktrees.dev", "规范化后的 owner、qa、dev 路径必须两两不同",
        "worktree-check --repo <角色绝对路径> --owner <owner绝对路径>",
        "--design-commit <固定设计提交>", "--handoff",
        "主 Agent 分派前，以及 qa/dev 首次操作时运行内部 CLI",
        "不得假设 subagent 继承主 Agent cwd", "不悄悄降级串行",
        "不在任一路仍运行时执行 converge 或删除角色 worktree",
        "tests（qa）或 implementation（dev）内容是否已提交", "同一可写 worktree 不并发派工",
        "不以 gate 文件是否存在判定阶段完成",
        "code-review 内部按其契约的本轮应派人数启动独立 subagent",
        "design 与 converge 不走步骤 4",
        "由各 intent 自行启动恰好 1 个 owner",
        "仅一路未完成走步骤 3",
        "禁止把主 Agent 会话切离 owner",
        "禁止 `move_agent_to_root`",
        "用角色绝对路径操作，不切会话根",
        "仅 Cursor 主 Agent 可按",
        "横幅随绑定的 worktree 更新",
    ):
        assert rule in text
