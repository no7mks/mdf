"""Issue #3 的检查范围、规则一致性与编码回归。"""

from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize("keep_fact", [False, True])
def test_deleted_source_is_not_uncovered(python_exe, tmp_path, keep_fact):
    repo = copy_fixture(tmp_path)
    source = repo / "src/obsolete.py"
    fact = repo / "docs/system/interfaces/obsolete.md"
    source.write_text("OLD = True\n")
    fact.write_text("---\ndoc_type: system-interfaces\nevidence: [src/obsolete.py]\n---\n\n# 旧接口\n")
    init_git(repo)
    source.unlink()
    if not keep_fact:
        fact.unlink()
    result = mdf(python_exe, "check", "--repo", str(repo), "--profile", "closeout", "--against", "HEAD")
    data = json.loads(result.stdout)
    assert "src/obsolete.py" not in data["implementation_paths"]
    assert not any(f["code"] == "audit.uncovered" for f in data["findings"])
    if keep_fact:
        assert "docs/system/interfaces/obsolete.md" in data["document_paths"]
        assert any(f["code"] == "evidence.missing_path" for f in data["findings"])


@pytest.mark.parametrize("invalid", [False, True])
def test_shared_module_findings_are_unique(python_exe, tmp_path, invalid):
    repo = copy_fixture(tmp_path)
    modules = repo / ".mdf/modules.yaml"
    modules.write_text("modules: invalid\n" if invalid else modules.read_text().replace(
        "    ignore: []", "    ignore:\n      - pattern: src/absent/**\n        reason: 过期规则"))
    init_git(repo)
    expected = "modules.invalid" if invalid else "audit.ignore_empty"
    for command in (("check", "--profile", "closeout"), ("fact-audit",)):
        result = mdf(python_exe, *command, "--repo", str(repo), "--scope", "full")
        data = json.loads(result.stdout)
        data = data.get("result", {}).get("audit", data)
        assert [f["code"] for f in data["findings"]].count(expected) == 1


@pytest.mark.parametrize("name", ["docs/system/interfaces/api.md", "docs/system/overview.md"])
def test_invalid_utf8_is_a_finding(python_exe, tmp_path, name):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    (repo / name).write_bytes(b"\xff\xfe")
    result = mdf(python_exe, "check", "--repo", str(repo), "--profile", "closeout", "--scope", "full")
    assert result.returncode == 2, result.stderr
    data = json.loads(result.stdout)
    assert any(f.get("path") == name and f["code"] == "fact.frontmatter" for f in data["findings"])


def test_ig_job_import_contract():
    import importlib
    from mdf_core.foundation.constants import TOOL_VERSION, PROTOCOL_VERSION, SCHEMA_VERSION
    from mdf_core.foundation.errors import MDFError

    assert TOOL_VERSION == PROTOCOL_VERSION == SCHEMA_VERSION == 3
    assert issubclass(MDFError, RuntimeError)
    for name in ("module_verify", "project_verify", "verify_run", "lint", "reports"):
        assert importlib.import_module(f"mdf_core.execution.{name}")


def test_ig_review_quick_report_contract(python_exe, tmp_path):
    from test_fact_inputs import report_files

    repo = copy_fixture(tmp_path)
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    ctx = payload(mdf(python_exe, "fact-audit", "--repo", str(repo), "--against", base, "--quick"))["result"]
    expected = {"schema_version": 3, "mode": "against", "operation": "fact-audit", "against": base}
    assert {key: ctx[key] for key in expected} == expected
    context_file, report_file = report_files(tmp_path, ctx)
    checked = payload(mdf(python_exe, "fact-audit-report-check", "--repo", str(repo),
                          "--context-file", context_file, "--report-file", report_file))
    assert checked["result"]["valid"] is True
    assert checked["result"]["decision"] == "pass"


@pytest.mark.parametrize("group", ["size", "prose", "overview"])
def test_invalid_utf8_remains_blocking_with_only(python_exe, tmp_path, group):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    (repo / "docs/system/overview.md").write_bytes(b"\xff")
    result = mdf(python_exe, "check", "--repo", str(repo), "--scope", "full", "--only", group)
    assert result.returncode == 2, result.stderr
    assert any(f["code"] == "document.encoding" for f in json.loads(result.stdout)["findings"])


@pytest.mark.parametrize("change", ["delete", "rename", "untracked", "never-matched"])
@pytest.mark.parametrize("scope", ["against", "full"])
def test_ignore_matching_agrees_across_entrypoints(python_exe, tmp_path, change, scope):
    repo = copy_fixture(tmp_path)
    source = repo / "src/generated.py"
    if change in {"delete", "rename"}:
        source.write_text("VALUE = 1\n")
    init_git(repo)
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace("    ignore: []",
        "    ignore:\n      - pattern: src/generated.py\n        reason: 生成文件"))
    if change == "delete":
        source.unlink()
    elif change == "rename":
        source.rename(repo / "src/renamed.py")
    elif change == "untracked":
        source.write_text("VALUE = 1\n")
    args = ("--against", "HEAD") if scope == "against" else ("--scope", "full")
    expected = change == "never-matched" or scope == "full"
    for command in (("check", "--profile", "closeout"), ("fact-audit",)):
        result = mdf(python_exe, *command, "--repo", str(repo), *args)
        data = json.loads(result.stdout)
        data = data.get("result", {}).get("audit", data)
        assert sum(f["code"] == "audit.ignore_empty" for f in data["findings"]) == int(expected)


def test_no_ignore_rules_skip_repository_file_probes(tmp_path, monkeypatch):
    from mdf_core.inspection.check_engine import check_payload
    from mdf_core.inspection.scan_context import RepoScanContext

    repo = copy_fixture(tmp_path)
    unrelated = repo / "src/unrelated.py"
    unrelated.write_text("VALUE = 1\n")
    init_git(repo)
    original = RepoScanContext.safe_file

    def guarded(scan, path):
        assert path != unrelated, "无 ignore 规则的单文件检查不得探测无关实现文件"
        return original(scan, path)

    monkeypatch.setattr(RepoScanContext, "safe_file", guarded)
    check_payload(repo, "dev", "paths", document_paths=["docs/system/interfaces/api.md"], only={"contract"})
