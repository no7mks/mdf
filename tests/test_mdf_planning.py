"""具名验证配置、PRP 拆分事务与依赖视图。"""
from types import SimpleNamespace

from mdf_test_support import *  # noqa: F403


def add_prp(repo, identifier, deps=(), status="ready", milestone=None, slug=None):
    template = (repo / "docs/proposals" / PRP_NAME).read_text()
    depends_on = json.dumps(list(deps), ensure_ascii=False)
    text = template.replace("prp-001", identifier).replace(
        "depends_on: []", f"depends_on: {depends_on}"
    )
    text = text.replace("status: ready", f"status: {status}")
    if milestone is not None:
        text = text.replace(
            f"depends_on: {depends_on}",
            f"depends_on: {depends_on}\n"
            f"milestone: {json.dumps(milestone, ensure_ascii=False)}",
        )
    if slug is None:
        slug = f"item-{identifier.split('-', 1)[1].lower()}"
    path = repo / "docs/proposals" / f"{identifier}-{slug}.md"
    path.write_text(text)
    return path


def index_item(identifier, deps=(), blocked=(), status="ready"):
    return {
        "id": identifier, "title": "Service health", "status": status,
        "depends_on": list(deps), "blocked_by": list(blocked),
        "in_progress": False,
    }


def test_tree_mixed_dag_drafts_truncation_and_invalid_dependencies(
    python_exe, tmp_path
):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-003", ["prp-001"])
    add_prp(repo, "prp-004", ["prp-001"])
    add_prp(repo, "prp-005", ["prp-003", "prp-004"])
    add_prp(repo, "prp-006", status="draft")
    add_prp(repo, "prp-007", ["prp-006"])
    init_git(repo)
    data = payload(mdf(python_exe, "tree", "--repo", str(repo)))
    assert data["operation"] == "tree"
    assert data["index"] == {
        "groups": [],
        "ungrouped": [
            index_item("prp-001"),
            index_item("prp-003", ["prp-001"], ["prp-001"]),
            index_item("prp-004", ["prp-001"], ["prp-001"]),
            index_item("prp-005", ["prp-003", "prp-004"], ["prp-003", "prp-004"]),
            index_item("prp-006", status="draft"),
            index_item("prp-007", ["prp-006"], ["prp-006"]),
        ],
    }
    roots = {node["id"]: node for node in data["trees"]}
    assert set(roots) == {"prp-001", "prp-006"}
    assert roots["prp-006"]["status"] == "draft"
    assert [child["id"] for child in roots["prp-006"]["children"]] == ["prp-007"]
    children = roots["prp-001"]["children"]
    assert children[1]["children"][0]["reference"] is True
    assert children[0]["children"][0]["blocked_by"] == ["prp-003", "prp-004"]
    shallow = payload(mdf(python_exe, "tree", "--repo", str(repo), "--depth", "1"))
    assert shallow["hidden"] == ["prp-003", "prp-004", "prp-005", "prp-007"]
    assert mdf(python_exe, "tree", "--repo", str(repo), "--depth", "0").returncode != 0
    add_prp(repo, "prp-008", ["prp-099"])
    assert "invalid_proposals" in mdf(python_exe, "tree", "--repo", str(repo)).stderr


