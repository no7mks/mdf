"""fact-audit 在各 scope 检查代码行数，包括实现根外的测试代码。"""
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize("scope", ["full", "branch", "paths"])
@pytest.mark.parametrize("name", ["src/large.py", "tests/test_large.py"])
def test_audit_rejects_oversized_code(python_exe, tmp_path, scope, name):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("pass\n" * 1001, encoding="utf-8")
    git(repo, "add", name)
    extra = ["--base", base] if scope == "branch" else []
    if scope == "paths":
        extra = ["--implementation-path", name]
    result = mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", scope, *extra)
    assert result.returncode == 2
    findings = json.loads(result.stdout)["findings"]
    assert [(item["code"], item["path"]) for item in findings] == [("code.size", name)]
    assert "700 行" in findings[0]["message"]

    path.write_text("pass\n" * 700, encoding="utf-8")
    assert_ok(mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", scope, *extra))
