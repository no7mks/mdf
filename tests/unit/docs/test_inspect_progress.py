"""阶段开始立即 flush，异常保留原对象且不报告阶段结束。"""
from mdf_test_support import *  # noqa: F403


def test_progress_flushes_start_before_work(monkeypatch):
    load_core_module()
    from mdf_core.progress import progress

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
    from mdf_core.progress import progress
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
    from mdf_core import progress

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
    from mdf_core.progress import progress_items

    with pytest.raises(RuntimeError):
        for _ in progress_items("事实文档", ["docs/a.md"]):
            raise RuntimeError("检查失败")
    stderr = capsys.readouterr().err
    assert "已检查 0/1，当前 docs/a.md" in stderr
    assert "已检查 1/1" not in stderr


def test_item_progress_handles_empty_scope(capsys):
    load_core_module()
    from mdf_core.progress import progress_items

    assert list(progress_items("事实文档", [])) == []
    assert "已检查 0/0" in capsys.readouterr().err
