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


def test_scoped_module_validation_does_not_report_unrelated_playbooks(tmp_path):
    load_core_module()
    from mdf_core.execution.modules_check import validate_modules

    repo = copy_fixture(tmp_path)
    path = repo / "tests/playbooks/invalid.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nsuites: [unknown]\n---\n\n## S01 Step\n")
    init_git(repo)
    for scope, expected in [
        ({repo / "docs/system/testing/quick.md"}, False),
        ({path}, True), ({repo / ".mdf/modules.yaml"}, True), (None, True),
    ]:
        findings = []
        validate_modules(repo, findings, paths=scope)
        assert any(item.code == "playbooks.invalid" for item in findings) is expected


@pytest.mark.parametrize("content, diagnostic_kind", [
    ("---\nsuites: [billing]\n---\n\n# Missing steps\n", "归属 playbook 解析失败"),
    ("---\nsuites: [billing]\n\n# Unterminated frontmatter\n", "归属未知"),
    ("---\nsuites: [other]\n---\n\n# Missing steps\n", None),
])
def test_scoped_named_doc_points_to_unusable_playbook(tmp_path, content, diagnostic_kind):
    load_core_module()
    from mdf_core.execution.modules_check import validate_modules

    repo = copy_fixture(tmp_path)
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace("named: []", "named: [billing]"))
    doc = repo / "docs/system/testing/billing.md"
    doc.write_text("---\ntitle: billing\n---\n\n# Billing\n\n目的：测试。\n\ntestcase：playbook。\n")
    book = repo / "tests/playbooks/billing.md"
    book.parent.mkdir(parents=True)
    book.write_text(content)
    init_git(repo)
    findings = []
    validate_modules(repo, findings, paths={doc})
    diagnostic = next(item for item in findings if item.code == "modules.named_doc_command")
    if diagnostic_kind:
        assert diagnostic_kind in diagnostic.message
        assert "tests/playbooks/billing.md" in diagnostic.message
    else:
        assert "playbook 解析失败" not in diagnostic.message
        assert "tests/playbooks/billing.md" not in diagnostic.message
    assert not any(item.code == "playbooks.invalid" for item in findings)
    findings = []
    validate_modules(repo, findings)
    assert any(item.code == "playbooks.invalid" for item in findings)
