"""独立 quick 的 stale、范围、CI 与非语义检查边界。"""
from mdf_test_support import *  # noqa: F403


FACT = "docs/system/interfaces/api.md"


def quick(python_exe, repo, *args):
    return mdf(python_exe, "fact-audit", "--repo", str(repo), "--quick", *args)


def test_quick_skips_contract_structure_coverage_and_semantics(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    (repo / "AGENTS.md").unlink()
    (repo / "src/uncovered.py").write_text("VALUE = 1\n")
    fact = repo / FACT
    fact.write_text(fact.read_text().replace("doc_type: system-interfaces", "doc_type: invalid")
                    + "\n`healthy()` 返回错误的描述。\n" + "无关超长文字\n" * 600)
    init_git(repo)
    result = quick(python_exe, repo)
    assert_ok(result)
    data = json.loads(result.stdout)
    assert data["mode"] == "quick" and data["semantic_review"] is False
    assert data["scope"] == "full" and FACT in data["document_paths"]
    assert data["findings"] == []
    assert "契约检查" not in result.stderr and "文档结构检查" not in result.stderr
    assert not (repo / "audit-ran").exists()
    assert mdf(python_exe, "fact-audit", "--repo", str(repo)).returncode == 2


@pytest.mark.parametrize("state", ["committed", "deleted"])
def test_quick_rejects_changed_evidence(python_exe, tmp_path, state):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    source = repo / "src/service.py"
    if state == "deleted":
        source.unlink()
    else:
        source.write_text(source.read_text() + "\n# 新实现\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "test: 更新实现")
    result = quick(python_exe, repo, "--scope", "branch", "--base", base)
    assert_ok(result)
    data = fact_audit_view(json.loads(result.stdout))
    assert FACT in data["document_paths"]
    expected = "evidence.missing_path" if state == "deleted" else "evidence.stale"
    assert expected in {item["code"] for item in data["findings"]}
    assert data["semantic_review"] is False and data["mode"] == "quick"


def test_quick_allows_dirty_worktree(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    (repo / "scratch.txt").write_text("dirty\n")
    result = quick(python_exe, repo)
    assert "dirty_worktree" not in result.stderr
    data = json.loads(result.stdout)
    assert data["mode"] == "quick"
    assert_ok(result)


def test_quick_passes_after_document_revalidation(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    source = repo / "src/service.py"
    source.write_text(source.read_text() + "\n# 新实现\n")
    git(repo, "add", "src/service.py")
    git(repo, "commit", "-m", "test: 更新实现")
    fact = repo / FACT
    fact.write_text(fact.read_text() + "\n已复核当前实现。\n")
    git(repo, "add", FACT)
    git(repo, "commit", "-m", "docs: 复核事实")
    assert_ok(quick(python_exe, repo, "--scope", "paths", "--document-path", FACT))
    assert quick(python_exe, repo, "--scope", "full").returncode == 2


@pytest.mark.parametrize("reference", ["directory", "generated"])
def test_quick_maps_directory_and_generated_dependencies(python_exe, tmp_path, reference):
    repo = copy_fixture(tmp_path)
    fact = repo / FACT
    if reference == "directory":
        fact.write_text(fact.read_text().replace("path: src/service.py", "path: src"))
    else:
        generator = repo / "src/generator.py"
        generator.write_text("#!/usr/bin/env python3\nraise RuntimeError('不得运行')\n")
        generator.chmod(0o755)
        fact.write_text(fact.read_text().replace("evidence:\n", "generated:\n  source: src/service.py\n"
                                               "  generator: src/generator.py\nevidence:\n"))
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    source = repo / ("src/service.py" if reference == "directory" else "src/generator.py")
    source.write_text(source.read_text() + "\n# 新版本\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "test: 更新依赖")
    for args in (("--scope", "branch", "--base", base),
                 ("--scope", "paths", "--implementation-path", source.relative_to(repo).as_posix())):
        result = quick(python_exe, repo, *args)
        data = fact_audit_view(json.loads(result.stdout))
        if args[0] == "--scope" and args[1] == "branch":
            assert_ok(result)
        else:
            assert result.returncode == 2
        assert FACT in data["document_paths"]
        code = "generated.stale" if reference == "generated" else "evidence.stale"
        assert code in {item["code"] for item in data["findings"]}


@pytest.mark.parametrize("failure", ["missing", "frontmatter"])
def test_quick_cannot_pass_unverifiable_evidence(python_exe, tmp_path, failure):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    fact = repo / FACT
    if failure == "frontmatter":
        fact.write_text("缺少 frontmatter\n")
        expected = "fact.frontmatter"
    else:
        fact.write_text(fact.read_text().replace("src/service.py", "src/unknown.py"))
        expected = "evidence.missing_path"
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "test: 不可判定证据")
    result = quick(python_exe, repo, "--scope", "paths", "--document-path", FACT)
    assert result.returncode == 2
    assert expected in result.stdout


def test_quick_respects_document_ignore(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace('      - "src/**"', '      - "src/**"\n      - "docs/**"', 1)
                       .replace("    ignore: []", f"    ignore:\n      - pattern: {FACT}\n        reason: 非当前事实", 1))
    init_git(repo)
    result = quick(python_exe, repo, "--scope", "paths", "--document-path", FACT)
    assert_ok(result)
    assert json.loads(result.stdout)["document_paths"] == []
    assert json.loads(result.stdout)["ignored"] == [FACT]


def test_quick_explicit_document_does_not_validate_unrelated_page(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    (repo / "docs/system/data/model.md").write_text("缺少 frontmatter\n")
    init_git(repo)
    result = quick(python_exe, repo, "--scope", "paths", "--document-path", FACT)
    assert_ok(result)
    assert payload(result)["document_paths"] == [FACT]


@pytest.mark.parametrize("args", [
    ("--against", "HEAD", "--scope", "full"), ("--scope", "paths"),
    ("--scope", "full", "--base", "HEAD"),
    ("--scope", "branch", "--document-path", FACT), ("--scope", "branch", "--base", "unknown"),
])
def test_quick_invalid_arguments_fail(python_exe, tmp_path, args):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    assert quick(python_exe, repo, *args).returncode != 0


def test_quick_with_against_is_allowed(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    data = payload(quick(python_exe, repo, "--against", base))
    assert data["semantic_review"] is False and data["result"]["against"] == base


def test_quick_rejects_shallow_ci_checkout(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    clone = tmp_path / "shallow"
    git(tmp_path, "clone", "--depth", "1", repo.as_uri(), str(clone))
    result = quick(python_exe, clone)
    assert result.returncode == 2
    assert "audit.shallow" in result.stdout


@pytest.mark.parametrize("destination", ["src/renamed.py", "outside/renamed.py"])
def test_quick_branch_retains_renamed_evidence_old_path(python_exe, tmp_path, destination):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / destination).parent.mkdir(exist_ok=True)
    git(repo, "mv", "src/service.py", destination)
    git(repo, "commit", "-m", "test: 重命名证据")
    result = quick(python_exe, repo, "--scope", "branch", "--base", base)
    assert_ok(result)
    data = fact_audit_view(json.loads(result.stdout))
    assert FACT in data["document_paths"]
    assert any(item["code"] == "evidence.missing_path" and item["path"] == FACT for item in data["findings"])


@pytest.mark.parametrize("scope", ["full", "branch"])
def test_quick_detects_submodule_directory_stale_despite_diff_ignore(python_exe, tmp_path, scope):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    initial = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "deps").mkdir()
    (repo / "deps/README.md").write_text("dependency\n")
    replace(repo / FACT, "path: src/service.py", "path: deps")
    replace(repo / ".mdf/modules.yaml", '      - "src/**"', '      - "src/**"\n      - "deps/**"')
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{initial},deps/sub")
    git(repo, "add", "deps/README.md", FACT, ".mdf/modules.yaml")
    git(repo, "commit", "-m", "test: 记录目录证据")
    dependency = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "update-index", "--cacheinfo", f"160000,{dependency},deps/sub")
    git(repo, "commit", "-m", "test: 更新依赖")
    git(repo, "config", "diff.ignoreSubmodules", "all")
    extra = ("--base", dependency) if scope == "branch" else ()
    result = quick(python_exe, repo, "--scope", scope, *extra)
    data = fact_audit_view(json.loads(result.stdout))
    if scope == "branch":
        assert_ok(result)
    else:
        assert result.returncode == 2
    assert any(item["code"] == "evidence.stale" and item["path"] == FACT
               for item in data["findings"])
