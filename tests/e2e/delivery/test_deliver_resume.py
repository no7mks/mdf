"""角色 worktree 清理后在 owner 上续办 converge。"""
from conftest import skill_dir
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def workflow(name):
    return (skill_dir("mdf") / "references" / f"{name}.md").read_text()


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
    assert status["worktrees"]["qa"][0]["path"] is None
    assert status["worktrees"]["dev"][0]["path"] is None
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
    assert "续办仍调用同一命令" in text
    assert "缺少有效记录却缺角色时停止" in text
