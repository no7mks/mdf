"""具名验证配置、PRP 拆分事务与依赖视图。"""
from mdf_test_support import *  # noqa: F403


def add_prp(repo, identifier, deps=(), status="ready"):
    template = (repo / "proposals" / PRP_NAME).read_text()
    text = template.replace("prp-AB23", identifier).replace("depends_on: []", f"depends_on: {json.dumps(list(deps))}")
    text = text.replace("status: ready", f"status: {status}")
    path = repo / "proposals" / f"{identifier}-item.md"
    path.write_text(text)
    return path


def test_next_ready_dag_drafts_truncation_and_invalid_dependencies(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-EF56", ["prp-AB23"])
    add_prp(repo, "prp-GH78", ["prp-AB23"])
    add_prp(repo, "prp-JK89", ["prp-EF56", "prp-GH78"])
    add_prp(repo, "prp-LM23", status="draft")
    add_prp(repo, "prp-NP45", ["prp-LM23"])
    init_git(repo)
    data = payload(mdf(python_exe, "next", "--repo", str(repo)))
    assert data["needs_review"] == ["prp-LM23"]
    assert data["blocked"] == [{"id": "prp-NP45", "blocked_by": ["prp-LM23"]}]
    children = data["trees"][0]["children"]
    assert children[1]["children"][0]["reference"] is True
    assert children[0]["children"][0]["blocked_by"] == ["prp-EF56", "prp-GH78"]
    shallow = payload(mdf(python_exe, "next", "--repo", str(repo), "--depth", "1"))
    assert shallow["hidden"] == ["prp-EF56", "prp-GH78", "prp-JK89"]
    assert mdf(python_exe, "next", "--repo", str(repo), "--depth", "0").returncode != 0
    add_prp(repo, "prp-QR67", ["prp-ZZ99"])
    assert "invalid_proposals" in mdf(python_exe, "next", "--repo", str(repo)).stderr


def split_spec(repo):
    body = (repo / "proposals" / PRP_NAME).read_text().split("---", 2)[2]
    return {"source": "prp-AB23", "rationale": "用户确认两项共同覆盖验收，下游仅依赖第一项",
            "children": [{"id": key, "filename": f"{key}-part.md", "depends_on": [], "body": body}
                         for key in ("prp-EF56", "prp-GH78")],
            "downstream": {"prp-JK89": ["prp-EF56"]}}


def test_split_preview_then_transaction_and_downstream(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-JK89", ["prp-AB23"])
    init_git(repo)
    spec = tmp_path / "split.json"
    spec.write_text(json.dumps(split_spec(repo)))
    args = ["prp-split", "--repo", str(repo), "--spec-file", str(spec)]
    before = git(repo, "status", "--porcelain").stdout
    result = payload(mdf(python_exe, *args, "--dry-run"))
    assert len(result["files"]) == 4
    assert git(repo, "status", "--porcelain").stdout == before
    payload(mdf(python_exe, *args))
    assert 'status: "replaced"' in (repo / "proposals" / PRP_NAME).read_text()
    assert 'depends_on: ["prp-EF56"]' in (repo / "proposals/prp-JK89-item.md").read_text()
    assert 'status: "draft"' in (repo / "proposals/prp-EF56-part.md").read_text()
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


def test_invalid_split_has_no_partial_writes(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-JK89", ["prp-AB23"])
    init_git(repo)
    spec = split_spec(repo)
    spec["children"][0]["depends_on"] = ["prp-JK89"]
    path = tmp_path / "split.json"
    path.write_text(json.dumps(spec))
    result = mdf(python_exe, "prp-split", "--repo", str(repo), "--spec-file", str(path))
    assert "invalid_proposals" in result.stderr
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


def test_implemented_dependencies_unlock_next_and_replaced_relations_validate(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    replace(repo / "proposals" / PRP_NAME, "status: ready", "status: implemented")
    add_prp(repo, "prp-EF56", ["prp-AB23"])
    # add_prp copies its source; explicitly keep the dependent ready.
    replace(repo / "proposals/prp-EF56-item.md", "status: implemented", "status: ready")
    init_git(repo)
    data = payload(mdf(python_exe, "next", "--repo", str(repo)))
    assert [node["id"] for node in data["trees"]] == ["prp-EF56"]
    source = repo / "proposals" / PRP_NAME
    source.write_text(source.read_text().replace("status: implemented", "status: replaced")
                      .replace("depends_on: []", "depends_on: []\nreplaced_by: [prp-ZZ99, prp-XX88]"))
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "proposal.replaced_by" in result.stdout


@pytest.mark.parametrize("location", [".specs/started", "changes/unreleased/started"])
def test_split_rejects_branch_record_even_when_current_tree_has_no_specs(python_exe, tmp_path, location):
    repo = copy_fixture(tmp_path)
    add_prp(repo, "prp-JK89", ["prp-AB23"])
    init_git(repo)
    git(repo, "checkout", "-b", "feature/started")
    folder = repo / location
    folder.mkdir(parents=True)
    (folder / "delivery.json").write_text(json.dumps({"proposal": "prp-AB23"}))
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 记录另一分支开工")
    git(repo, "checkout", "main")
    spec = tmp_path / "split.json"
    spec.write_text(json.dumps(split_spec(repo)))
    result = mdf(python_exe, "prp-split", "--repo", str(repo), "--spec-file", str(spec))
    assert "proposal_started" in result.stderr
    assert not git(repo, "status", "--porcelain").stdout


def test_split_write_failure_restores_all_original_files(python_exe, tmp_path, monkeypatch):
    repo = copy_fixture(tmp_path).resolve()
    add_prp(repo, "prp-JK89", ["prp-AB23"])
    init_git(repo)
    spec = tmp_path / "split.json"
    spec.write_text(json.dumps(split_spec(repo)))
    load_core_module()
    from mdf_core.prp_split import command_split
    original = Path.write_text
    target = repo / "proposals/prp-GH78-part.md"

    def fail_second(path, content, *args, **kwargs):
        if path == target:
            raise OSError("模拟第二项写入失败")
        return original(path, content, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_second)
    with pytest.raises(OSError):
        command_split(SimpleNamespace(repo=str(repo), spec_file=str(spec), dry_run=False))
    assert not git(repo, "status", "--porcelain").stdout
