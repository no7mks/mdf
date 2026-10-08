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
