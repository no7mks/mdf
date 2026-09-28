"""模板占位符、Bug 与 Change 模板的契约示例。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_bug_template_uses_a_bare_found_in_sentinel():
    template = skill_dir("mdf") / "assets" / "templates" / "bug.md"
    text = template.read_text(encoding="utf-8")

    assert "found_in: {{MDF_FOUND_IN}}" in text
    assert 'found_in: "{{MDF_FOUND_IN}}"' not in text


def test_change_contract_uses_the_supported_evidence_mapping_example():
    contract = skill_dir("mdf") / "references" / "object-contract.md"
    text = contract.read_text(encoding="utf-8")

    assert "evidence: {tests:" not in text
    assert "evidence:\n  tests: []\n  commands: []\n  artifacts: []" in text


def test_release_objectives_keep_only_the_selected_work_line():
    template = skill_dir("mdf") / "assets" / "templates" / "release-objectives.md"
    text = template.read_text(encoding="utf-8")

    assert "## 工作线" in text
    assert "{{MDF_RELEASE_WORK_LINE}}" in text
    assert "不联调" not in text
    assert "联调" not in text
    assert "本版选定" not in text


def test_template_slots_use_mdf_prefix():
    load_core_module()
    from mdf_core.constants import MARKER_RE

    slot = re.compile(r"\{\{[^{}\n]+\}\}")
    leftover: list[tuple[str, str]] = []
    root = skill_dir("mdf") / "assets" / "templates"
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        for match in slot.finditer(path.read_text(encoding="utf-8")):
            token = match.group(0)
            if token == "{{MDF_...}}" or MARKER_RE.search(token):
                continue
            leftover.append((path.name, token))
    assert leftover == []
