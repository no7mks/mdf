"""唯一 MDF Skill 的入口与内部工作流契约测试。"""

from __future__ import annotations

from conftest import skill_dir


def workflow(name: str) -> str:
    return (skill_dir("mdf") / "workflows" / f"{name}.md").read_text(
        encoding="utf-8"
    )


def test_mdf_is_the_only_public_skill_and_dispatches_commands() -> None:
    skill = skill_dir("mdf")
    entry = (skill / "SKILL.md").read_text(encoding="utf-8")

    assert [path.name for path in skill.parent.iterdir() if path.is_dir()] == [
        "mdf"
    ]
    for command in (
        "init-repo",
        "start",
        "review-doc",
        "finish",
        "audit",
        "archive",
        "grill <议题>",
    ):
        assert command in entry
    assert "裸 `$mdf`" in entry
    assert "workflows/<command>.md" in entry


def test_init_and_review_load_internal_contracts() -> None:
    init = workflow("init-repo")
    review = workflow("review-doc")

    assert "repository-contract.md" in init
    assert "workflows.md" in init
    assert "完整写入方案" in init
    assert "再次显式调用 `$mdf init-repo`" in init
    assert "object-contract.md" in review
    assert "内部 grill 工作流" in review
    assert "closed 或 archive 对象拒绝修改" in review


def test_start_and_finish_define_strict_gitflow_operations() -> None:
    start = workflow("start")
    finish = workflow("finish")

    assert "master" in start and "develop" in start
    assert "推送到 origin 并设置 upstream" in start
    assert "no-ff 合并到 develop" in finish
    assert "no-ff 合并到" in finish and "master" in finish
    assert "原子 push" in finish
    assert "v<semver>" in finish
