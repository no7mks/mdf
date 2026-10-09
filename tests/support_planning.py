"""规划类 E2E 共用的 Proposal 构造。"""
from types import SimpleNamespace
from mdf_test_support import *  # noqa: F403


def add_prp(repo, identifier, deps=(), status="ready", milestone=None, slug=None):
    template = proposal_markdown(repo / "docs/proposals" / PRP_NAME)
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
    suffix = ".md" if status == "draft" else ".html"
    path = repo / "docs/proposals" / f"{identifier}-{slug}{suffix}"
    path.write_text(text if suffix == ".md" else proposal_html(text))
    return path
