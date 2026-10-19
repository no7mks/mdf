"""统一 lint 的代码规模、完整 package、ignore 与各入口边界。"""
from mdf_test_support import *  # noqa: F403


def latest_summary(repo):
    paths = list((repo / ".mdf/reports").glob("*-lint/summary.json"))
    return json.loads(max(paths, key=lambda path: path.stat().st_mtime_ns).read_text())


@pytest.mark.parametrize("args", [("lint",), ("--scope", "named", "--suites", "lint"),
                                 ("--scope", "smart", "--module", "default")])
def test_lint_rejects_code_size_without_requiring_third_party_tools(python_exe, tmp_path, args):
    repo = copy_fixture(tmp_path)
    path = repo / "src/large.py"
    path.write_text("pass\n" * 1001)
    init_git(repo)
    result = mdf(python_exe, "verify", *args, "--repo", str(repo))
    assert result.returncode != 0
    findings = latest_summary(repo)["findings"]
    assert [(item["code"], item["path"]) for item in findings] == [("code.size", "src/large.py")]
    assert "700 行" in findings[0]["message"]
    path.write_text("pass\n" * 700)
    assert_ok(mdf(python_exe, "verify", *args, "--repo", str(repo)))


def test_lint_uses_overrides_and_complete_package_counts(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    path = repo / "src/large.py"
    path.write_text("pass\n" * 1201)
    package = repo / "src/package"
    package.mkdir()
    for index in range(61):
        (package / f"unit_{index}.py").write_text("pass\n")
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace("    ignore: []\n",
        "    ignore: []\n    size_limits:\n      max_file_lines: 1200\n"
        "      max_package_files: 60\n      split_percent: 60\n"))
    init_git(repo)
    args = ("verify", "lint", "--repo", str(repo))
    assert mdf(python_exe, *args).returncode != 0
    findings = latest_summary(repo)["findings"]
    assert [item["code"] for item in findings] == ["code.size", "package.size"]
    assert "720 行" in findings[0]["message"] and "36 个" in findings[1]["message"]
    modules.write_text(modules.read_text().replace("    ignore: []\n",
        "    ignore:\n      - pattern: src/large.py\n        reason: 生成文件\n"
        "      - pattern: src/package/unit_60.py\n        reason: 生成文件\n"))
    assert_ok(mdf(python_exe, *args))


def test_all_module_lint_also_checks_unowned_sources(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    (repo / "unowned.py").write_text("pass\n" * 1001)
    init_git(repo)
    assert mdf(python_exe, "verify", "lint", "--repo", str(repo)).returncode != 0
    assert latest_summary(repo)["findings"][0]["path"] == "unowned.py"
    assert_ok(mdf(python_exe, "verify", "smart", "--module", "default", "--repo", str(repo)))


def test_selected_ignored_member_does_not_expand_package_scope(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    package = repo / "generated"
    package.mkdir()
    for index in range(51):
        (package / f"unit_{index}.py").write_text("pass\n")
    path = repo / ".mdf/modules.yaml"
    text = path.read_text()
    first = text.index("    sourceset:")
    last = text.index("    ignore: []", first)
    text = text[:first] + "    sourceset:\n      - generated/unit_0.py\n" + text[last:]
    path.write_text(text.replace("    ignore: []\n",
        "    ignore:\n      - pattern: generated/unit_0.py\n        reason: 生成文件\n"))
    init_git(repo)
    assert_ok(mdf(python_exe, "verify", "smart", "--module", "default", "--repo", str(repo)))
    assert latest_summary(repo)["all_passed"] is True


def test_project_lint_command_failure_is_not_hidden_by_clean_structure(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    patch_module_command(repo, "lint", lambda command: "exit 3")
    assert mdf(python_exe, "verify", "lint", "--repo", str(repo)).returncode != 0
    assert latest_summary(repo)["all_passed"] is False
    assert latest_summary(repo)["structure_passed"] is True
