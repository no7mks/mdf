"""fact-audit 不再检查 package 规模，ignore 报告只包含事实审计范围。"""
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize("scope", ["full", "branch", "paths"])
@pytest.mark.parametrize("folder", ["src/large", "tests/large"])
def test_audit_package_scope_and_ignore(python_exe, tmp_path, scope, folder):
    repo = copy_fixture(tmp_path)
    directory = repo / folder
    directory.mkdir(parents=True)
    for index in range(51):
        (directory / f"unit_{index}.py").write_text("pass\n")
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    name = f"{folder}/unit_0.py"
    (repo / name).write_text("pass  # touched\n")
    extra = ["--base", base] if scope == "branch" else []
    if scope == "paths":
        extra = ["--implementation-path", name]
    args = ("fact-audit", "--repo", str(repo), "--scope", scope, *extra)
    result = mdf(python_exe, *args)
    assert result.returncode == 0
    findings = json.loads(result.stdout)["findings"]
    assert not findings
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace("    ignore: []\n",
        f"    ignore:\n      - pattern: {folder}/unit_50.py\n        reason: 生成文件\n"))
    data = payload(mdf(python_exe, *args))
    expected = ([{"path": f"{folder}/unit_50.py",
                  "ignore_path": f"{folder}/unit_50.py", "reason": "生成文件"}] if scope == "full" else [])
    assert data["ignored"] == expected


def test_branch_audit_checks_package_after_deleting_a_member(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    directory = repo / "src/large"
    directory.mkdir()
    for index in range(52):
        (directory / f"unit_{index}.py").write_text("pass\n")
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    (directory / "unit_51.py").unlink()
    git(repo, "add", "--all")
    result = mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", "branch", "--base", base)
    assert result.returncode == 0
    assert not json.loads(result.stdout)["findings"]


@pytest.mark.parametrize("scope", ["branch", "paths"])
@pytest.mark.parametrize("deleted", [False, True])
@pytest.mark.parametrize("overlap", [False, True])
def test_ignored_member_does_not_trigger_package_check(python_exe, tmp_path, scope, deleted, overlap):
    repo = copy_fixture(tmp_path)
    directory = repo / "src/large"
    directory.mkdir()
    for index in range(51):
        (directory / f"unit_{index}.py").write_text("pass\n")
    for name in ["generated_one.py", "generated_two.py"]:
        (directory / name).write_text("pass\n")
    modules = repo / ".mdf/modules.yaml"
    rules = "    ignore:\n      - pattern: src/large/generated_*.py\n        reason: 生成文件\n"
    if overlap:
        rules += "      - pattern: src/large/generated_two.py\n        reason: 单个生成文件\n"
    modules.write_text(modules.read_text().replace("    ignore: []\n", rules))
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    name = "src/large/generated_one.py"
    if deleted:
        (repo / name).unlink()
        git(repo, "add", "--all")
        if scope == "paths":
            name = "src/large/generated_two.py"
    else:
        (repo / name).write_text("pass  # touched\n")
    extra = ["--base", base] if scope == "branch" else ["--implementation-path", name]
    assert_ok(mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", scope, *extra))
    full = mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", "full")
    assert full.returncode == 0
    assert not json.loads(full.stdout)["findings"]
