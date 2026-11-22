"""运行日志目录的过期清理，以及 run 代跑。"""
import errno
import json
import os
import sys
import time
from pathlib import Path

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
    for path in (old_dir, old_file):
        os.utime(path, (stale, stale))
    prune(root)
    assert sorted(path.name for path in root.iterdir()) == ["new"]
    assert not (root / ".gitignore").exists()


def test_strip_control_removes_csi_and_splits_cr():
    load_core_module()
    from mdf_core.execution.run_logs import strip_control

    assert strip_control("\x1b[31mred\x1b[0m") == "red"
    assert strip_control("ab\rcd") == "ab\ncd"


def test_report_creation_rejects_symlinked_mdf(tmp_path):
    from mdf_core.execution.reports import new_report_dir
    from mdf_core.foundation.errors import MDFError

    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / ".mdf"
    link.symlink_to(outside)

    with pytest.raises(MDFError) as error:
        new_report_dir(tmp_path, "quick")

    assert error.value.code == "managed_symlink"
    assert list(outside.iterdir()) == []


def test_report_creation_does_not_follow_a_gitignore_symlink(tmp_path):
    from mdf_core.execution.reports import new_report_dir

    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / ".mdf" / "reports" / ".gitignore"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside / "ignore")

    created = new_report_dir(tmp_path, "quick")

    assert created.is_dir()
    assert link.is_symlink()
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
    assert not (outside / ".gitignore").exists()
    prune(link)
    assert old.read_text() == "keep"


@pytest.mark.parametrize("err_no", [errno.EROFS, errno.EACCES])
@pytest.mark.parametrize("existing_logs", [False, True])
@pytest.mark.parametrize("use_env", [True, False])
def test_run_log_falls_back_when_main_log_dir_is_unwritable(
    tmp_path, monkeypatch, err_no, existing_logs, use_env
):
    load_core_module()
    import mdf_core.execution.run_logs as run_logs

    main = tmp_path / "main"
    worktree = tmp_path / "worktree"
    (main / ".mdf").mkdir(parents=True)
    (worktree / ".mdf").mkdir(parents=True)
    main_logs = (main / ".mdf" / "logs").resolve()
    if existing_logs:
        run_logs.ignored_dir(main_logs)

    home = tmp_path / "home"
    fallback = (tmp_path / "env-logs") if use_env else (home / ".mdf" / "logs")
    monkeypatch.setenv("HOME", str(home))
    if use_env:
        monkeypatch.setenv("MDF_LOG_DIR", str(fallback))
    else:
        monkeypatch.delenv("MDF_LOG_DIR", raising=False)
    monkeypatch.setattr(run_logs, "_main_repo", lambda repo: main.resolve())

    orig_ignored_dir = run_logs.ignored_dir
    orig_unique_dir = run_logs.unique_dir

    def fake_ignored_dir(path):
        target = Path(path).resolve()
        if not existing_logs and target == main_logs:
            raise OSError(err_no, os.strerror(err_no), str(path))
        return orig_ignored_dir(path)

    def fake_unique_dir(root, name):
        target = Path(root).resolve()
        if existing_logs and target == main_logs:
            raise OSError(err_no, os.strerror(err_no), str(root))
        return orig_unique_dir(root, name)

    monkeypatch.setattr(run_logs, "ignored_dir", fake_ignored_dir)
    monkeypatch.setattr(run_logs, "unique_dir", fake_unique_dir)

    log = run_logs.RunLog(["validate", "--repo", str(worktree)])
    with log:
        print("ok")
        log.finish(0)

    assert log.path.parent == fallback.resolve()
    assert log.path.name.endswith("-validate")
    assert (log.path / "stdout.log").read_text(encoding="utf-8") == "ok\n"
    assert json.loads((log.path / "meta.json").read_text(encoding="utf-8"))["exit_code"] == 0
    meta = json.loads((log.path / "meta.json").read_text(encoding="utf-8"))
    assert "tool_revision" in meta and "mdf_root" in meta


