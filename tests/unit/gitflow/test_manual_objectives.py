"""人工工作账本的起点与收口检查。"""
import pytest
from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.manual import STEPS, require_manual_objectives


def checklist(marks):
    return "\n".join(f"- [{mark}] {step}" for mark, step in zip(marks, STEPS))


def test_start_requires_user_work_pending():
    require_manual_objectives(checklist("x       "), starting=True)
    with pytest.raises(MDFError, match="用户显式勾选"):
        require_manual_objectives(checklist("xx      "), starting=True)


def test_finish_requires_all_steps_and_order():
    require_manual_objectives(checklist("xxxxxxxx"), finishing=True)
    with pytest.raises(MDFError, match="未完成"):
        require_manual_objectives(checklist("x xxxxxx"), finishing=True)
    with pytest.raises(MDFError, match="固定顺序"):
        require_manual_objectives(checklist("xxxxxxxx").replace("verify smoke", "converge"))


def test_pr_manual_requires_catch_up_and_no_pr_checkbox():
    require_manual_objectives(checklist("x       "), starting=True, pr_mode=True)
    text = checklist("xxxxxxxx")
    require_manual_objectives(text, finishing=True, pr_mode=True)
    with pytest.raises(MDFError, match="未完成"):
        require_manual_objectives(text.replace("[x] consolidate", "[ ] consolidate"), finishing=True, pr_mode=True)
    with pytest.raises(MDFError, match="固定顺序"):
        require_manual_objectives(text + "\n- [x] pr", finishing=True, pr_mode=True)
