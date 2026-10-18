"""fact-audit 对触及 package 检查完整成员，并遵守 module ignore。"""
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
    assert result.returncode == 2
    findings = json.loads(result.stdout)["findings"]
    assert [(item["code"], item["path"]) for item in findings] == [("package.size", folder)]
    assert "51" in findings[0]["message"] and "35" in findings[0]["message"]
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace("    ignore: []\n",
        f"    ignore:\n      - pattern: {folder}/unit_50.py\n        reason: 生成文件\n"))
    data = payload(mdf(python_exe, *args))
    assert data["ignored"] == [{"path": f"{folder}/unit_50.py",
                               "ignore_path": f"{folder}/unit_50.py", "reason": "生成文件"}]


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
    assert result.returncode == 2
    assert [(item["code"], item["path"]) for item in json.loads(result.stdout)["findings"]] == [
        ("package.size", "src/large")]
