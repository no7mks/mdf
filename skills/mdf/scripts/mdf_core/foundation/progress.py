"""检查阶段的实时 stderr 输出；stdout 留给结构化结果。"""
import sys
import time
from contextlib import contextmanager
from typing import Callable, Iterator, Sequence, TypeVar

T = TypeVar("T")


def report_progress(label: str, message: str) -> None:
    print(f"[{label}] {message}", file=sys.stderr, flush=True)


def progress_items(
    label: str, items: Sequence[T], describe: Callable[[T], str] = str,
) -> Iterator[T]:
    """处理前报告当前位置；只在调用方处理后增加已检查数。"""
    started = time.monotonic()
    total = len(items)
    for completed, item in enumerate(items):
        report_progress(
            label,
            f"已检查 {completed}/{total}，当前 {describe(item)}，"
            f"用时 {time.monotonic() - started:.1f}s",
        )
        yield item
    report_progress(
        label, f"已检查 {total}/{total}，用时 {time.monotonic() - started:.1f}s",
    )


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
