"""deliver intent 的持续推进、subagent 分派与 worktree 核验约束。"""
from conftest import skill_dir
from mdf_test_support import *  # noqa: F403


def workflow(name):
    return (skill_dir("mdf") / "references" / f"{name}.md").read_text()


def test_deliver_continues_until_actual_finish_and_preserves_approvals():
    text = workflow("deliver")
    for rule in (
        "只完成当前一个交付", "阶段完成 ─", "2 Select",
        "不结束 deliver", "需要用户决定时暂停", "已有有效确认继续适用",
        "步骤 5 必须取得 finish 的实际成功结果", "不会被 finish 删除的主 worktree",
        "不重放已经发生的发布操作", "release/hotfix 包含 finish 规定的 tag 与发版推送",
        "角色已集成并清理时读取 owner 的两路证据",
        "尚未存在本次交付时委托", "references/start.md",
        "$mdf deliver --auto-pilot", "$mdf deliver --yolo", "死硬阻塞才停止",
        "即将调用 `finish-gitflow` 之前", "不增加该关口", "跳过此关口",
        "位置参数至多一个", "自动分辨", "分不清就询问",
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
    assert "由 `$mdf deliver --auto-pilot` 委托时" in workflow("close-out")
    assert "不得自行调用 `finish-gitflow`" in workflow("close-out")
    assert "由 `$mdf deliver --yolo` 委托时" in workflow("close-out")
    assert "直接执行本步骤" in workflow("close-out")
    assert "不得将普通 next 自动升级为 deliver" in workflow("next")
    help_text = workflow("help")
    assert "$mdf deliver" in help_text
    assert "$mdf deliver --auto-pilot" in help_text
    assert "$mdf deliver --yolo" in help_text
    assert "$mdf deliver prp-001" in help_text


def test_deliver_requires_independent_subagents_and_verified_worktrees():
    text = workflow("deliver")
    for rule in (
        "必须分别交给 subagent，不由主 Agent 串行代做",
        "两路已有一条运行时", "不得重复创建执行者",
        "worktrees.qa", "worktrees.dev", "规范化后的 owner、qa、dev 路径必须两两不同",
        "worktree-check --repo <角色绝对路径> --owner <owner绝对路径>",
        "--design-commit <固定设计提交>", "--handoff",
        "主 Agent 分派前和 subagent 首次操作时都运行内部 CLI",
        "不得假设 subagent 继承主 Agent cwd", "不悄悄降级串行",
        "不在任一路仍运行时执行 converge 或删除角色 worktree",
        "tests（qa）或 implementation（dev）fingerprint", "同一可写 worktree 不并发派工",
        "code-review 内部按 roster.reviewers 启动独立 subagent",
        "design 与 converge 不走步骤 4",
        "由各 intent 自行启动恰好 1 个 owner",
        "仅一路未完成走步骤 3",
        "禁止把主 Agent 会话切离 owner",
        "禁止 `move_agent_to_root`",
        "用角色绝对路径操作，不切会话根",
        "仅 Cursor 主 Agent 可按",
        "横幅随绑定的 worktree/branch 更新",
    ):
        assert rule in text
