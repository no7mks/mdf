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
    assert "## 联调" in text
    assert "{{MDF_RELEASE_INTEGRATE}}" in text
    assert "has_dev: {{MDF_HAS_DEV}}" in text
    assert "integrate（无联调工作线：start 写入时已勾" in text
    assert "owner 开发（has_dev: no：start 写入时已勾" in text
    assert "converge（has_dev: no：start 写入时已勾" in text
    assert "不联调：" not in text
    assert "工作线按是否联调二选一" not in text
    assert "本版选定" not in text


@pytest.mark.parametrize(("name", "first_heading"), [
    ("adhoc-objectives.md", "工作目标"),
    ("objectives.md", "目标与非目标"),
    ("manual-objectives.md", "工作范围"),
    ("release-objectives.md", "本版范围"),
])
def test_objectives_templates_frontload_delivery_content(name, first_heading):
    text = (skill_dir("mdf") / "assets" / "templates" / name).read_text(encoding="utf-8")
    headings = re.findall(r"^## (.+)$", text, re.M)

    assert headings[0] == first_heading
    assert headings[-1] == "步骤"
    if name != "adhoc-objectives.md":
        assert "可验证验收" in headings[:-1]


def test_template_slots_use_mdf_prefix():
    load_core_module()
    from mdf_core.foundation.constants import MARKER_RE

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
