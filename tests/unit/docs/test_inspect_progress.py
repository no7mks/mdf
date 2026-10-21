"""阶段开始立即 flush，异常保留原对象且不报告阶段结束。"""
from mdf_test_support import *  # noqa: F403


def test_progress_flushes_start_before_work(monkeypatch):
    load_core_module()
    from mdf_core.foundation.progress import progress

    class Stream(io.StringIO):
        def flush(self):
            self.flushed = self.getvalue()

    stream = Stream()
    monkeypatch.setattr(sys, "stderr", stream)
    with progress("检查"):
        assert stream.flushed == "[检查] 开始\n"
    assert stream.flushed == stream.getvalue()
    assert "检查结束，用时" in stream.flushed


def test_progress_preserves_exception_and_reports_interruption(capsys):
    core = load_core_module()
    from mdf_core.foundation.progress import progress
    error = core.MDFError("检查失败")
    with pytest.raises(core.MDFError) as caught:
        with progress("检查"):
            raise error
    assert caught.value is error
    stderr = capsys.readouterr().err
    assert "中断，用时" in stderr
    assert "检查结束" not in stderr


def test_item_progress_counts_only_completed_work(monkeypatch, capsys):
    load_core_module()
    from mdf_core.foundation import progress

    ticks = iter([10.0, 10.0, 12.0, 15.0])
    monkeypatch.setattr(progress.time, "monotonic", lambda: next(ticks))
    items = progress.progress_items("evidence", ["src/a.py", "src/b.py"])
    assert next(items) == "src/a.py"
    assert capsys.readouterr().err == (
        "[evidence] 已检查 0/2，当前 src/a.py，用时 0.0s\n"
    )
    assert next(items) == "src/b.py"
    assert capsys.readouterr().err == (
        "[evidence] 已检查 1/2，当前 src/b.py，用时 2.0s\n"
    )
    assert list(items) == []
    assert capsys.readouterr().err == "[evidence] 已检查 2/2，用时 5.0s\n"


def test_item_progress_does_not_report_completion_on_failure(capsys):
    load_core_module()
    from mdf_core.foundation.progress import progress_items

    with pytest.raises(RuntimeError):
        for _ in progress_items("事实文档", ["docs/a.md"]):
            raise RuntimeError("检查失败")
    stderr = capsys.readouterr().err
    assert "已检查 0/1，当前 docs/a.md" in stderr
    assert "已检查 1/1" not in stderr


def test_item_progress_handles_empty_scope(capsys):
    load_core_module()
    from mdf_core.foundation.progress import progress_items

    assert list(progress_items("事实文档", [])) == []
    assert "已检查 0/0" in capsys.readouterr().err


def test_plan_preserves_global_stage_in_nested_workers(capsys):
    load_core_module()
    from mdf_core.foundation.progress import ProgressPlan, report_progress
    from mdf_core.inspection.parallel import collect_parallel

    def leaf():
        report_progress("evidence", "已检查 1/1")
        return []

    def document():
        return collect_parallel([("页面", leaf)])

    plan = ProgressPlan("doctor", ("契约检查", "汇总"))
    with plan.stage(1):
        collect_parallel([("事实文档", document)])
    with plan.stage(2):
        pass
    report_progress("外部", "无阶段")
    lines = capsys.readouterr().err.splitlines()
    assert lines[0] == "[doctor] 全局共 2 个阶段：1. 契约检查 → 2. 汇总"
    assert "[全局 doctor 阶段 1/2，已完成 0/2] [evidence] 已检查 1/1" in lines
    assert "[全局 doctor 阶段 2/2，已完成 2/2]" in lines[-2]
    assert lines[-1] == "[外部] 无阶段"


def test_plan_failure_does_not_advance_and_restores_parent(capsys):
    load_core_module()
    from mdf_core.foundation.progress import ProgressPlan, report_progress

    plan = ProgressPlan("doctor", ("契约检查", "汇总"))
    with pytest.raises(RuntimeError):
        with plan.stage(1):
            raise RuntimeError("失败")
    report_progress("外部", "无阶段")
    stderr = capsys.readouterr().err
    assert "[全局 doctor 阶段 1/2，已完成 0/2] [doctor 1/2：契约检查] 中断" in stderr
    assert "已完成 1/2" not in stderr
    assert stderr.endswith("[外部] 无阶段\n")


def test_groups_keep_ids_when_discovered_and_track_remaining(capsys):
    from mdf_core.foundation.progress import (
        ProgressPlan, register_progress_groups, report_count, skip_progress_group,
    )

    plan = ProgressPlan("doctor", ("检查",), groups=("文档", "后续"))
    with plan.stage(1):
        report_count("文档", 0, 2)
        register_progress_groups(["页面 A", "页面 B"], reason="扫描完成")
        report_count("页面 B", 0, 1)
        report_count("页面 A", 1, 1)
        skip_progress_group("后续", "无需执行")
        register_progress_groups(["页面 A", "页面 C"], reason="新增页面")
        report_count("页面 B", 1, 1)
        report_count("页面 C", 0, 0)
        report_count("文档", 2, 2)
    stderr = capsys.readouterr().err
    assert "组数 2 → 4" in stderr and "组数 4 → 5" in stderr
    assert "共 4 组｜完成 0｜运行 2｜待开始 2" in stderr
    assert "运行中：组 1、组 4" in stderr
    assert "[组 4] [页面 B] 已检查 0/1" in stderr
    assert "[组 4] [页面 B] 已检查 1/1" in stderr
    assert "共 5 组｜完成 4｜运行 0｜待开始 0｜中断 0｜跳过 1" in stderr


def test_group_failure_keeps_pending_and_marks_running_interrupted(capsys):
    from mdf_core.foundation.progress import ProgressPlan, report_count

    plan = ProgressPlan("doctor", ("检查",), groups=("当前", "后续"))
    with pytest.raises(RuntimeError):
        with plan.stage(1):
            report_count("当前", 0, 2)
            raise RuntimeError("无法继续")
    assert "共 2 组｜完成 0｜运行 0｜待开始 1｜中断 1｜跳过 0" in capsys.readouterr().err
