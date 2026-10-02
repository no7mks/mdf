"""Jev 可选加速契约：无 tool 时不得硬依赖。"""

from pathlib import Path

from conftest import skill_dir


def test_common_jev_optional_accelerator_is_non_blocking() -> None:
    text = (skill_dir("mdf") / "references" / "common.md").read_text(encoding="utf-8")
    assert "Jev 可选加速" in text
    assert "无 Jev 时主 Agent 路径与未引入前完全一致" in text
    assert "禁止空探测" in text
    assert "`choice` / `noul` / `score` / `run`" in text
    assert "不是硬依赖" in text
    assert "首次不可用提示" in text
    assert "每会话至多一行" in text
    assert "README「Jev 可选加速」" in text
    assert "不得追问" in text


def test_hung_intents_keep_optional_accelerator_marker() -> None:
    root = skill_dir("mdf") / "references"
    paths = (
        "jot.md", "intake.md", "init.md", "prp-review.md", "code-review.md",
        "next.md", "deliver.md", "fact-audit.md", "archive.md",
        "bug-close.md", "fix.md", "migrate.md", "close-out.md",
    )
    for name in paths:
        text = (root / name).read_text(encoding="utf-8")
        assert "可选加速" in text, name
        assert "common.md" in text and "Jev" in text, name
