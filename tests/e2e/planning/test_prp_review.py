"""评审 Markdown PRP，原位转状态并绑定已确认版本。"""
from mdf_test_support import *  # noqa: F403


def review(python_exe, work, action, *extra):
    return mdf(python_exe, "prp-review", action, "--repo", str(work), "--proposal", PRP_ID, *extra)


def planning_repo(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "master")
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    return work, work / "docs/proposals" / PRP_NAME


def test_review_updates_status_in_place_and_preserves_markdown(python_exe, tmp_path):
    work, path = planning_repo(python_exe, tmp_path)
    replace(path, "depends_on: []", 'depends_on: [] # 保留注释\nmilestone: "第一\\u2028阶段"')
    before = path.read_bytes()
    payload(review(python_exe, work, "draft"))
    assert path.read_bytes() == before.replace(b"status: ready", b"status: draft", 1)
    markdown = (
        "\n## 约束与取舍\n\n1. 保留 <边界> & 错误语义。\n"
        "   - 采用稳定接口。\n2. 核对实际结果。\n\n"
        "| 方案 | 理由 |\n| --- | --- |\n| 本地 | 离线运行 |\n\n"
        "```python\nprint('<script>')\n```\n\n"
        f"[当前稿]({PRP_NAME}#约束与取舍)\n"
    )
    original = (path.read_text() + markdown).replace("\n", "\r\n").encode()
    path.write_bytes(original)
    index = work / "docs/user-guide/README.md"
    links = index.read_bytes()
    checked = payload(review(python_exe, work, "check"))
    assert path == work / checked["path"]
    assert path.read_bytes() == original
    assert "confirmation_required" in review(python_exe, work, "ready").stderr

    confirmed = payload(review(python_exe, work, "ready", "--confirmed-sha256", checked["sha256"]))
    assert confirmed["path"] == checked["path"]
    assert path.read_bytes() == original.replace(b"status: draft", b"status: ready", 1)
    assert index.read_bytes() == links
    assert list(path.parent.iterdir()) == [path]
    assert_ok(mdf(python_exe, "validate", "--repo", str(work), "--level", "strict"))
    payload(review(python_exe, work, "draft"))
    assert path.read_bytes() == original


def test_changed_draft_requires_new_markdown_confirmation(python_exe, tmp_path):
    work, path = planning_repo(python_exe, tmp_path)
    payload(review(python_exe, work, "draft"))
    checked = payload(review(python_exe, work, "check"))
    updated = path.read_text() + "\n## 新约束\n\n必须离线运行。\n"
    path.write_text(updated)
    result = review(python_exe, work, "ready", "--confirmed-sha256", checked["sha256"])
    assert "review_changed" in result.stderr
    assert path.read_text() == updated


def test_html_proposal_is_invalid(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    path = repo / "docs/proposals" / PRP_NAME
    path.rename(path.with_suffix(".html"))
    init_git(repo)
    data = payload(mdf(python_exe, "check", "--profile", "entry", "--repo", str(repo)))
    assert data["normal_workflows_allowed"]
    checked = mdf(python_exe, "check", "--profile", "objects", "--repo", str(repo))
    assert checked.returncode == 2
    data = json.loads(checked.stdout)
    assert "object.filename" in {item["code"] for item in data["findings"]}


@pytest.mark.parametrize("status,archived", [
    ("ready", False), ("implemented", False), ("released", False), ("released", True),
])
def test_markdown_proposals_validate_without_changes(python_exe, tmp_path, status, archived):
    repo = copy_fixture(tmp_path)
    path = repo / "docs/proposals" / PRP_NAME
    text = path.read_text().replace("status: ready", f"status: {status}")
    if status == "released":
        text = text.replace("status: released", "status: released\nreleased_in: 1.2.0")
    path.write_text(text)
    if archived:
        target = path.parent / "archive/1.2" / path.name
        target.parent.mkdir(parents=True)
        path.rename(target)
        replace(repo / "docs/user-guide/README.md", PRP_NAME, f"archive/1.2/{PRP_NAME}")
    init_git(repo)
    data = payload(mdf(python_exe, "check", "--profile", "entry", "--repo", str(repo)))
    assert data["findings"] == []
    assert data["normal_workflows_allowed"] is True
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--level", "strict"))
    assert git(repo, "status", "--porcelain").stdout == ""
