"""playbook frontmatter 归属与步骤标题解析。"""
from pathlib import Path

from mdf_test_support import *  # noqa: F403


def _parse(tmp_path: Path, text: str, named=("billing",)):
    load_core_module()
    from mdf_core.execution.playbooks import parse_playbook

    (tmp_path / "p.md").write_text(text, encoding="utf-8")
    return parse_playbook(tmp_path, "p.md", set(named))


def test_parse_playbook_reads_suites_and_steps(tmp_path):
    result = _parse(tmp_path, "---\nsuites: [release, billing]\n---\n\n# t\n\n## S01 一\n\n## S02 二\n\n### S03 子标题\n")
    assert result == {"path": "p.md", "suites": ["release", "billing"], "steps": ["S01", "S02"]}


@pytest.mark.parametrize(
    "example",
    [
        "```markdown\n## S02 示例\n## S01 示例\n```\n",
        "~~~\n## S02 示例\n```\n## S01 示例\n~~~\n",
        "````\n```\n## S02 示例\n```\n````\n",
    ],
)
def test_parse_playbook_ignores_steps_in_fenced_code(tmp_path, example):
    text = f"---\nsuites: [release]\n---\n\n## S01 真实\n\n{example}\n## S03 收尾\n"
    assert _parse(tmp_path, text)["steps"] == ["S01", "S03"]


@pytest.mark.parametrize(
    "text",
    [
        "# 无 frontmatter\n\n## S01 一\n",
        "---\nsuites: []\n---\n\n## S01 一\n",
        "---\nsuites: [release, release]\n---\n\n## S01 一\n",
        "---\nsuites: [quick]\n---\n\n## S01 一\n",
        "---\nsuites: [smoke]\n---\n\n## S01 一\n",
        "---\nsuites: [other]\n---\n\n## S01 一\n",
        "---\nsuites: [release]\n---\n\n## 步骤一\n",
        "---\nsuites: [release]\n---\n\n## S01 一\n\n## S01 二\n",
    ],
)
def test_parse_playbook_rejects_invalid(tmp_path, text):
    load_core_module()
    from mdf_core.foundation.errors import MDFError

    with pytest.raises(MDFError) as error:
        _parse(tmp_path, text)
    assert error.value.code == "invalid_playbook"
