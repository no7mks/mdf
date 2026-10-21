"""有限并发执行只读检查，按输入顺序汇总 findings。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Sequence

from mdf_core.foundation.errors import Finding
from mdf_core.foundation.progress import progress, report_progress


def collect_parallel(
    checks: Sequence[tuple[str, Callable[[], list[Finding]]]],
    *,
    label: str | None = None,
) -> list[Finding]:
    def inspect(check):
        name, run = check
        with progress(name):
            return run()

    if label:
        report_progress(label, f"已检查 0/{len(checks)}")
    if not checks:
        return []
    results: list[list[Finding]] = [[] for _ in checks]
    with ThreadPoolExecutor(max_workers=min(4, len(checks))) as pool:
        pending = {pool.submit(inspect, check): index for index, check in enumerate(checks)}
        for completed, future in enumerate(as_completed(pending), start=1):
            index = pending[future]
            results[index] = future.result()
            if label:
                report_progress(label, f"已检查 {completed}/{len(checks)}，完成 {checks[index][0]}")
    return [finding for result in results for finding in result]
