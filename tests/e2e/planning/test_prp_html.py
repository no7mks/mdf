"""确认后的 PRP 唯一 HTML、引用改写、重新评审与正文保真。"""
from mdf_test_support import *  # noqa: F403


def draft_repo(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "master")
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    payload(mdf(python_exe, "prp-format", "draft", "--repo", str(work), "--proposal", PRP_ID))
    return work, work / "docs/proposals" / Path(PRP_NAME).with_suffix(".md")


def format_prp(python_exe, work, action, *extra):
    return mdf(python_exe, "prp-format", action, "--repo", str(work), "--proposal", PRP_ID, *extra)


def test_confirmed_html_is_unique_and_rewrites_links_and_can_return_to_draft(python_exe, tmp_path):
    work, draft = draft_repo(python_exe, tmp_path)
    draft.write_text(draft.read_text() + (
        "\n## 约束与取舍\n\n1. 保留 <边界> & 错误语义。\n"
        "   - 采用稳定接口。\n2. 核对实际结果。\n\n"
        "| 方案 | 理由 |\n| --- | --- |\n| 本地 | 离线运行 |\n\n"
        "```python\nprint('<script>')\n```\n\n"
        "[当前稿](prp-0001-service-health.md#约束与取舍)\n"
    ))
    link = work / "docs/README.md"
    link.write_text(link.read_text() + "\n[计划](proposals/prp-0001-service-health.md)\n")
    preview = payload(format_prp(python_exe, work, "preview"))
    preview_path = work / preview["path"]
    html = preview_path.read_text()
    assert "<table>" in html and "&lt;边界&gt; &amp;" in html
    assert "&lt;script&gt;" in html and "data-indent=\"3\"" in html
    assert 'data-marker="2." value="2"' in html
    assert re.search(r'<ol>.*?<li[^>]*>.*?<ul>.*?</ul>.*?</li>.*?value="2"', html, re.DOTALL)
    assert "confirmation_required" in format_prp(python_exe, work, "ready").stderr
    assert draft.is_file()
    payload(format_prp(python_exe, work, "ready", "--confirmed"))
    target = draft.with_suffix(".html")
    assert target.is_file() and not draft.exists() and not preview_path.exists()
    assert "proposals/prp-0001-service-health.html" in link.read_text()
    assert 'href="prp-0001-service-health.html#约束与取舍"' in target.read_text()
    data = payload(mdf(python_exe, "list", "--repo", str(work), "--type", "proposal"))
    assert data["objects"][0]["status"] == "ready"
    assert data["objects"][0]["path"].endswith(".html")
    assert_ok(mdf(python_exe, "validate", "--repo", str(work)))
    payload(format_prp(python_exe, work, "draft"))
    assert draft.is_file() and not target.exists()
    body = draft.read_text()
    assert "## 约束与取舍" in body and "1. 保留 <边界> & 错误语义。" in body
    assert "   - 采用稳定接口。" in body and "| 本地 | 离线运行 |" in body
    assert "print('<script>')" in body
    assert "proposals/prp-0001-service-health.md" in link.read_text()


def test_changed_draft_requires_new_html_confirmation(python_exe, tmp_path):
    work, draft = draft_repo(python_exe, tmp_path)
    payload(format_prp(python_exe, work, "preview"))
    draft.write_text(draft.read_text() + "\n## 新约束\n\n必须离线运行。\n")
    result = format_prp(python_exe, work, "ready", "--confirmed")
    assert "preview_changed" in result.stderr
    assert draft.is_file() and not draft.with_suffix(".html").exists()
    assert "draft" in draft.read_text()


def test_duplicate_markdown_and_html_are_rejected(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    path = repo / "docs/proposals" / PRP_NAME
    path.with_suffix(".md").write_text(proposal_markdown(path))
    init_git(repo)
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "object.id_duplicate" in result.stdout


def markdown_repo(tmp_path, status="ready", archived=False):
    repo = copy_fixture(tmp_path)
    source = repo / "docs/proposals" / PRP_NAME
    target = source.with_suffix(".md")
    text = proposal_markdown(source).replace("status: ready", f"status: {status}")
    if status == "released":
        text = text.replace("status: released", "status: released\nreleased_in: 1.2.0")
    if archived:
        target = target.parent / "archive/1.2" / target.name
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    source.unlink()
    replace(repo / "docs/user-guide/README.md", PRP_NAME,
            target.relative_to(repo / "docs/proposals").as_posix())
    init_git(repo)
    return repo, target


@pytest.mark.parametrize("status,archived", [
    ("ready", False), ("implemented", False), ("released", False), ("released", True),
])
def test_existing_markdown_proposals_validate_without_conversion(python_exe, tmp_path, status, archived):
    repo, path = markdown_repo(tmp_path, status, archived)
    before = {item: item.read_bytes() for item in (repo / "docs").rglob("*") if item.is_file()}
    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["findings"] == []
    assert data["normal_workflows_allowed"] is True
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))
    assert path.is_file() and not path.with_suffix(".html").exists()
    assert before == {item: item.read_bytes() for item in (repo / "docs").rglob("*") if item.is_file()}


def test_existing_markdown_still_requires_valid_content(python_exe, tmp_path):
    repo, path = markdown_repo(tmp_path)
    replace(path, "## 验收标准", "## 其他内容")
    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert "object.section" in {item["code"] for item in data["findings"]}
    assert data["normal_workflows_allowed"] is False


def test_existing_ready_markdown_can_be_reviewed_into_html(python_exe, tmp_path):
    repo, _ = markdown_repo(tmp_path)
    git(repo, "branch", "master")
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    draft = work / "docs/proposals" / Path(PRP_NAME).with_suffix(".md")
    payload(format_prp(python_exe, work, "draft"))
    data = payload(mdf(python_exe, "list", "--repo", str(work), "--type", "proposal"))
    assert data["objects"][0]["status"] == "draft"
    payload(format_prp(python_exe, work, "preview"))
    payload(format_prp(python_exe, work, "ready", "--confirmed"))
    assert not draft.exists() and draft.with_suffix(".html").is_file()
    assert_ok(mdf(python_exe, "validate", "--repo", str(work)))
