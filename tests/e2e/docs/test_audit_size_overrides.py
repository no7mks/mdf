"""module size_limits 从 YAML 到各 scope 的真实检查，并保持文档规则不变。"""
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize("scope", ["full", "branch", "paths"])
def test_audit_uses_module_size_overrides(python_exe, tmp_path, scope):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    path = repo / "src/large.py"
    path.write_text("pass\n" * 1100)
    package = repo / "src/package"
    package.mkdir()
    for index in range(55):
        (package / f"unit_{index}.py").write_text("pass\n")
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace("    ignore: []\n",
        "    ignore: []\n    size_limits:\n      max_file_lines: 1200\n"
        "      max_package_files: 60\n      split_percent: 60\n"))
    git(repo, "add", "--all")
    extra = ["--base", base] if scope == "branch" else []
    if scope == "paths":
        extra = ["--implementation-path", "src/large.py", "--implementation-path", "src/package/unit_0.py"]
    args = ("fact-audit", "--repo", str(repo), "--scope", scope, *extra)
    assert_ok(mdf(python_exe, *args))
    path.write_text("pass\n" * 1201)
    for index in range(55, 61):
        (package / f"unit_{index}.py").write_text("pass\n")
    git(repo, "add", "--all")
    result = mdf(python_exe, *args)
    assert result.returncode == 2
    findings = json.loads(result.stdout)["findings"]
    assert [item["code"] for item in findings] == ["code.size", "package.size"]
    assert "module default" in findings[0]["message"] and "720 行" in findings[0]["message"]
    assert "module default" in findings[1]["message"] and "36 个" in findings[1]["message"]


def test_module_split_percent_does_not_override_document_rules(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    page = repo / "docs/system/testing/conventions.md"
    page.write_text(page.read_text() + "\n" + ("长" * 101 + "。\n") * 451)
    modules = repo / ".mdf/modules.yaml"
    text = modules.read_text().replace('      - "src/**"\n', '      - "src/**"\n      - "docs/**"\n')
    modules.write_text(text.replace("    ignore: []\n",
        "    ignore: []\n    size_limits:\n      split_percent: 20\n"))
    init_git(repo)
    result = mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", "full")
    assert result.returncode == 2
    findings = json.loads(result.stdout)["findings"]
    size = [item for item in findings if item["code"] == "size.hard"]
    assert len(size) == 1 and "315 行" in size[0]["message"]
    sentences = [item for item in findings if item["code"] == "prose.sentence"]
    assert sentences and all("200" in item["message"] and "140" in item["message"] for item in sentences)
