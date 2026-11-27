"""静态 profile、零拷贝输入与 IG strict 的外部契约。"""

from collections import Counter

from mdf_test_support import *  # noqa: F403

FACT = "docs/system/interfaces/api.md"


@pytest.mark.parametrize("args", [
    ("--profile", "entry", "--scope", "full"),
    ("--profile", "objects", "--scope", "branch"),
    ("--profile", "objects", "--scope", "paths", "--implementation-path", "src/service.py"),
    ("--profile", "closeout", "--only", "links"),
    ("--against", "HEAD", "--scope", "branch"),
    ("--against", "HEAD", "--base", "HEAD"),
    ("--against", "HEAD", "--document-path", FACT),
    ("--scope", "full", "--base", "HEAD"),
    ("--scope", "paths"),
    ("--scope", "paths", "--document-path", "docs/JOTS.md"),
    ("--scope", "paths", "--document-path", "src/service.py"),
    ("--scope", "paths", "--document-path", "../outside.md"),
    ("--only", "unknown"),
])
def test_check_rejects_invalid_options(python_exe, tmp_path, args):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = mdf(python_exe, "check", "--repo", str(repo), *args)
    assert result.returncode == 1
    assert '"invalid_arguments"' in result.stderr


@pytest.mark.parametrize("level", [(), ("--level", "basic")])
def test_ig_strict_requires_explicit_level(python_exe, tmp_path, level):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = mdf(python_exe, "validate", "--repo", str(repo), *level)
    assert result.returncode == 1
    assert '"invalid_arguments"' in result.stderr


def test_static_dev_and_entry_skip_history_and_snapshots(python_exe, tmp_path, monkeypatch):
    from mdf_core.reviewing import fact_context
    from mdf_core.inspection.check_engine import check_payload
    from mdf_core.workspace.gitutil import GitPathIndex

    repo = copy_fixture(tmp_path)
    init_git(repo)
    (repo / "src/service.py").write_text("changed = True\n")

    def forbidden(*args, **kwargs):
        pytest.fail("entry 与 dev 不读取 freshness history 或创建 snapshot")

    monkeypatch.setattr(fact_context, "snapshot", forbidden)
    monkeypatch.setattr(fact_context, "working_snapshot", forbidden)
    monkeypatch.setattr(GitPathIndex, "last_commit", forbidden)
    for profile in ("entry", "dev"):
        data, _ = check_payload(repo, profile, base="HEAD" if profile == "dev" else None)
        assert "freshness" in data["skipped_checks"]
        assert not any(f["code"] == "evidence.stale" for f in data["findings"])


def test_staged_unstaged_untracked_and_tracked_ignored(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    (repo / ".gitignore").write_text((repo / ".gitignore").read_text() + "src/ignored*.py\n")
    init_git(repo)
    (repo / "src/ignored_tracked.py").write_text("tracked = True\n")
    git(repo, "add", "-f", "src/ignored_tracked.py")
    git(repo, "commit", "-m", "test: 保留已跟踪的忽略源文件")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "src/ignored_tracked.py").write_text("tracked = False\n")
    git(repo, "add", "src/ignored_tracked.py")
    (repo / "src/ignored_tracked.py").write_text("tracked = True\n")
    (repo / "src/service.py").write_text("unstaged = True\n")
    (repo / "src/untracked.py").write_text("untracked = True\n")
    (repo / "src/ignored_untracked.py").write_text("ignored = True\n")
    name = "docs/system/interfaces/new.md"
    (repo / name).write_text("---\ndoc_type: system-interfaces\nevidence: [src/untracked.py]\n---\n\n# 新页\n")
    result = mdf(python_exe, "check", "--repo", str(repo), "--profile", "closeout", "--against", base)
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["implementation_paths"] == ["src/ignored_tracked.py", "src/service.py", "src/untracked.py"]
    assert {(f["code"], f.get("path")) for f in data["findings"]} >= {
        ("fact.untracked", name), ("evidence.untracked", name), ("audit.uncovered", "src/ignored_tracked.py"),
    }


