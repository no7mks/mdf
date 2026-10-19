"""Coverage CLI 的独立运行、覆写与原始运行报告。"""
from mdf_test_support import *  # noqa: F403


def configure(repo, *, covered=85, exit_code=0, override=False):
    script = repo / "coverage_command.py"
    script.write_text(
        "import json, os\nfrom pathlib import Path\n"
        f"data = {{'metrics': {{'lines': {{'covered': {covered}, 'total': 100}}, "
        "'branches': {'covered': 3, 'total': 4}}}\n"
        "Path(os.environ['MDF_REPORT_DIR'], 'coverage.json').write_text(json.dumps(data))\n"
        f"raise SystemExit({exit_code})\n"
    )
    definition = f"    coverage:\n      command: {sys.executable} coverage_command.py\n"
    definition += "      targets:\n        lines: 85\n        branches: 75\n"
    path = repo / ".mdf/modules.yaml"
    text = path.read_text()
    if override:
        text += "\nverification:\n" + "\n".join(line[2:] for line in definition.splitlines()) + "\n"
    else:
        text = text.replace("    ignore: []\n", "    ignore: []\n" + definition)
    path.write_text(text)


@pytest.mark.parametrize("override", [False, True])
def test_coverage_shortcut_runs_and_reports_all_metrics(python_exe, tmp_path, override):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    configure(repo, override=override)
    data = payload(mdf(python_exe, "verify", "coverage", "--repo", str(repo)))["result"]
    assert data["configured"] is True and data["all_passed"] is True
    assert len(data["results"]) == 1
    report = data["results"][0]
    assert report["report"]["metrics"]["branches"]["actual"] == 75
    assert (repo / report["log"] / "stdout.log").is_file()


@pytest.mark.parametrize("covered,exit_code", [(84, 0), (85, 3)])
def test_target_failure_and_command_failure_are_both_failures(python_exe, tmp_path, covered, exit_code):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    configure(repo, covered=covered, exit_code=exit_code)
    result = mdf(python_exe, "verify", "coverage", "--repo", str(repo))
    assert result.returncode != 0
    assert "verify_command_failed" in result.stderr


def test_unconfigured_and_stale_reports(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    args = ("verify", "coverage", "--repo", str(repo))
    assert payload(mdf(python_exe, *args))["result"]["configured"] is False
    configure(repo)
    assert_ok(mdf(python_exe, *args))
    (repo / "coverage_command.py").write_text("print('no report')\n")
    result = mdf(python_exe, *args)
    assert result.returncode != 0
    assert "coverage_failed" in result.stderr
