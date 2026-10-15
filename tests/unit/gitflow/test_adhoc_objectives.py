"""Adhoc 五步账本不接受缺项、越序或虚报完成。"""
import pytest
from mdf_core.adhoc import objectives, require_objectives
from mdf_core.errors import MDFError


def test_adhoc_initial_and_completed_objectives():
    text = objectives()
    require_objectives(text, starting=True)
    require_objectives(text.replace("[ ]", "[x]"), finishing=True)
    with pytest.raises(MDFError, match="未完成"):
        require_objectives(text, finishing=True)
    with pytest.raises(MDFError, match="均须未勾选"):
        require_objectives(text.replace("[ ]", "[x]", 1), starting=True)


def test_adhoc_progress_is_a_completed_prefix():
    text = objectives()
    assert require_objectives(text) == "工作"
    assert require_objectives(text.replace("[ ]", "[x]", 1)) == "code-review"
    with pytest.raises(MDFError, match="顺序完成"):
        require_objectives(text.replace("- [ ] verify smart", "- [x] verify smart"))


@pytest.mark.parametrize("old,new", [
    ("- [ ] 工作\n", ""),
    ("verify smart", "verify branch"),
    ("fact audit/update", "fact update"),
    ("- [ ] 工作\n- [ ] code-review", "- [ ] code-review\n- [ ] 工作"),
])
def test_adhoc_rejects_changed_or_reordered_steps(old, new):
    with pytest.raises(MDFError, match="固定顺序"):
        require_objectives(objectives().replace(old, new))
