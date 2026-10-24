"""module ignore 对文档体积、单句与 prose-check 使用一致的排除语义。"""
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize("scope", ["full", "branch", "paths"])
def test_audit_ignore_exempts_document_limits(python_exe, tmp_path, scope):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    name = "docs/system/testing/conventions.md"
    page = repo / name
    page.write_text(page.read_text() + "\n" + ("长" * 101 + "。\n") * 451)
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "-m", "test: 扩大文档")
    extra = ["--base", base] if scope == "branch" else []
    if scope == "paths":
        extra = ["--document-path", name]
    args = ("fact-audit", "--repo", str(repo), "--scope", scope, *extra)
    result = mdf(python_exe, *args)
    assert result.returncode == 2
    codes = {item["code"] for item in json.loads(result.stdout)["findings"]}
    assert {"size.hard", "prose.sentence"} <= codes
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace('"src/**"', '"**"', 1).replace("    ignore: []", f"    ignore:\n      - pattern: {name}\n        reason: 保留外部手册"))
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "-m", "test: 排除外部手册")
    data = payload(mdf(python_exe, *args))
    assert data["findings"] == []
    assert name not in data['document_paths']
    assert all(row['document'] != name for row in data['mappings'])
    assert data["ignored"] == [{"path": name, "ignore_path": name, "reason": "保留外部手册"}]


@pytest.mark.parametrize("explicit", [False, True])
def test_prose_check_honors_module_ignore(python_exe, tmp_path, explicit):
    repo = copy_fixture(tmp_path)
    name = "docs/system/testing/conventions.md"
    page = repo / name
    page.write_text(page.read_text() + "\n" + "长" * 101 + "。\n")
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace('"src/**"', '"**"', 1).replace("    ignore: []", f"    ignore:\n      - pattern: {name}\n        reason: 保留外部手册"))
    init_git(repo)
    extra = ["--path", name] if explicit else []
    data = payload(mdf(python_exe, "prose-check", "--repo", str(repo), *extra))
    assert data["issues"] == []
    assert data["ignored"] == [name]
    if explicit:
        assert data["checked"] == 0


def test_prose_check_without_modules_still_checks_explicit_documents(python_exe, tmp_path):
    repo = tmp_path / "plain"
    repo.mkdir()
    (repo / "note.md").write_text("长" * 101 + "。\n")
    init_git(repo)
    result = mdf(python_exe, "prose-check", "--repo", str(repo), "--path", "note.md")
    assert result.returncode == 2
    assert [item["code"] for item in json.loads(result.stdout)["issues"]] == ["prose.sentence"]
