"""release-closeout 移动交付材料并重写 Proposal 链接。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


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
    (review / "objectives.md").write_text("# 发布目标\n\n本版收口。\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 附带交付过程材料")
    seed_verify_branch(python_exe, repo)
    payload(mdf(python_exe, "release-closeout", "--repo", str(repo), "--release-date", "2026-09-10"))
    archived = repo / "changes/1.3.0/service-health"
    assert json.loads((archived / "delivery.json").read_text()) == identity
    assert f"../../../docs/proposals/archive/1.3/{PRP_NAME}" in (archived / "objectives.md").read_text()
    assert (archived / "gates/code-review.json").is_file()
    assert (repo / "changes/1.3.0/code-review.md").is_file()
    assert (repo / "changes/1.3.0/objectives.md").is_file()
    assert not review.exists()
    assert not child.exists()
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full"))