@pytest.mark.parametrize("err_no", [errno.EROFS, errno.EACCES])
def test_prune_oserror_does_not_abort_or_block_fallback(tmp_path, monkeypatch, err_no):
    load_core_module()
    import mdf_core.execution.run_logs as run_logs

    root = run_logs.ignored_dir(tmp_path / "logs")
    stale_dir = root / "old-dir"
    stale_dir.mkdir()
    stale_file = root / "old.log"
    stale_file.write_text("x", encoding="utf-8")
    stale = time.time() - 8 * 86400
    for item in (stale_dir, stale_file):
        os.utime(item, (stale, stale))

    def fail_rmtree(path):
        raise OSError(err_no, os.strerror(err_no), str(path))

    monkeypatch.setattr(run_logs.shutil, "rmtree", fail_rmtree)
    run_logs.prune(root)

    orig_iterdir = Path.iterdir

    def fail_iterdir(self):
        if self == root:
            raise OSError(err_no, os.strerror(err_no), str(self))
        return orig_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", fail_iterdir)
    run_logs.prune(root)


def test_run_log_does_not_follow_a_gitignore_symlink(tmp_path, monkeypatch):
    load_core_module()
    import mdf_core.execution.run_logs as run_logs

    repo = tmp_path / "repo"
    (repo / ".mdf" / "logs").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = repo / ".mdf" / "logs" / ".gitignore"
    link.symlink_to(outside / "ignore")
    fallback = tmp_path / "fallback"
    monkeypatch.setenv("MDF_LOG_DIR", str(fallback))

    log = run_logs.RunLog(["validate", "--repo", str(repo)])

    assert log.path.parent == (repo / ".mdf" / "logs").resolve()
    assert link.is_symlink()
    assert list(outside.iterdir()) == []
    assert not fallback.exists()


@pytest.mark.parametrize("err_no", [errno.EROFS, errno.EACCES])
def test_run_log_and_cli_fail_explicitly_when_all_candidates_unwritable(
    tmp_path, monkeypatch, capsys, err_no
):
    load_core_module()
    import mdf_core.cli as cli
    import mdf_core.execution.run_logs as run_logs
    from mdf_core.foundation.errors import MDFError

    repo = tmp_path / "repo"
    (repo / ".mdf").mkdir(parents=True)
    fallback = tmp_path / "unwritable-fallback"
    home = tmp_path / "home"
    monkeypatch.setenv("MDF_LOG_DIR", str(fallback))
    monkeypatch.setenv("HOME", str(home))

    def fail_ignored_dir(path):
        raise OSError(err_no, os.strerror(err_no), str(path))

    monkeypatch.setattr(run_logs, "ignored_dir", fail_ignored_dir)

    with pytest.raises(MDFError) as error:
        run_logs.RunLog(["validate", "--repo", str(repo)])

    assert error.value.code == "log_dir_unwritable"
    assert error.value.details["candidates"] == [
        str(repo.resolve() / ".mdf" / "logs"),
        str(fallback),
    ]
    assert not (home / ".mdf" / "logs").exists()

    code = cli.main(["validate", "--repo", str(repo)])
    assert code == 1
    err = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert err["ok"] is False
    assert err["error"] == "log_dir_unwritable"
    assert err["log"] is None
    assert err["details"]["candidates"] == [
        str(repo.resolve() / ".mdf" / "logs"),
        str(fallback),
    ]


@pytest.mark.parametrize(
    "argv_prefix",
    [
        ["fact-audit-report-check"],
        ["review-context", "--against", "HEAD~1"],
        ["fact-audit", "--against=HEAD~1"],
    ],
)
def test_standalone_review_commands_never_touch_repo_logs(tmp_path, monkeypatch, argv_prefix):
    load_core_module()
    import mdf_core.execution.run_logs as run_logs

    repo = tmp_path / "repo"
    (repo / ".mdf").mkdir(parents=True)
    fallback = tmp_path / "fallback"
    monkeypatch.setenv("MDF_LOG_DIR", str(fallback))

    log = run_logs.RunLog([*argv_prefix, "--repo", str(repo)])
    assert log.path.parent == fallback.resolve()
    assert not (repo / ".mdf" / "logs").exists()
