"""closeout 预览与直接写入、失败时保留现场。"""
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
