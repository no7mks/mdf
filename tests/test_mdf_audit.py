"""Mars Development Flow 的确定性协议与事务测试。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403


def test_full_audit_works_without_site_packages(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    cli = skill_dir("mdf") / "scripts" / "mdf.py"
    result = run(
        [
            python_exe,
            "-S",
            str(cli),
            "validate",
            "--repo",
            str(repo),
            "--scope",
            "full",
        ]
    )
    assert_ok(result)
    assert json.loads(result.stdout)["finding_count"] == 0


def test_audit_reports_evidence_mapping_without_running_commands(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / ".mdf" / "manifest.yaml", '- "true"', '- "touch audit-ran"'
    )
    init_git(repo)

    result = mdf(python_exe, "audit", "--repo", str(repo))
    data = payload(result)

    assert data["finding_count"] == 0
    assert data["warning_count"] == 0
    assert data["implementation_paths"] == ["src/service.py"]
    assert any(
        item["evidence"] == ["src/service.py"] for item in data["mappings"]
    )
    assert not (repo / "audit-ran").exists()


def test_audit_uncovered_file_is_warning_and_ignorelist_can_cover_it(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    generated = repo / "src" / "generated"
    generated.mkdir()
    (generated / "client.py").write_text("VALUE = 1\n", encoding="utf-8")
    init_git(repo)

    data = payload(mdf(python_exe, "audit", "--repo", str(repo)))
    assert data["finding_count"] == 0
    assert [item["path"] for item in data["warnings"]] == [
        "src/generated/client.py"
    ]

    (repo / ".mdf" / "audit-ignore.yaml").write_text(
        "ignored:\n  - path: src/generated\n    reason: generated client\n",
        encoding="utf-8",
    )
    git(repo, "add", ".mdf/audit-ignore.yaml")
    git(repo, "commit", "-m", "test: 忽略生成客户端")
    data = payload(mdf(python_exe, "audit", "--repo", str(repo)))
    assert data["warning_count"] == 0
    assert data["ignored"] == [
        {
            "path": "src/generated/client.py",
            "ignore_path": "src/generated",
            "reason": "generated client",
        }
    ]


def test_audit_rejects_invalid_ignore_and_scope_paths(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    (repo / ".mdf" / "audit-ignore.yaml").write_text(
        "ignored:\n  - path: src/nope.py\n    reason: stale rule\n",
        encoding="utf-8",
    )
    init_git(repo)

    result = mdf(python_exe, "audit", "--repo", str(repo))
    assert result.returncode == 2
    assert "audit.ignore_rule" in result.stdout

    result = mdf(
        python_exe,
        "audit",
        "--repo",
        str(repo),
        "--scope",
        "paths",
        "--implementation-path",
        "docs/system/overview.md",
    )
    assert result.returncode == 2
    assert "audit.scope_path" in result.stdout


def test_audit_rejects_missing_or_overlapping_implementation_roots(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / ".mdf" / "manifest.yaml", "implementation_roots: [src]\n", ""
    )
    init_git(repo)

    result = mdf(python_exe, "audit", "--repo", str(repo))
    assert result.returncode == 2
    assert "manifest.implementation_roots" in result.stdout


def test_audit_rejects_overlapping_implementation_roots(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    (repo / "src" / "nested").mkdir()
    replace(
        repo / ".mdf" / "manifest.yaml",
        "implementation_roots: [src]\n",
        "implementation_roots: [src, src/nested]\n",
    )
    init_git(repo)

    result = mdf(python_exe, "audit", "--repo", str(repo))
    assert result.returncode == 2
    assert "manifest.implementation_root_overlap" in result.stdout


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            "ignored:\n  - path: src/service.py\n    reason: one\n"
            "  - path: src/service.py\n    reason: two\n",
            "audit.ignore_duplicate",
        ),
        (
            "ignored:\n  - path: src/empty\n    reason: intentionally empty\n",
            "audit.ignore_empty",
        ),
    ],
)
def test_audit_rejects_duplicate_or_empty_ignore_rules(
    python_exe: str, tmp_path: Path, content: str, expected: str
):
    repo = copy_fixture(tmp_path)
    (repo / "src" / "empty").mkdir()
    (repo / ".mdf" / "audit-ignore.yaml").write_text(
        content, encoding="utf-8"
    )
    init_git(repo)

    result = mdf(python_exe, "audit", "--repo", str(repo))
    assert result.returncode == 2
    assert expected in result.stdout


def test_audit_accepts_exact_range_paths(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)

    data = payload(
        mdf(
            python_exe,
            "audit",
            "--repo",
            str(repo),
            "--scope",
            "paths",
            "--implementation-path",
            "src/service.py",
            "--document-path",
            "docs/system/interfaces/api.md",
        )
    )
    assert data["implementation_paths"] == ["src/service.py"]
    assert data["document_paths"] == ["docs/system/interfaces/api.md"]


@pytest.mark.parametrize(
    "bad_value", ["0.0.0-unreleased", "0.0.0-dev", "1.2.3-rc.1"]
)
def test_bug_found_in_accepts_only_bare_unreleased_or_stable(
    python_exe: str, tmp_path: Path, bad_value: str
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / f"bugs/{BUG_NAME}",
        "found_in: unreleased",
        f"found_in: {bad_value}",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "bug.found_in" in result.stdout


def test_unreleased_sentinel_is_rejected_in_proposal_found_in(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / "proposals" / PRP_NAME,
        "status: ready\nrelated: []",
        "status: ready\nrelated: []\nfound_in: unreleased",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "version.sentinel_scope" in result.stdout


def test_audit_flags_evidence_changed_after_fact_doc(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    assert_ok(
        mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    )

    service = repo / "src" / "service.py"
    service.write_text(
        service.read_text(encoding="utf-8") + "\n# changed after docs\n",
        encoding="utf-8",
    )
    git(repo, "add", "src/service.py")
    git(repo, "commit", "-m", "test: 修改事实证据")

    result = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert result.returncode != 0
    assert "src/service.py" in result.stdout


def test_audit_rejects_ignored_untracked_evidence(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    reference = repo / "docs" / "product" / "reference" / "capabilities.md"
    replace(reference, "path: src/service.py", "path: ignored-evidence.txt")
    (repo / ".gitignore").write_text("ignored-evidence.txt\n", encoding="utf-8")
    (repo / "ignored-evidence.txt").write_text(
        "future evidence that is deliberately not versioned\n",
        encoding="utf-8",
    )
    init_git(repo)
    assert not git(repo, "ls-files", "ignored-evidence.txt").stdout

    result = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert result.returncode != 0
    assert "ignored-evidence.txt" in result.stdout


def test_audit_does_not_let_dirty_fact_docs_hide_stale_evidence(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    service = repo / "src" / "service.py"
    service.write_text(
        service.read_text(encoding="utf-8") + "\n# newer evidence\n",
        encoding="utf-8",
    )
    git(repo, "add", "src/service.py")
    git(repo, "commit", "-m", "test: 提交晚于事实页的证据")

    fact_docs = [
        *sorted((repo / "docs" / "product").rglob("*.md")),
        *sorted((repo / "docs" / "system").rglob("*.md")),
    ]
    assert fact_docs
    for fact_doc in fact_docs:
        fact_doc.write_text(
            fact_doc.read_text(encoding="utf-8") + "\n<!-- dirty -->\n",
            encoding="utf-8",
        )

    result = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert result.returncode != 0
    assert "evidence" in result.stdout


def test_generated_fact_requires_evidence_and_repository_relative_paths(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    outside_source = tmp_path / "outside-source.yaml"
    outside_generator = tmp_path / "outside-generator.py"
    outside_source.write_text("value: outside\n", encoding="utf-8")
    outside_generator.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    outside_generator.chmod(0o755)
    fact = repo / "docs" / "system" / "interfaces" / "api.md"
    replace(
        fact,
        (
            "evidence:\n"
            "  - path: src/service.py\n"
            '    verification: "读取函数签名并运行 python -m pytest"'
        ),
        (
            "generated:\n"
            f"  source: {outside_source}\n"
            f"  generator: {outside_generator}"
        ),
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert result.returncode != 0
    assert "evidence.missing" in result.stdout
    assert "generated.outside_repo" in result.stdout


def test_audit_does_not_rerun_generated_document_generator(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    generator = repo / "scripts" / "generate-interface.py"
    generator.parent.mkdir()
    generator.write_text(
        (
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            'path = Path("docs/system/interfaces/api.md")\n'
            'text = path.read_text(encoding="utf-8")\n'
            "path.write_text(\n"
            '    text.replace("`healthy()` 返回布尔值。", '
            '"`healthy()` 返回字符串。"),\n'
            '    encoding="utf-8",\n'
            ")\n"
        ),
        encoding="utf-8",
    )
    generator.chmod(0o755)
    fact = repo / "docs" / "system" / "interfaces" / "api.md"
    replace(
        fact,
        '    verification: "读取函数签名并运行 python -m pytest"\n',
        (
            '    verification: "读取函数签名并运行 python -m pytest"\n'
            "generated:\n"
            "  source: src/service.py\n"
            "  generator: scripts/generate-interface.py\n"
        ),
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert_ok(result)
    assert "generated.drift" not in result.stdout
