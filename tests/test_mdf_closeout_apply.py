"""release-closeout 的直接写入与失败现场测试。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403


def test_closeout_apply_executes_directly_without_staged_repository(
    tmp_path: Path,
):
    core = load_core_module()
    repo = prepare_release_closeout_repo(tmp_path)
    context = closeout_context_for(core, repo, tmp_path, "service-health")

    result = core.apply_closeout(repo.resolve(), context)

    release_dir = repo / "changes" / "1.3.0"
    assert result["slugs"] == ["service-health"]
    assert (release_dir / "CHANGE.md").is_file()
    assert (release_dir / "service-health" / "CHANGE.md").is_file()
    assert not (repo / "changes" / "unreleased" / "service-health").exists()
    assert (repo / "docs/proposals" / "archive" / "1.3" / PRP_NAME).is_file()
    assert (repo / "docs/bugs" / "archive" / "1.3" / BUG_NAME).is_file()
    assert 'latest_release: "1.3.0"' in (
        repo / ".mdf" / "manifest.yaml"
    ).read_text(encoding="utf-8")
    assert not list(repo.rglob(".mdf-stage-*"))


def test_closeout_apply_failure_preserves_written_state(tmp_path: Path):
    core = load_core_module()
    repo = prepare_release_closeout_repo(tmp_path)
    context = closeout_context_for(core, repo, tmp_path, "service-health")
    collision = repo / "changes" / "1.3.0" / "service-health"
    collision.mkdir(parents=True)

    with pytest.raises(core.MDFError) as caught:
        core.apply_closeout(repo.resolve(), context)

    assert caught.value.code == "collision"
    proposal = repo / "docs/proposals" / PRP_NAME
    assert "status: released" in proposal.read_text(encoding="utf-8")
    assert git(repo, "status", "--porcelain").stdout


def test_closeout_preview_is_read_only_and_has_no_exact_write_set(
    tmp_path: Path,
):
    core = load_core_module()
    repo = prepare_release_closeout_repo(tmp_path)
    context = closeout_context_for(core, repo, tmp_path, "service-health")

    summary = core.summarize_closeout(repo.resolve(), context)

    assert summary["version"] == "1.3.0"
    assert summary["verification"]["executed"] is False
    assert "writes" not in summary
    assert (repo / "changes" / "unreleased" / "service-health").is_dir()
    assert not git(repo, "status", "--porcelain").stdout


def test_release_moves_delivery_materials_and_rewrites_proposal_links(python_exe, tmp_path):
    repo = prepare_release_closeout_repo(tmp_path)
    child = repo / "changes/unreleased/service-health"
    identity = {"proposal": "prp-001", "slug": "service-health", "start_commit": "a" * 40}
    (child / "delivery.json").write_text(json.dumps(identity))
    (child / "objectives.md").write_text(f"# 目标\n\n[需求](../../../docs/proposals/{PRP_NAME})\n")
    (child / "design.md").write_text("# 设计\n\n[实现](../../../src/service.py)\n")
    (child / "gates").mkdir()
    (child / "gates/code-review.json").write_text('{"summary":"交付审查证据"}\n')
    review = repo / "changes/unreleased/1.3.0"
    review.mkdir()
    (review / "code-review.md").write_text("# 审查\n\n通过。\n", encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 附带交付过程材料")
    payload(mdf(python_exe, "release-closeout", "--repo", str(repo), "--release-date", "2026-09-10"))
    archived = repo / "changes/1.3.0/service-health"
    assert json.loads((archived / "delivery.json").read_text()) == identity
    assert f"../../../docs/proposals/archive/1.3/{PRP_NAME}" in (archived / "objectives.md").read_text()
    assert (archived / "gates/code-review.json").is_file()
    assert (repo / "changes/1.3.0/code-review.md").is_file()
    assert not review.exists()
    assert not child.exists()
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full"))