def test_tree_index_includes_ready_and_groups_by_milestone(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-002", status="draft", milestone="阶段一")
    add_prp(repo, "prp-003", ["prp-002"], status="draft", milestone="阶段一")
    add_prp(repo, "prp-004", ["prp-001"], status="draft", milestone="阶段二")
    add_prp(repo, "prp-005", ["prp-001"], status="draft")
    init_git(repo)
    data = payload(mdf(python_exe, "tree", "--repo", str(repo)))
    assert data["index"] == {
        "groups": [
            {
                "milestone": "阶段一",
                "items": [
                    index_item("prp-002", status="draft"),
                    index_item("prp-003", ["prp-002"], ["prp-002"], "draft"),
                ],
            },
            {
                "milestone": "阶段二",
                "items": [
                    index_item("prp-004", ["prp-001"], ["prp-001"], "draft"),
                ],
            },
        ],
        "ungrouped": [
            index_item("prp-001"),
            index_item("prp-005", ["prp-001"], ["prp-001"], "draft"),
        ],
    }


def split_spec(repo):
    body = (repo / "docs/proposals" / PRP_NAME).read_text().split("---", 2)[2]
    return {"source": "prp-001", "rationale": "用户确认两项共同覆盖验收，下游仅依赖第一项",
            "children": [
                {
                    "id": key,
                    "filename": f"{key}-part-{key.split('-', 1)[1].lower()}.md",
                    "depends_on": [],
                    "body": body,
                }
                for key in ("prp-003", "prp-004")
            ],
            "downstream": {"prp-005": ["prp-003"]}}


@pytest.mark.parametrize("milestone", [None, "首次购买"])
def test_split_preview_then_transaction_and_downstream(python_exe, tmp_path, milestone):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-005", ["prp-001"])
    if milestone is not None:
        replace(repo / "docs/proposals" / PRP_NAME, "depends_on: []",
                f'depends_on: []\nmilestone: "{milestone}"')
    init_git(repo)
    checkout_develop(repo)
    spec = tmp_path / "split.json"
    spec.write_text(json.dumps(split_spec(repo)))
    work = planning_worktree(python_exe, repo)
    args = ["prp-split", "--repo", str(work), "--spec-file", str(spec)]
    before = git(work, "status", "--porcelain").stdout
    result = payload(mdf(python_exe, *args, "--dry-run"))
    assert len(result["files"]) == 4
    assert git(work, "status", "--porcelain").stdout == before
    payload(mdf(python_exe, *args))
    assert 'status: "replaced"' in (work / "docs/proposals" / PRP_NAME).read_text()
    assert 'depends_on: ["prp-003"]' in (
        work / "docs/proposals/prp-005-item-005.md"
    ).read_text()
    assert 'status: "draft"' in (
        work / "docs/proposals/prp-003-part-003.md"
    ).read_text()
    for name in (PRP_NAME, "prp-003-part-003.md", "prp-004-part-004.md"):
        content = (work / "docs/proposals" / name).read_text()
        if milestone is None:
            assert "milestone:" not in content
        else:
            assert f'milestone: "{milestone}"' in content
    assert_ok(mdf(python_exe, "validate", "--repo", str(work)))


@pytest.mark.parametrize("value", ['"first-purchase"', '"首次购买"', '"prp-001"',
                                   "null", '""', '"   "', "[]", "{}", "true", "42"])
def test_proposal_optional_milestone_validation(python_exe, tmp_path, value):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    args = ["validate", "--repo", str(repo)]
    assert_ok(mdf(python_exe, *args))
    replace(repo / "docs/proposals" / PRP_NAME, "depends_on: []",
            f"depends_on: []\nmilestone: {value}")
    result = mdf(python_exe, *args)
    if value in ('"first-purchase"', '"首次购买"'):
        assert_ok(result)
    else:
        assert result.returncode != 0
        assert "proposal.milestone" in result.stdout


def test_invalid_split_has_no_partial_writes(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-005", ["prp-001"])
    init_git(repo)
    checkout_develop(repo)
    spec = split_spec(repo)
    spec["children"][0]["depends_on"] = ["prp-005"]
    path = tmp_path / "split.json"
    path.write_text(json.dumps(spec))
    work = planning_worktree(python_exe, repo)
    result = mdf(python_exe, "prp-split", "--repo", str(work), "--spec-file", str(path))
    assert "invalid_proposals" in result.stderr
    assert not git(work, "status", "--porcelain").stdout


def test_split_requires_planning(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-005", ["prp-001"])
    init_git(repo)
    spec = tmp_path / "split.json"
    spec.write_text(json.dumps(split_spec(repo)))
    result = mdf(python_exe, "prp-split", "--repo", str(repo), "--spec-file", str(spec))
    assert "proposal_not_on_planning" in result.stderr
    checkout_develop(repo)
    result = mdf(python_exe, "prp-split", "--repo", str(repo), "--spec-file", str(spec))
    assert "proposal_not_on_planning" in result.stderr
    assert not git(repo, "status", "--porcelain").stdout


def test_verification_items_validate_identity_and_kind(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    manifest = repo / ".mdf/manifest.yaml"
    original = manifest.read_text()
    for value in ('      kind: unknown', '      kind: ""'):
        manifest.write_text(original.replace("      kind: custom", value))
        result = mdf(python_exe, "validate", "--repo", str(repo))
        assert "manifest.verification" in result.stdout


def test_verification_collections_are_all_or_nothing(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    manifest = repo / ".mdf/manifest.yaml"
    original = manifest.read_text()
    item = '    - id: check\n      kind: custom\n      command: "true"'
    mixed = item + "\n      collections: [quick, full]\n    - id: other\n      kind: custom\n      command: \"true\""
    manifest.write_text(original.replace(item, mixed))
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "manifest.verification" in result.stdout
    quick_only = item + "\n      collections: [quick]"
    manifest.write_text(original.replace(item, quick_only))
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "manifest.verification" in result.stdout
    layered = (
        item + "\n      collections: [quick, full]\n"
        "    - id: slow\n      kind: e2e\n      command: \"true\"\n"
        "      collections: [full]"
    )
    manifest.write_text(original.replace(item, layered))
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


def test_implemented_dependencies_unlock_next_and_replaced_relations_validate(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    replace(repo / "docs/proposals" / PRP_NAME, "status: ready", "status: implemented")
    add_prp(repo, "prp-003", ["prp-001"])
    # add_prp copies its source; explicitly keep the dependent ready.
    replace(repo / "docs/proposals/prp-003-item-003.md", "status: implemented", "status: ready")
    init_git(repo)
    data = payload(mdf(python_exe, "tree", "--repo", str(repo)))
    assert [node["id"] for node in data["trees"]] == ["prp-003"]
    source = repo / "docs/proposals" / PRP_NAME
    source.write_text(source.read_text().replace("status: implemented", "status: replaced")
                      .replace("depends_on: []", "depends_on: []\nreplaced_by: [prp-099, prp-009]"))
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "proposal.replaced_by" in result.stdout


def test_milestone_dependency_blocks_tree_until_members_are_implemented(
    python_exe, tmp_path
):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-002", milestone="阶段一")
    add_prp(repo, "prp-003", ["阶段一"])
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "depends_on: []",
        'depends_on: []\nmilestone: "阶段一"',
    )
    init_git(repo)
    data = payload(mdf(python_exe, "tree", "--repo", str(repo)))
    roots = {node["id"]: node for node in data["trees"]}
    assert set(roots) == {"prp-001", "prp-002", "prp-003"}
    assert roots["prp-003"]["blocked_by"] == ["阶段一"]
    assert roots["prp-001"]["children"] == []
    assert roots["prp-002"]["children"] == []
    replace(repo / "docs/proposals" / PRP_NAME, "status: ready", "status: implemented")
    replace(
        repo / "docs/proposals/prp-002-item-002.md",
        "status: ready",
        "status: implemented",
    )
    data = payload(mdf(python_exe, "tree", "--repo", str(repo)))
    assert [node["id"] for node in data["trees"]] == ["prp-003"]
    assert data["trees"][0]["blocked_by"] == []


def test_rejected_milestone_member_does_not_block_dependents(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-002", status="rejected", milestone="阶段一")
    replace(
        repo / "docs/proposals/prp-002-item-002.md",
        "status: rejected",
        "status: rejected\nreject-reason: wont-do",
    )
    add_prp(repo, "prp-003", ["阶段一"])
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "status: ready\ndepends_on: []",
        'status: implemented\ndepends_on: []\nmilestone: "阶段一"',
    )
    init_git(repo)
    data = payload(mdf(python_exe, "tree", "--repo", str(repo)))
    assert [node["id"] for node in data["trees"]] == ["prp-003"]
    assert data["trees"][0]["blocked_by"] == []


def test_split_rejects_branch_record_even_when_current_tree_has_no_changes(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-005", ["prp-001"])
    init_git(repo)
    git(repo, "checkout", "-b", "feature/started")
    folder = repo / "changes/unreleased/started"
    folder.mkdir(parents=True)
    (folder / "delivery.json").write_text(json.dumps({"proposal": "prp-001"}))
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 记录另一分支开工")
    git(repo, "checkout", "main")
    checkout_develop(repo)
    spec = tmp_path / "split.json"
    spec.write_text(json.dumps(split_spec(repo)))
    work = planning_worktree(python_exe, repo)
    result = mdf(python_exe, "prp-split", "--repo", str(work), "--spec-file", str(spec))
    assert "proposal_started" in result.stderr
    assert not git(work, "status", "--porcelain").stdout


def test_split_write_failure_restores_all_original_files(python_exe, tmp_path, monkeypatch):
    repo = copy_fixture(tmp_path).resolve()
    add_prp(repo, "prp-005", ["prp-001"])
    init_git(repo)
    checkout_develop(repo)
    spec = tmp_path / "split.json"
    spec.write_text(json.dumps(split_spec(repo)))
    work = planning_worktree(python_exe, repo).resolve()
    load_core_module()
    from mdf_core.prp_split import command_split
    original = Path.write_text
    target = work / "docs/proposals/prp-004-part-004.md"

    def fail_second(path, content, *args, **kwargs):
        if path == target:
            raise OSError("模拟第二项写入失败")
        return original(path, content, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_second)
    with pytest.raises(OSError):
        command_split(SimpleNamespace(repo=str(work), spec_file=str(spec), dry_run=False))
    assert not git(work, "status", "--porcelain").stdout
