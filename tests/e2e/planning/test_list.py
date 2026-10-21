"""只读 list 命令：过滤、依赖与开工标注、宽松跳过。"""
from mdf_test_support import *  # noqa: F403
from support_planning import *  # noqa: F403


def add_bug(repo, identifier, status="open", severity="major"):
    template = (repo / "docs/bugs" / BUG_NAME).read_text()
    text = template.replace(BUG_ID, identifier).replace("status: open", f"status: {status}")
    text = text.replace("severity: major", f"severity: {severity}")
    slug = f"fix-{identifier.split('-', 1)[1].lower()}"
    path = repo / "docs/bugs" / f"{identifier}-{slug}.md"
    path.write_text(text)
    return path


def ids(data):
    return [item["id"] for item in data["objects"]]


def test_list_filters_by_type_status_milestone_and_severity(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-0003", ["prp-0001"], status="draft", milestone="阶段一")
    add_prp(repo, "prp-0004", status="rejected")
    replace(repo / "docs/proposals/prp-0004-item-0004.html", "status: rejected",
            "status: rejected\nreject-reason: wont-do")
    add_bug(repo, "bug-EF56", status="fixed", severity="trivial")
    init_git(repo)
    base = ["list", "--repo", str(repo)]
    everything = payload(mdf(python_exe, *base))
    assert ids(everything) == ["bug-CD34", "bug-EF56", "prp-0001", "prp-0003", "prp-0004"]
    assert everything["count"] == 5 and everything["skipped"] == []
    assert ids(payload(mdf(python_exe, *base, "--type", "bug", "--status", "open"))) == ["bug-CD34"]
    assert ids(payload(mdf(python_exe, *base, "--status", "draft", "--status", "fixed"))) == [
        "bug-EF56", "prp-0003"]
    assert ids(payload(mdf(python_exe, *base, "--milestone", "阶段一"))) == ["prp-0003"]
    assert ids(payload(mdf(python_exe, *base, "--severity", "trivial"))) == ["bug-EF56"]
    draft = payload(mdf(python_exe, *base, "--status", "draft"))["objects"][0]
    assert draft["title"] == "Service health" and draft["blocked_by"] == ["prp-0001"]
    assert draft["in_progress"] is False and draft["milestone"] == "阶段一"
    bug = payload(mdf(python_exe, *base, "--type", "bug", "--status", "fixed"))["objects"][0]
    assert bug["severity"] == "trivial" and bug["found_in"] == "unreleased"


@pytest.mark.parametrize("args, message", [
    (["--type", "proposal", "--severity", "major"], "--severity 只适用于 bug"),
    (["--type", "bug", "--milestone", "m"], "--milestone 只适用于 proposal"),
    (["--milestone", "m", "--severity", "major"], "不能同时使用"),
    (["--severity", "blocker"], "severity 必须是"),
    (["--type", "bug", "--status", "ready"], "未知状态: ready"),
    (["--status", "done"], "未知状态: done"),
])
def test_list_rejects_conflicting_filters(python_exe, tmp_path, args, message):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = mdf(python_exe, "list", "--repo", str(repo), *args)
    assert result.returncode == 1
    assert "invalid_filter" in result.stderr and message in result.stderr


def test_list_marks_started_and_excludes_archive_but_resolves_archived_dependencies(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    archive = repo / "docs/proposals/archive/1.2"
    archive.mkdir(parents=True)
    released = add_prp(repo, "prp-0005", status="released")
    replace(released, "status: released", "status: released\nreleased_in: 1.2.0")
    released.rename(archive / released.name)
    add_prp(repo, "prp-0003", ["prp-0005"], status="ready")
    init_git(repo)
    git(repo, "checkout", "-b", "feature/started")
    folder = repo / "changes/unreleased/started"
    folder.mkdir(parents=True)
    (folder / "delivery.json").write_text(json.dumps({"proposal": "prp-0001"}))
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 记录开工")
    git(repo, "checkout", "main")
    data = payload(mdf(python_exe, "list", "--repo", str(repo), "--type", "proposal"))
    by_id = {item["id"]: item for item in data["objects"]}
    assert sorted(by_id) == ["prp-0001", "prp-0003"]
    assert by_id["prp-0001"]["in_progress"] is True
    assert by_id["prp-0003"]["in_progress"] is False and by_id["prp-0003"]["blocked_by"] == []


def test_list_skips_broken_files_and_does_not_require_ready(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    (repo / "docs/bugs/notes.md").write_text("# 不是对象\n")
    (repo / "docs/bugs/bug-EF56-broken.md").write_text("no frontmatter\n")
    (repo / "docs/proposals/prp-0003-noid.md").write_text("---\ntype: proposal\n---\n# x\n")
    replace(repo / ".mdf/manifest.yaml", "state: ready", "state: initializing")
    init_git(repo)
    data = payload(mdf(python_exe, "list", "--repo", str(repo)))
    assert ids(data) == ["bug-CD34", "prp-0001"]
    assert [item["path"] for item in data["skipped"]] == [
        "docs/bugs/bug-EF56-broken.md", "docs/bugs/notes.md", "docs/proposals/prp-0003-noid.md"]
    assert all(item["reason"] for item in data["skipped"])
    assert mdf(python_exe, "tree", "--repo", str(repo)).returncode == 1
