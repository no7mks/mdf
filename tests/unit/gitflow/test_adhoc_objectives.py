"""Adhoc 固定账本不接受缺项、越序或虚报完成。"""
import pytest
from mdf_core.lifecycle.adhoc import objectives, require_objectives
from mdf_core.foundation.errors import MDFError

WORK = "更新配置说明"


def test_adhoc_initial_and_completed_objectives():
    text = objectives(WORK)
    require_objectives(text, starting=True)
    require_objectives(text.replace("[ ]", "[x]"), finishing=True)
    with pytest.raises(MDFError, match="未完成"):
        require_objectives(text, finishing=True)
    with pytest.raises(MDFError, match="均须未勾选"):
        require_objectives(text.replace("[ ]", "[x]", 1), starting=True)


def test_adhoc_progress_is_a_completed_prefix():
    text = objectives(WORK)
    assert require_objectives(text) == "工作"
    assert require_objectives(text.replace("[ ]", "[x]", 1)) == "lint"
    with pytest.raises(MDFError, match="顺序完成"):
        require_objectives(text.replace("- [ ] verify smart", "- [x] verify smart"))


@pytest.mark.parametrize("old,new", [
    ("- [ ] 工作\n", ""),
    ("verify smart", "verify branch"),
    ("fact audit/update", "fact update"),
    ("- [ ] 工作\n- [ ] lint", "- [ ] lint\n- [ ] 工作"),
])
def test_adhoc_rejects_changed_or_reordered_steps(old, new):
    with pytest.raises(MDFError, match="固定顺序"):
        require_objectives(objectives(WORK).replace(old, new))


def test_pr_adhoc_requires_catch_up_and_no_pr_checkbox():
    text = objectives(WORK).replace("- [ ] close-out\n", "")
    require_objectives(text, starting=True, pr_mode=True)
    assert require_objectives(text.replace("[ ]", "[x]", 5), pr_mode=True) == "catch-up"
    checked = text.replace("[ ]", "[x]")
    assert require_objectives(checked, finishing=True, pr_mode=True) is None
    with pytest.raises(MDFError, match="未完成"):
        require_objectives(checked.replace("[x] catch-up", "[ ] catch-up"), finishing=True, pr_mode=True)
    with pytest.raises(MDFError, match="固定顺序"):
        require_objectives(checked + "\n- [x] pr", finishing=True, pr_mode=True)
