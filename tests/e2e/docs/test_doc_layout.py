"""文档布局、doc_type、按角色体积限制与 branch 范围审计。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def _codes(result) -> list[str]:
    return [item["code"] for item in json.loads(result.stdout)["findings"]]


def test_fact_pages_allow_product_macros(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    page = repo / "docs" / "user-guide" / "README.md"
    page.write_text(
        page.read_text(encoding="utf-8")
        + "\n角色宏为 `{{char}}`、{{ user }}、{{API_KEY}}。\n",
        encoding="utf-8",
    )
    init_git(repo)
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))

    replace(page, "`{{char}}`", "`{{MDF_EVIDENCE_PATH}}`")
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "-m", "test: 留下模板占位")
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "fact.marker" in _codes(result)


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


def test_docs_testing_handbook_reports_layout_migrate(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    (repo / "docs" / "testing.md").write_text("# 旧测试手册\n", encoding="utf-8")
    init_git(repo)

    result = mdf(python_exe, "doctor", "--repo", str(repo))
    data = payload(result)
    codes = [item["code"] for item in data["findings"]]
    assert "layout.migrate" in codes
    assert any(
        item["path"] == "docs/testing.md" for item in data["findings"]
    )


def test_missing_testing_facet_reports_layout_testing(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    for path in (repo / "docs" / "system" / "testing").glob("*.md"):
        path.unlink()
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "layout.testing" in _codes(result)


def test_testing_pages_require_system_testing_doc_type(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    page = repo / "docs" / "system" / "testing" / "conventions.md"
    replace(page, "doc_type: system-testing", "doc_type: system-operations")
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "fact.doc_type_path" in _codes(result)

    replace(page, "doc_type: system-operations", "doc_type: system-testing")
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "-m", "test: 修正 testing doc_type")
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


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
    ("relative_path", "lines"),
    [
        ("README.md", 201),
        ("docs/README.md", 101),
        ("docs/system/overview.md", 101),
        ("docs/system/interfaces/index.md", 101),
        ("docs/system/testing/index.md", 101),
        ("docs/system/interfaces/api.md", 451),
        ("docs/user-guide/README.md", 101),
        ("docs/user-guide/topic.md", 451),
        ("PROJECT.md", 101),
        ("docs/context/adr/use-sqlite.md", 301),
        ("docs/proposals/prp-001-service-health.md", 501),
    ],
)
def test_audit_enforces_size_limits_by_role(
    python_exe: str, tmp_path: Path, relative_path: str, lines: int
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
    assert result.returncode == 2
    hits = [item for item in data["findings"] if item["code"] == "size.hard"]
    assert [item["path"] for item in hits] == [relative_path]
    assert not any(item["code"] == "size.soft" for item in data["warnings"])


def test_agents_size_counts_only_managed_block(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    agents = repo / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    agents.write_text("\n".join(["自定义规则。"] * 300) + "\n" + text, encoding="utf-8")
    init_git(repo)

    data = payload(mdf(python_exe, "fact-audit", "--repo", str(repo)))
    assert data["finding_count"] == 0
    assert [item["code"] for item in data["warnings"]] == ["agents.size"]


def test_agents_size_warning_can_be_ignored(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    agents = repo / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    agents.write_text("\n".join(["自定义规则。"] * 300) + "\n" + text, encoding="utf-8")
    (repo / ".mdf" / "audit-ignore.yaml").write_text(
        "ignored:\n  - path: AGENTS.md\n    reason: 保留托管块外说明\n",
        encoding="utf-8",
    )
    init_git(repo)
    data = payload(mdf(python_exe, "fact-audit", "--repo", str(repo)))
    assert data["finding_count"] == 0
    assert data["warning_count"] == 0
    assert data["ignored"] == [
        {
            "path": "AGENTS.md",
            "ignore_path": "AGENTS.md",
            "reason": "保留托管块外说明",
        }
    ]


def test_glossary_and_changes_are_not_sized(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    (repo / "GLOSSARY.md").write_text("# 词典\n" + "词。\n" * 600, encoding="utf-8")
    init_git(repo)
    data = payload(mdf(python_exe, "fact-audit", "--repo", str(repo)))
    assert data["finding_count"] == 0 and data["warning_count"] == 0


def test_audit_reports_overview_core_module_shape(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    overview = repo / "docs" / "system" / "overview.md"
    text = overview.read_text(encoding="utf-8")
    overview.write_text(
        text.replace("| 鉴权 | 不适用：此夹具无鉴权面 |\n", ""),
        encoding="utf-8",
    )
    init_git(repo)
    result = mdf(python_exe, "fact-audit", "--repo", str(repo))
    assert result.returncode == 2
    assert "overview.core_modules" in _codes(result)

    overview.write_text(
        text.replace(
            "| 鉴权 | 不适用：此夹具无鉴权面 |",
            "| 鉴权 | 不适用： |",
        ),
        encoding="utf-8",
    )
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "-m", "test: 空不适用理由")
    result = mdf(python_exe, "fact-audit", "--repo", str(repo))
    assert result.returncode == 2
    hits = [
        item for item in json.loads(result.stdout)["findings"]
        if item["code"] == "overview.core_modules"
    ]
    assert hits and "鉴权" in hits[0]["message"]


def test_audit_reports_project_entry_links(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    (repo / "PROJECT.md").write_text("# 维护手册\n", encoding="utf-8")
    init_git(repo)
    result = mdf(python_exe, "fact-audit", "--repo", str(repo))
    assert result.returncode == 2
    assert "project.entry_links" in _codes(result)

    (repo / "PROJECT.md").write_text(
        "# 维护手册\n\n"
        "见 `docs/system/overview.md`、`docs/README.md` 与 "
        "`docs/system/testing/index.md`。\n",
        encoding="utf-8",
    )
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "-m", "test: 补入口指向")
    data = payload(mdf(python_exe, "fact-audit", "--repo", str(repo)))
    assert data["finding_count"] == 0


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


def test_audit_reports_prose_structure_in_fact_pages_only_managed_agents(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    page = repo / "docs/system/testing/conventions.md"
    page.write_text(page.read_text() + "\n" + "".join(f"第{i}行说明。\n" for i in range(7)))
    agents = repo / "AGENTS.md"
    agents.write_text(agents.read_text() + "\n" + "项目自有说明。\n" * 8)
    init_git(repo)
    data = json.loads(mdf(python_exe, "fact-audit", "--repo", str(repo)).stdout)
    prose = [item for item in data["findings"] if item["code"].startswith("prose.")]
    assert [(item["code"], item["path"]) for item in prose] == [
        ("prose.block", "docs/system/testing/conventions.md"),
    ]
