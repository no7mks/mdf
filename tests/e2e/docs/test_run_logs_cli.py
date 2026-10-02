"""每次 CLI 调用与 Core 代跑的验证入口都留下完整日志。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def latest(root):
    return sorted(path for path in root.iterdir() if path.is_dir())[-1]


def test_cli_call_logs_full_output_and_error_points_to_log(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    run = latest(repo / ".mdf/logs")
    assert run.name.endswith("-doctor")
    assert json.loads((run / "stdout.log").read_text())["ok"] is True
    meta = json.loads((run / "meta.json").read_text())
    assert meta["argv"][0] == "doctor" and meta["exit_code"] == 0
    failed = mdf(python_exe, "verify", "run", "--scope", "branch", "--repo", str(repo))
    error = json.loads(failed.stderr.strip().splitlines()[-1])
    log = Path(error["log"])
    assert log.parent == (repo / ".mdf/logs").resolve()
    assert error["error"] in (log / "stderr.log").read_text()
    assert json.loads((log / "meta.json").read_text())["exit_code"] == 1
    assert ".mdf/" not in git(repo, "status", "--porcelain").stdout


def test_usage_errors_are_logged(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    mdf(python_exe, "doctor", "--repo", str(repo), "--bogus")
    run = latest(repo / ".mdf/logs")
    assert "--bogus" in (run / "stderr.log").read_text()
    assert json.loads((run / "meta.json").read_text())["exit_code"] == 2


def test_worktree_calls_log_to_main_repository(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    payload(mdf(python_exe, "delivery", "status", "--repo", str(repo)))
    main = Path(git(repo, "rev-parse", "--path-format=absolute",
                    "--git-common-dir").stdout.strip()).parent
    assert latest(main / ".mdf/logs").name.endswith("-delivery")
    assert not (repo / ".mdf/logs").exists()


def test_unmanaged_directory_logs_to_fallback(python_exe, tmp_path, monkeypatch):
    fallback = tmp_path / "fallback"
    monkeypatch.setenv("MDF_LOG_DIR", str(fallback))
    plain = tmp_path / "plain"
    plain.mkdir()
    mdf(python_exe, "doctor", "--repo", str(plain))
    assert not (plain / ".mdf").exists()
    assert latest(fallback).name.endswith("-doctor")


def test_verify_keeps_full_output_of_every_entry(python_exe, tmp_path):
    repo, root = converge_ready(python_exe, tmp_path)
    patch_module_command(
        repo, "lint", lambda _: "python3 -c 'print(9000 * chr(120))'"
    )
    commit(repo, "test: lint 长输出")
    payload(mdf(python_exe, "verify", "run", "--scope", "branch", "--repo", str(repo)))
    evidence = json.loads((root / "verify.branch.json").read_text())
    logs = {item["id"]: item["log"] for item in evidence["results"]}
    assert set(logs) == {
        "lint:default", "build:default", "quick:default", "smoke:default",
    }
    assert (repo / logs["lint:default"] / "stdout.log").read_text() == 9000 * "x" + "\n"
    assert (repo / logs["build:default"] / "stderr.log").is_file()
