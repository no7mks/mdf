"""运行日志目录的过期清理。"""
import os
import time

from mdf_test_support import *  # noqa: F403


def test_prune_removes_entries_older_than_seven_days(tmp_path):
    load_core_module()
    from mdf_core.run_logs import ignored_dir, prune
    root = ignored_dir(tmp_path / "logs")
    old_dir, new_dir, old_file = root / "old", root / "new", root / "old.log"
    old_dir.mkdir()
    (old_dir / "stdout.log").write_text("x")
    new_dir.mkdir()
    old_file.write_text("x")
    stale = time.time() - 8 * 86400
    for path in (old_dir, old_file, root / ".gitignore"):
        os.utime(path, (stale, stale))
    prune(root)
    assert sorted(path.name for path in root.iterdir()) == [".gitignore", "new"]
    assert (root / ".gitignore").read_text() == "*\n"
