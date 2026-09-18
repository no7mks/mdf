"""v3 文档布局：user-guide 事实页、ADR 位置、体积限制与 branch 范围审计。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403


def _codes(result) -> list[str]:
    return [item["code"] for item in json.loads(result.stdout)["findings"]]


def test_user_guide_pages_require_user_guide_doc_type(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    topic = repo / "docs" / "user-guide" / "health.md"
    topic.write_text(
        (repo / "docs" / "user-guide" / "README.md")
        .read_text(encoding="utf-8")
        .replace("doc_type: user-guide", "doc_type: system-interfaces"),
        encoding="utf-8",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "fact.doc_type_path" in _codes(result)

    replace(topic, "doc_type: system-interfaces", "doc_type: user-guide")
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "-m", "test: 修正 doc_type")
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full"))


def test_retired_docs_directories_report_layout_migrate(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    (repo / "docs" / "product" / "reference").mkdir(parents=True)
    (repo / "docs" / "product" / "reference" / "old.md").write_text("# 旧页\n", encoding="utf-8")
    (repo / "docs" / "adr").mkdir()
    init_git(repo)

    result = mdf(python_exe, "doctor", "--repo", str(repo))
    data = payload(result)
    codes = [item["code"] for item in data["findings"]]
    assert codes.count("layout.migrate") == 2
    assert data["normal_workflows_allowed"] is False
    assert any("$mdf migrate" in item["message"] for item in data["findings"])


def test_schema_version_mismatch_points_to_migrate(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    replace(repo / ".mdf" / "manifest.yaml", "schema_version: 3", "schema_version: 2")
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    finding = next(
        item for item in json.loads(result.stdout)["findings"]
        if item["code"] == "manifest.schema"
    )
    assert "$mdf migrate" in finding["message"]


def test_adrs_live_under_context(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    adr = repo / "docs" / "context" / "adr" / "use-sqlite.md"
    adr.parent.mkdir(parents=True)
    adr.write_text(
        "---\nid: adr-use-sqlite\ntype: adr\nstatus: accepted\n---\n\n# 使用 SQLite\n",
        encoding="utf-8",
    )
    init_git(repo)
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full"))

    replace(adr, "id: adr-use-sqlite", "id: adr-other")
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "adr.id" in _codes(result)


@pytest.mark.parametrize(
    ("relative_path", "lines", "expected"),
    [
        ("docs/README.md", 121, "size.hard"),
        ("docs/README.md", 81, "size.soft"),
        ("docs/system/overview.md", 121, "size.hard"),
        ("docs/system/interfaces/index.md", 121, "size.hard"),
        ("docs/system/interfaces/api.md", 501, "size.hard"),
        ("docs/system/interfaces/api.md", 401, "size.soft"),
        ("docs/user-guide/README.md", 121, "size.hard"),
        ("docs/user-guide/topic.md", 401, "size.soft"),
        ("PROJECT.md", 401, "size.hard"),
        ("PROJECT.md", 201, "size.soft"),
        ("docs/context/adr/use-sqlite.md", 401, "size.hard"),
        ("docs/proposals/prp-001-service-health.md", 501, "size.hard"),
    ],
)
def test_audit_enforces_size_limits_by_role(
    python_exe: str, tmp_path: Path, relative_path: str, lines: int, expected: str
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    path = repo / relative_path
    if path.exists():
        text = path.read_text(encoding="utf-8")
    elif relative_path.startswith("docs/context/adr/"):
        text = "---\nid: adr-use-sqlite\ntype: adr\nstatus: accepted\n---\n\n# ADR\n"
    elif relative_path.startswith("docs/system/interfaces/"):
        text = (repo / "docs/system/interfaces/api.md").read_text(encoding="utf-8")
    elif relative_path.startswith("docs/user-guide/"):
        text = (repo / "docs/user-guide/README.md").read_text(encoding="utf-8")
    else:
        text = "# 页面\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    body_lines = text.splitlines()
    while len(body_lines) < lines:
        body_lines.append("填充行。")
    path.write_text("\n".join(body_lines) + "\n", encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "-m", "test: 撑大文档")

    result = mdf(python_exe, "fact-audit", "--repo", str(repo))
    data = json.loads(result.stdout)
    if expected == "size.hard":
        assert result.returncode == 2
        hits = [item for item in data["findings"] if item["code"] == "size.hard"]
    else:
        assert_ok(result)
        hits = [item for item in data["warnings"] if item["code"] == "size.soft"]
    assert [item["path"] for item in hits] == [relative_path]


def test_agents_size_counts_only_managed_block(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    agents = repo / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    agents.write_text("\n".join(["自定义规则。"] * 300) + "\n" + text, encoding="utf-8")
    init_git(repo)

    data = payload(mdf(python_exe, "fact-audit", "--repo", str(repo)))
    assert data["warning_count"] == 0


def test_glossary_and_changes_are_not_sized(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    (repo / "GLOSSARY.md").write_text("# 词典\n" + "词。\n" * 600, encoding="utf-8")
    init_git(repo)
    data = payload(mdf(python_exe, "fact-audit", "--repo", str(repo)))
    assert data["finding_count"] == 0 and data["warning_count"] == 0


def test_branch_scope_maps_changed_implementation_to_fact_pages(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "-b", "feature/health")
    service = repo / "src" / "service.py"
    service.write_text(service.read_text(encoding="utf-8") + "\n# tweak\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "feat: 调整实现")
    (repo / "docs/README.md").write_text(
        (repo / "docs/README.md").read_text(encoding="utf-8") + "补充。\n" * 200,
        encoding="utf-8",
    )

    data = json.loads(
        mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", "branch").stdout
    )
    assert data["base"] == base
    assert data["implementation_paths"] == ["src/service.py"]
    assert set(data["document_paths"]) == {
        "docs/system/architecture/current.md",
        "docs/system/data/model.md",
        "docs/system/deviations.md",
        "docs/system/interfaces/api.md",
        "docs/system/operations/runbook.md",
        "docs/system/overview.md",
        "docs/user-guide/README.md",
    }
    hard = [item["path"] for item in data["findings"] if item["code"] == "size.hard"]
    assert hard == ["docs/README.md"]

    (repo / "docs/README.md").write_text("# Documentation\n", encoding="utf-8")
    explicit = json.loads(
        mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", "branch", "--base", base).stdout
    )
    assert explicit["implementation_paths"] == ["src/service.py"]
    assert explicit["base"] == base
    # 实现晚于事实页提交：范围内事实页应报 evidence.stale，而非被 branch 范围遗漏。
    assert {item["code"] for item in explicit["findings"]} == {"evidence.stale"}


def test_branch_scope_ignores_unrelated_fact_pages(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    git(repo, "checkout", "-q", "-b", "feature/docs")
    page = repo / "docs/system/interfaces/api.md"
    page.write_text(page.read_text(encoding="utf-8") + "\n补充说明。\n", encoding="utf-8")

    data = payload(mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", "branch"))
    assert data["implementation_paths"] == []
    assert data["document_paths"] == ["docs/system/interfaces/api.md"]


def test_branch_scope_rejects_paths_and_missing_base(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    init_git(repo)

    result = mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", "branch")
    assert result.returncode == 2
    assert "audit.base" in _codes(result)

    result = mdf(
        python_exe, "fact-audit", "--repo", str(repo), "--scope", "branch",
        "--base", "HEAD", "--implementation-path", "src/service.py",
    )
    assert result.returncode == 2
    assert "audit.scope" in _codes(result)

    result = mdf(
        python_exe, "fact-audit", "--repo", str(repo), "--scope", "full", "--base", "HEAD"
    )
    assert result.returncode == 2
    assert "audit.scope" in _codes(result)
