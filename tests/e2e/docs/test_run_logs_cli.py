"""每次 CLI 调用与 Core 代跑的验证入口都留下完整日志。"""
import time

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
    failed = mdf(python_exe, "verify", "--scope", "branch", "--repo", str(repo))
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
    payload(mdf(python_exe, "verify", "--scope", "branch", "--repo", str(repo)))
    evidence = json.loads((root / "verification-report.json").read_text())
    logs = {item["id"]: item["log"] for item in evidence["results"]}
    assert set(logs) == {
        "lint:default", "build:default", "quick:default", "smoke:default",
    }
    assert (repo / logs["lint:default"] / "stdout.log").read_text() == 9000 * "x" + "\n"
    assert (repo / logs["build:default"] / "stderr.log").is_file()


@pytest.mark.parametrize("existing_logs", [False, True])
def test_linked_worktree_with_readonly_main_repo_falls_back_to_mdf_log_dir(
    python_exe, tmp_path, monkeypatch, existing_logs
):
    from mdf_core.execution.run_logs import ignored_dir

    main = copy_fixture(tmp_path / "main")
    init_git(main)
    base = git(main, "rev-parse", "HEAD").stdout.strip()
    worktree = tmp_path / "worktree"
    git(main, "worktree", "add", "-b", "feature/readonly-check", str(worktree), "HEAD")
    (worktree / "src/extra.py").write_text("EXTRA = 1\n", encoding="utf-8")
    commit(worktree, "test: 新增实现文件")

    stale = time.time() - 8 * 86400
    reports = ignored_dir(worktree / ".mdf/reports")
    stale_report = reports / "old-report.log"
    stale_report.write_text("stale", encoding="utf-8")
    os.utime(stale_report, (stale, stale))

    locked = []
    if existing_logs:
        main_logs = ignored_dir(main / ".mdf/logs")
        stale_log = main_logs / "old-run.log"
        stale_log.write_text("stale", encoding="utf-8")
        os.utime(stale_log, (stale, stale))
        locked.append(main_logs)
    locked.extend([main / ".mdf", reports])

    fallback = tmp_path / "ext-logs"
    monkeypatch.setenv("MDF_LOG_DIR", str(fallback))

    try:
        for path in locked:
            path.chmod(0o555)

        assert_ok(mdf(python_exe, "validate", "--repo", str(worktree), "--level", "strict"))
        assert_ok(mdf(python_exe, "doctor", "--repo", str(worktree)))
        assert_ok(mdf(python_exe, "prose-check", "--repo", str(worktree)))
        run_res = payload(
            mdf(
                python_exe, "run", "--repo", str(worktree), "--name", "probe",
                "--", python_exe, "-c", "print('ok')",
            )
        )
        assert Path(run_res["log"]).parent == fallback.resolve()

        review_ctx = payload(
            mdf(python_exe, "review-context", "--repo", str(worktree), "--against", base)
        )["result"]
        assert review_ctx["incomplete"] == []
        assert_ok(mdf(python_exe, "validate", "--repo", str(worktree), "--level", "strict"))
        review_ctx_file = tmp_path / "review-context.json"
        review_report_file = tmp_path / "review-report.json"
        review_ctx_file.write_text(json.dumps(review_ctx), encoding="utf-8")
        review_keys = (
            "schema_version", "mode", "against", "head",
            "rules_sha256", "context_sha256", "paths",
        )
        review_report = {
            **{k: review_ctx[k] for k in review_keys},
            "decision": "pass",
            "incomplete": [],
            "findings": [],
        }
        review_report_file.write_text(json.dumps(review_report), encoding="utf-8")
        review_check = payload(
            mdf(
                python_exe, "review-report-check",
                "--context-file", str(review_ctx_file),
                "--report-file", str(review_report_file),
            )
        )["result"]
        assert review_check["valid"] is True and review_check["decision"] == "pass"

        fact_ctx = payload(
            mdf(python_exe, "fact-audit", "--repo", str(worktree), "--against", base)
        )["result"]
        assert fact_ctx["audit"]["findings"] == []
        assert_ok(mdf(python_exe, "validate", "--repo", str(worktree), "--level", "strict"))
        fact_ctx_file = tmp_path / "fact-context.json"
        fact_report_file = tmp_path / "fact-report.json"
        fact_ctx_file.write_text(json.dumps(fact_ctx), encoding="utf-8")
        fact_keys = (
            "schema_version", "mode", "operation", "against", "worktree_sha256",
            "rules_sha256", "context_sha256", "paths",
            "implementation_paths", "document_paths",
        )
        fact_report = {
            **{k: fact_ctx[k] for k in fact_keys},
            "findings": [],
            "incomplete": [],
            "warnings": [
                {"index": i, "disposition": "accepted", "evidence": "内部调整，无可观察契约变化"}
                for i, _ in enumerate(fact_ctx["audit"]["warnings"])
            ],
            "decision": "pass",
        }
        fact_report_file.write_text(json.dumps(fact_report), encoding="utf-8")
        fact_check = payload(
            mdf(
                python_exe, "fact-audit-report-check",
                "--repo", str(worktree),
                "--context-file", str(fact_ctx_file),
                "--report-file", str(fact_report_file),
            )
        )["result"]
        assert fact_check["valid"] is True and fact_check["decision"] == "pass"

        names = [item.name for item in fallback.iterdir() if item.is_dir()]
        for suffix in (
            "-validate", "-doctor", "-prose-check", "-probe",
            "-review-context", "-review-report-check",
            "-fact-audit", "-fact-audit-report-check",
        ):
            assert any(name.endswith(suffix) for name in names), suffix
        if not existing_logs:
            assert not (main / ".mdf/logs").exists()
        assert git(worktree, "status", "--porcelain").stdout == ""
        assert git(main, "status", "--porcelain").stdout == ""
    finally:
        for path in reversed(locked):
            if path.exists():
                path.chmod(0o755)


def test_cli_fails_explicitly_when_all_log_candidates_are_unwritable(
    python_exe, tmp_path, monkeypatch
):
    main = copy_fixture(tmp_path / "main")
    init_git(main)
    worktree = tmp_path / "worktree"
    git(main, "worktree", "add", "-b", "feature/unwritable-logs", str(worktree), "HEAD")

    ro_parent = tmp_path / "ro-parent"
    ro_parent.mkdir()
    fallback = ro_parent / "logs"
    monkeypatch.setenv("MDF_LOG_DIR", str(fallback))

    locked = [main / ".mdf", ro_parent]
    try:
        for path in locked:
            path.chmod(0o555)
        result = mdf(python_exe, "validate", "--repo", str(worktree), "--level", "strict")
        assert result.returncode == 1
        error = json.loads(result.stderr.strip().splitlines()[-1])
        assert error["ok"] is False
        assert error["error"] == "log_dir_unwritable"
        assert error["log"] is None
        assert error["details"]["candidates"] == [
            str(main.resolve() / ".mdf" / "logs"),
            str(fallback),
        ]
    finally:
        for path in reversed(locked):
            if path.exists():
                path.chmod(0o755)
