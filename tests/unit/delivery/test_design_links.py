"""design 材料本地链接的规范化。"""
from mdf_test_support import *  # noqa: F403


def test_canonical_local_link_missing_is_not_delivery_internal(tmp_path: Path):
    load_core_module()
    from mdf_core.inspection.validate_links import canonical_local_link

    repo = copy_fixture(tmp_path)
    root = repo / "changes/unreleased/service-health"
    root.mkdir(parents=True)
    source = root / "objectives.md"
    source.write_text("# 目标\n")
    (root / "design.md").write_text("# 设计\n")
    ghost = canonical_local_link(
        repo, source, f"docs/proposals/{PRP_NAME}", root
    )
    assert ghost == (
        f"changes/unreleased/service-health/docs/proposals/{PRP_NAME}"
    )
    assert not ghost.startswith("@delivery/")
    real = canonical_local_link(
        repo, source, f"../../../docs/proposals/{PRP_NAME}", root
    )
    assert real == f"docs/proposals/{PRP_NAME}"
    sibling = canonical_local_link(repo, source, "design.md", root)
    assert sibling == "@delivery/design.md"
