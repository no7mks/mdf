"""持续交付契约、并行路径绑定和集成后续办。"""

from conftest import skill_dir
from mdf_test_support import *  # noqa: F403
from test_mdf_delivery import setup_delivery, sync_roles, record, commit


def workflow(name):
    return (skill_dir("mdf") / "references" / f"{name}.md").read_text()


def test_deliver_continues_until_actual_finish_and_preserves_approvals():
    text = workflow("deliver")
    for rule in (
        "只完成当前一个交付", "阶段完成 ─", "2 Select",
        "不结束 deliver", "需要用户决定时暂停", "已有有效确认继续适用",
        "步骤 5 必须取得 finish 的实际成功结果", "不会被 finish 删除的主 worktree",
        "不重放已经发生的发布操作", "release/hotfix 包含 finish 规定的 tag 与发版推送",
        "没有独立开发 intent 的剩余工作由主 Agent", "角色已集成并清理时读取 owner 的两路证据",
    ):
        assert rule in text
    assert "不新增 CLI command、gate 或统一 workflow 状态文件" in text
    for name in ("start", "design", "write-tests", "implement", "converge", "code-review", "finish"):
        assert f"references/{name}.md" in text
    for name in ("design", "write-tests", "implement", "converge", "code-review"):
        assert "deliver 内部委托时完成后返回调用方" in workflow(name)
    assert "不得将普通 next 自动升级为 deliver" in workflow("next")
    assert "$mdf deliver" in workflow("help")


def test_deliver_requires_independent_subagents_and_verified_worktrees():
    text = workflow("deliver")
    for rule in (
        "必须分别交给 subagent，不由主 Agent 串行代做",
        "两路已有一条运行时", "不得重复创建执行者",
        "worktrees.qa.path", "worktrees.dev.path", "规范化后的 owner、qa、dev 路径必须两两不同",
        "git rev-parse --show-toplevel", "git branch --show-current",
        "git rev-parse --path-format=absolute --git-common-dir",
        "git merge-base --is-ancestor <design_commit> HEAD",
        "主 Agent 分派前和 subagent 首次操作时都必须核对",
        "不得假设 subagent 继承主 Agent cwd", "不悄悄降级串行",
        "不在任一路仍运行时执行 converge 或删除角色 worktree",
        "tests（qa）或 implementation（dev）指纹", "同一可写 worktree 不并发派工",
        "code-review 内部仍强制 3 个 subagent 同范围只读审查",
    ):
        assert rule in text


def test_converge_can_resume_from_owner_after_role_cleanup(python_exe, tmp_path):
    owner, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, owner)
    common_dir = git(owner, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    assert len({owner.resolve(), qa.resolve(), dev.resolve()}) == 3
    for path, stage, branch in (
        (qa, "write-tests", "qa/feature/service-health"),
        (dev, "implement", "dev/feature/service-health"),
    ):
        assert Path(git(path, "rev-parse", "--show-toplevel").stdout.strip()).resolve() == path.resolve()
        assert git(path, "branch", "--show-current").stdout.strip() == branch
        assert git(path, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip() == common_dir
        payload(record(python_exe, path, stage))
        commit(path)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(owner)))
    assert not qa.exists() and not dev.exists()
    # 模拟集成清理后、全绿之前的中断；续办仅检查已集成的证据，不再次 integrate。
    status = payload(mdf(python_exe, "delivery", "status", "--repo", str(owner)))["result"]
    assert status["worktrees"]["qa"]["path"] is None
    assert status["worktrees"]["dev"]["path"] is None
    current = payload(mdf(python_exe, "delivery", "check", "--repo", str(owner),
                          "--stage", "converge"))["result"]
    for stage in ("write-tests", "implement"):
        gate = json.loads((root / "gates" / f"{stage}.json").read_text())
        assert gate["fingerprints"]["design"] == current["design"]
        git(owner, "merge-base", "--is-ancestor", gate["head"], "HEAD")
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(owner)))
    payload(record(python_exe, owner, "converge"))
    assert (root / "gates/converge.json").is_file()
    assert not qa.exists() and not dev.exists()
    text = workflow("converge")
    assert "通过后跳过 integrate" in text
    assert "仅部分角色缺失或无法证明已集成时停止" in text
