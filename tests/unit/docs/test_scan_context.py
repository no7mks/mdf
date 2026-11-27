"""并行检查共享 scan 时只加载一次 inventory、metadata 与 anchors。"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from time import sleep

import pytest

from mdf_test_support import load_core_module

load_core_module()
from mdf_core.inspection import scan_context, validate_links


@pytest.mark.parametrize("access", ["inventory", "metadata", "anchors"])
def test_parallel_scan_cache_is_loaded_once(tmp_path, monkeypatch, access):
    scan = scan_context.RepoScanContext(tmp_path)
    path = tmp_path / "topic.md"
    path.write_text("---\ntitle: 标题\n---\n# 标题\n")
    calls = Counter()
    lock = Lock()
    barrier = Barrier(4)

    def counted(key, value):
        with lock:
            calls[key] += 1
        sleep(0.02)
        return value

    monkeypatch.setattr(scan, "_paths", lambda *args: counted(args, {"topic.md"}))
    monkeypatch.setattr(scan_context, "_metadata", lambda text: counted("metadata", ({"title": "标题"}, "")))
    monkeypatch.setattr(validate_links, "document_anchors", lambda path: counted("anchors", {"标题"}))

    def read(_):
        barrier.wait(timeout=5)
        if access == "inventory":
            return scan.visible_with_dirs, scan.tracked_with_dirs
        if access == "metadata":
            return scan.frontmatter(path)
        return scan.anchors(path)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read, range(4)))
    assert all(result == results[0] for result in results)
    assert calls and all(count == 1 for count in calls.values())