def test_objects_paths_checks_prose_after_write(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    path = repo / "docs/proposals" / PRP_NAME
    path.write_text(path.read_text() + "\n" + "一行文字。\n" * 7)
    full = payload(mdf(python_exe, "check", "--repo", str(repo), "--profile", "objects"))
    assert "prose" in full["skipped_checks"]
    result = mdf(python_exe, "check", "--repo", str(repo), "--profile", "objects", "--scope", "paths",
                 "--document-path", path.relative_to(repo).as_posix())
    assert result.returncode == 2
    assert any(f["code"] == "prose.block" for f in json.loads(result.stdout)["findings"])


def strict_keys(result):
    data = json.loads(result.stdout)
    keys = Counter((f["code"], f.get("path"), f["message"], f["severity"]) for f in data["findings"])
    assert result.returncode == (2 if any(key[-1] == "error" for key in keys) else 0)
    assert data["ok"] is (result.returncode == 0)
    return keys


def test_ig_strict_multiset_stays_frozen(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)

    def run_strict():
        return strict_keys(mdf(python_exe, "validate", "--repo", str(repo), "--level", "strict"))

    baseline = run_strict()
    (repo / "src/uncovered.py").write_text("NEW = True\n")
    git(repo, "add", "src/uncovered.py")
    git(repo, "commit", "-m", "test: 覆盖提示")
    assert run_strict() == baseline

    page = repo / FACT
    page.write_text(page.read_text() + "\n[缺失锚点](#missing)\n\n" + "短句。\n" * 8)
    assert run_strict() == baseline
    page.write_text(page.read_text() + "\n\n")
    assert run_strict() == baseline

    (repo / ".mdf/tmp").symlink_to(tmp_path / "artifacts", target_is_directory=True)
    with_warning = run_strict()
    assert [(code, path, severity, count) for (code, path, _, severity), count in (with_warning - baseline).items()] == [
        ("path.symlink", ".mdf/tmp", "warning", 1),
    ]
    page.write_text(page.read_text() + "\n[断链](missing.md)\n")
    assert [(key[0], key[-1]) for key in run_strict() - with_warning] == [("link.broken", "error")]


def test_static_links_and_object_inventory_exclude_ignored_local_files(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    path = "docs/context/adr/local-draft.md"
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / ".gitignore").write_text((repo / ".gitignore").read_text() + f"{path}\nprivate.md\n")
    init_git(repo)
    (repo / path).write_text("未声明 frontmatter 的本地草稿。\n")
    (repo / "private.md").write_text("# 本地文件\n")
    payload(mdf(python_exe, "check", "--repo", str(repo), "--profile", "objects"))
    readme = repo / "AGENTS.md"
    readme.write_text(readme.read_text() + "\n[本地文件](private.md)\n")
    result = mdf(python_exe, "check", "--repo", str(repo), "--scope", "paths",
                 "--document-path", "AGENTS.md", "--only", "links")
    assert result.returncode == 2
    assert [f["code"] for f in json.loads(result.stdout)["findings"]] == ["link.broken"]


def test_scoped_fact_audit_revalidates_global_object_invariants(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    original = repo / "docs/proposals" / PRP_NAME
    duplicate = original.with_name(original.stem + "-duplicate.md")
    duplicate.write_text(original.read_text())
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    fact = repo / FACT
    fact.write_text(fact.read_text() + "\n<!-- 事实写入 -->\n")
    cmd = ("fact-audit", "--repo", str(repo), "--against", base)
    semantic = payload(mdf(python_exe, *cmd))["result"]["audit"]
    quick = payload(mdf(python_exe, *cmd, "--quick"))["result"]["audit"]
    assert "object.id_duplicate" in {item["code"] for item in semantic["findings"]}
    assert "object.id_duplicate" not in {item["code"] for item in quick["findings"]}


def test_static_and_snapshot_report_untracked_evidence(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    name = "docs/system/interfaces/new.md"
    (repo / "src/new.py").write_text("NEW = True\n")
    (repo / name).write_text("---\ndoc_type: system-interfaces\nevidence: [src/new.py]\n---\n\n# 新页\n")
    checked = mdf(python_exe, "check", "--repo", str(repo), "--profile", "closeout", "--against", "HEAD")
    audited = mdf(python_exe, "fact-audit", "--repo", str(repo), "--against", "HEAD")
    assert checked.returncode == 2
    expected = {"fact.untracked", "evidence.untracked"}
    keys = lambda rows: {f["code"] for f in rows if f.get("path") == name}
    assert keys(json.loads(checked.stdout)["findings"]) == expected
    assert keys(payload(audited)["result"]["audit"]["findings"]) == expected


def test_reference_page_size_in_target_repo(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    page = repo / FACT
    original = page.read_text()
    newline = original.index("\n")
    reference = original[:newline + 1] + "doc_style: reference\n" + original[newline + 1:]
    sections = "".join(f"\n## 参数 {i}\n\n" + "| 参数 | 值 |\n" * 90 for i in range(6))
    page.write_text(reference + sections)
    cli = ("check", "--repo", str(repo), "--scope", "paths", "--document-path", FACT, "--only", "size")
    payload(mdf(python_exe, *cli))
    page.write_text(reference + sections + sections + sections)
    result = mdf(python_exe, *cli)
    assert result.returncode == 2
    assert [item["code"] for item in json.loads(result.stdout)["findings"]] == ["size.hard"]


def test_objects_ignores_local_release_records(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    local_release = "changes/99.0.0"
    (repo / ".gitignore").write_text((repo / ".gitignore").read_text() + f"{local_release}/\n")
    init_git(repo)
    (repo / local_release).mkdir(parents=True)
    (repo / local_release / "CHANGE.md").write_text("本地草稿\n")
    payload(mdf(python_exe, "check", "--repo", str(repo), "--profile", "objects"))


def test_fact_audit_full_uses_same_visible_facts_as_closeout(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    draft = "docs/system/interfaces/private.md"
    (repo / ".gitignore").write_text((repo / ".gitignore").read_text() + f"{draft}\n")
    init_git(repo)
    (repo / draft).write_text("本地草稿\n")
    for command in (("check", "--profile", "closeout"), ("fact-audit",)):
        result = payload(mdf(python_exe, *command, "--repo", str(repo), "--scope", "full"))
        assert draft not in result["document_paths"]


def test_ignored_leaf_cannot_satisfy_testing_layout(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    path = "docs/system/testing/conventions.md"
    (repo / ".gitignore").write_text((repo / ".gitignore").read_text() + f"{path}\n")
    init_git(repo)
    result = payload(mdf(python_exe, "check", "--profile", "entry", "--repo", str(repo)))
    assert result["normal_workflows_allowed"] is False
    assert any(item["code"] == "layout.testing" for item in result["findings"])


def test_closeout_and_fact_audit_exclude_unrelated_historical_stale(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    local = repo / "src/unrelated.py"
    local.write_text("OLD = True\n")
    other_fact = "docs/system/interfaces/unrelated.md"
    (repo / other_fact).write_text("---\ndoc_type: system-interfaces\nevidence: [src/unrelated.py]\n---\n\n# 旧事实\n")
    init_git(repo)
    local.write_text("OLD = False\n")
    git(repo, "add", "src/unrelated.py")
    git(repo, "commit", "-m", "test: 保留历史 stale")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / FACT).write_text((repo / FACT).read_text() + "\n<!-- 当前范围 -->\n")
    for args in (("check", "--profile", "closeout"), ("fact-audit",)):
        result = payload(mdf(python_exe, *args, "--repo", str(repo), "--against", base))
        data = result.get("result", {}).get("audit", result)
        assert other_fact not in data["document_paths"]
        assert data["findings"] == []
    full = mdf(python_exe, "check", "--repo", str(repo), "--profile", "closeout", "--scope", "full")
    assert full.returncode == 2
    assert ("evidence.stale", other_fact) in {(f["code"], f.get("path")) for f in json.loads(full.stdout)["findings"]}
