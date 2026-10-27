"""运行日志目录的过期清理，以及 run 代跑。"""
import json
import os
import sys
import time

from mdf_test_support import *  # noqa: F403


def test_prune_removes_entries_older_than_seven_days(tmp_path):
    load_core_module()
    from mdf_core.execution.run_logs import ignored_dir, prune
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


def test_strip_control_removes_csi_and_splits_cr():
    load_core_module()
    from mdf_core.execution.run_logs import strip_control

    assert strip_control("\x1b[31mred\x1b[0m") == "red"
    assert strip_control("ab\rcd") == "ab\ncd"


@pytest.mark.parametrize("name", [".mdf", ".mdf/reports/.gitignore"])
def test_report_creation_rejects_symlink_at_write_target(tmp_path, name):
    from mdf_core.execution.reports import new_report_dir
    from mdf_core.foundation.errors import MDFError

    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside if link.name != ".gitignore" else outside / "ignore")

    with pytest.raises(MDFError) as error:
        new_report_dir(tmp_path, "quick")

    assert error.value.code == "managed_symlink"
    assert list(outside.iterdir()) == []


def test_run_logs_command_and_sets_report_dir(tmp_path, python_exe):
    (tmp_path / ".mdf").mkdir()
    probe = (
        "import os, sys;"
        " sys.stderr.write(os.environ['MDF_REPORT_DIR'] + chr(10));"
        " sys.stderr.write(chr(27) + '[31mred' + chr(27) + '[0m' + chr(10));"
        " sys.stderr.write('color=' + os.environ.get('NO_COLOR', '') + chr(10))"
    )
    result = mdf(
        python_exe, "run", "--repo", str(tmp_path), "--name", "probe",
        "--", sys.executable, "-c", probe,
    )
    data = payload(result)
    assert data["exit_code"] == 0
    assert data["command"][-1] == probe
    log_dir = tmp_path / data["log"]
    assert log_dir.name.endswith("-probe")
    stderr = (log_dir / "stderr.log").read_text(encoding="utf-8")
    assert str(log_dir) in stderr
    assert "color=1" in stderr
    assert "red" in stderr
    assert "\x1b" not in stderr


def test_run_nonzero_returns_run_failed(tmp_path, python_exe):
    (tmp_path / ".mdf").mkdir()
    result = mdf(
        python_exe, "run", "--repo", str(tmp_path), "--name", "fail",
        "--", sys.executable, "-c", "raise SystemExit(3)",
    )
    assert result.returncode != 0
    error = json.loads(result.stderr.strip().splitlines()[-1])
    assert error["error"] == "run_failed"
    assert error["details"]["exit_code"] == 3


@pytest.mark.parametrize("name", ["logs", "reports", "tmp"])
def test_local_artifact_symlink_allows_writes_and_skips_pruning(tmp_path, name):
    from mdf_core.execution.run_logs import ignored_dir, prune

    outside = tmp_path / "outside"
    outside.mkdir()
    old = outside / "old.log"
    old.write_text("keep")
    stale = time.time() - 8 * 86400
    os.utime(old, (stale, stale))
    link = tmp_path / ".mdf" / name
    link.parent.mkdir()
    link.symlink_to(outside, target_is_directory=True)

    assert ignored_dir(link) == link
    assert (outside / ".gitignore").read_text() == "*\n"
    prune(link)
    assert old.read_text() == "keep"
