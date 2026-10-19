"""人工工作账本的起点与收口检查。"""
import pytest
from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.manual import STEPS, require_manual_objectives


def checklist(marks):
    return "\n".join(f"- [{mark}] {step}" for mark, step in zip(marks, STEPS))


def test_start_requires_user_work_pending():
    require_manual_objectives(checklist("x      "), starting=True)
    with pytest.raises(MDFError, match="用户显式勾选"):
        require_manual_objectives(checklist("xx     "), starting=True)


def test_finish_requires_all_steps_and_order():
    require_manual_objectives(checklist("xxxxxxx"), finishing=True)
    with pytest.raises(MDFError, match="未完成"):
        require_manual_objectives(checklist("x xxxxx"), finishing=True)
    with pytest.raises(MDFError, match="固定顺序"):
        require_manual_objectives(checklist("xxxxxxx").replace("verify smoke", "converge"))
