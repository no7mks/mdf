"""suite 报告写入 verify.branch 证据，以及 named scope 运行。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def _register_billing(repo: Path, command: str = SUITE_OK) -> None:
    modules = repo / ".mdf/modules.yaml"
    text = modules.read_text(encoding="utf-8")
    if "billing" not in text:
        text = text.replace("named: []", "named:\n      - billing")
        modules.write_text(text, encoding="utf-8")
    doc = repo / "docs/system/testing/billing.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "---\n"
        f'command: "{command}"\n'
        "---\n\n"
        "# billing\n\n"
        "目的：计费回归。\n\n"
        "testcase 构成：计费相关用例。\n",
        encoding="utf-8",
    )


def test_verify_records_suite_reports_and_rejects_skipped(python_exe, tmp_path):
    repo, root = converge_ready(python_exe, tmp_path)
    payload(mdf(python_exe, "verify", "--scope", "branch", "--repo", str(repo)))
    evidence = json.loads((root / "verification-report.json").read_text())
    assert evidence["scope"] == "branch"
    assert "level" not in evidence
    reports = {item["id"]: item.get("report") for item in evidence["results"]}
    assert reports["lint:default"] is None and reports["build:default"] is None
    assert reports["quick:default"]["suite"] == "quick"
    assert reports["smoke:default"]["tests"] == 1
    assert (repo / reports["smoke:default"]["path"] / "r.xml").is_file()
    assert ".mdf/" not in git(repo, "status", "--porcelain").stdout
    patch_module_command(
        repo,
        "quick",
        lambda c: c.replace("<testcase/>", "<testcase><skipped/></testcase>"),
    )
    commit(repo, "test: quick 含 skipped")
    result = mdf(python_exe, "verify", "--scope", "branch", "--repo", str(repo))
    assert "verify_command_failed" in result.stderr
    evidence = json.loads((root / "verification-report.json").read_text())
    quick = next(
        item for item in evidence["results"] if item["id"] == "quick:default"
    )
    assert quick["passed"] is False and quick["error"] == "test_report_failed"
    assert quick["details"]["report"]["skipped"] == 1


def test_verify_named_reports_suite(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    _register_billing(repo, SUITE_OK)
    result = payload(
        mdf(
            python_exe,
            "verify",
            "--scope",
            "named",
            "--suites",
            "billing",
            "--repo",
            str(repo),
        )
    )
    item = result["result"]["results"][0]
    assert item["report"]["suite"] == "billing"
    assert item["report"]["path"].startswith(".mdf/reports/")
    assert item["report"]["path"].endswith("-billing")
    reserved = mdf(
        python_exe,
        "verify",
        "--scope",
        "named",
        "--suites",
        "full",
        "--repo",
        str(repo),
    )
    assert "invalid_delivery_suite" in reserved.stderr
    _register_billing(repo, "true")
    missing = mdf(
        python_exe,
        "verify",
        "--scope",
        "named",
        "--suites",
        "billing",
        "--repo",
        str(repo),
    )
    assert "missing_test_report" in missing.stderr


def test_verify_named_fixed_suite_quick(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = payload(
        mdf(
            python_exe,
            "verify",
            "--scope",
            "named",
            "--suites",
            "quick",
            "--repo",
            str(repo),
        )
    )
    assert [item["id"] for item in result["result"]["results"]] == ["quick:default"]
    assert result["result"]["all_passed"] is True


def test_verify_named_parallel_rejects_over_five(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    modules = repo / ".mdf/modules.yaml"
    text = modules.read_text(encoding="utf-8")
    text = text.replace("named: []", "named:\n      - bulk")
    modules.write_text(text, encoding="utf-8")
    commands = "\n".join(f'  - "{SUITE_OK}"' for _ in range(6))
    doc = repo / "docs/system/testing/bulk.md"
    doc.write_text(
        "---\n"
        f"commands:\n{commands}\n"
        "parallel: true\n"
        "---\n\n"
        "# bulk\n\n目的：并行上限。\n\ntestcase 构成：六条。\n",
        encoding="utf-8",
    )
    result = mdf(
        python_exe,
        "verify",
        "--scope",
        "named",
        "--suites",
        "bulk",
        "--repo",
        str(repo),
    )
    assert "too_many_parallel_commands" in result.stderr


@pytest.mark.parametrize("target", ["billing", "quick"])
def test_verify_suite_shortcut(python_exe, tmp_path, target):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    _register_billing(repo)
    result = payload(mdf(python_exe, "verify", target, "--repo", str(repo)))
    assert result["result"]["suites"] == [target]
    assert result["result"]["all_passed"] is True


@pytest.mark.parametrize("target", ["smart", "branch"])
def test_verify_scope_shortcut(python_exe, tmp_path, target):
    repo, root = converge_ready(python_exe, tmp_path)
    extra = ["--module", "default"] if target == "smart" else []
    result = payload(mdf(python_exe, "verify", target, *extra, "--repo", str(repo)))
    assert result["result"]["scope"] == target


def test_verify_named_shortcut_and_conflicting_scope(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = payload(mdf(
        python_exe, "verify", "named", "--suites", "quick", "--repo", str(repo),
    ))
    assert result["result"]["suites"] == ["quick"]
    conflict = mdf(
        python_exe, "verify", "quick", "--scope", "branch", "--repo", str(repo),
    )
    assert "invalid_verify_scope" in conflict.stderr
