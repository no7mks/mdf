"""fact-audit 各 scope 不再检查代码行数，仍保留范围内的 ignore 依据。"""
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize("scope", ["full", "branch", "paths"])
@pytest.mark.parametrize("name", ["src/large.py", "tests/test_large.py"])
def test_audit_leaves_code_size_to_lint(python_exe, tmp_path, scope, name):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("pass\n" * 1001, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-m", "test: 添加大代码文件")
    extra = ["--base", base] if scope == "branch" else []
    if scope == "paths":
        extra = ["--implementation-path", name]
    result = mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", scope, *extra)
    assert result.returncode == 0
    findings = fact_audit_view(json.loads(result.stdout))["findings"]
    assert not findings

    path.write_text("pass\n" * 700, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-m", "test: 缩小代码文件")
    assert_ok(mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", scope, *extra))


@pytest.mark.parametrize("scope", ["full", "branch", "paths"])
@pytest.mark.parametrize("name", ["src/generated/large.py", "tests/generated/test_large.py"])
def test_module_ignore_exempts_code_size_only_for_matched_files(python_exe, tmp_path, scope, name):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    ignored = repo / name
    ignored.parent.mkdir(parents=True, exist_ok=True)
    ignored.write_text("pass\n" * 1001)
    other = repo / "src/other.py"
    other.write_text("pass\n" * 1001)
    pattern = name.rsplit("/", 1)[0] + "/**"
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace('"src/**"', '"**"', 1).replace("    ignore: []", f"    ignore:\n      - pattern: {pattern}\n        reason: 保留生成文件"))
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 添加 ignored 大代码文件")
    extra = ["--base", base] if scope == "branch" else []
    if scope == "paths":
        extra = ["--implementation-path", name, "--implementation-path", "src/other.py"]
    args = ("fact-audit", "--repo", str(repo), "--scope", scope, *extra)
    result = mdf(python_exe, *args)
    assert result.returncode == 0
    data = fact_audit_view(json.loads(result.stdout))
    assert not data["findings"]
    assert data["ignored"] == [{"path": name, "ignore_path": pattern, "reason": "保留生成文件"}]
    other.write_text("pass\n" * 700)
    git(repo, "add", "src/other.py")
    git(repo, "commit", "-m", "test: 缩小非 ignored 代码文件")
    assert_ok(mdf(python_exe, *args))
