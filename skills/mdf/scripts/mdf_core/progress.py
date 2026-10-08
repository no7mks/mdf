"""检查阶段的实时 stderr 输出；stdout 留给结构化结果。"""
import sys
import time
from contextlib import contextmanager


def report_progress(label: str, message: str) -> None:
    print(f"[{label}] {message}", file=sys.stderr, flush=True)


@contextmanager
def progress(label: str):
    started = time.monotonic()
    report_progress(label, "开始")
    try:
        yield
    except BaseException:
        report_progress(label, f"中断，用时 {time.monotonic() - started:.1f}s")
        raise
    else:
        report_progress(label, f"检查结束，用时 {time.monotonic() - started:.1f}s")
