"""HTML 总结搬迁时保留含空格的路径、query、fragment 和 entity。"""
from mdf_test_support import *  # noqa: F403


def test_html_evidence_links_survive_move_with_spaces_and_entities(tmp_path):
    load_core_module()
    from mdf_core.moves import replacement_plan, apply_moves_and_rewrites
    from mdf_core.validate_links import collect_local_link_findings
    repo = tmp_path / "repo"
    source = repo / "changes/unreleased/1.3.0/delivery-summary.html"
    source.parent.mkdir(parents=True)
    target = repo / "src/run book & details.txt"
    target.parent.mkdir()
    target.write_text("证据")
    source.write_text(
        '<!doctype html><html><body><main><h1>总结</h1>'
        '<a href="../../../src/run book &amp; details.txt?x=1&amp;y=2#details">证据</a>'
        '<a href="https://example.invalid/a?x=1&amp;y=2">外部证据</a>'
        '</main></body></html>')
    findings = []
    collect_local_link_findings(repo, source, findings)
    assert findings == []
    destination = repo / "changes/1.3.0/delivery-summary.html"
    moves = {source: destination}
    rewrites = replacement_plan(repo, moves)
    apply_moves_and_rewrites(moves, rewrites)
    text = destination.read_text()
    assert 'href="../../src/run book &amp; details.txt?x=1&amp;y=2#details"' in text
    assert 'href="https://example.invalid/a?x=1&amp;y=2"' in text
    collect_local_link_findings(repo, destination, findings)
    assert findings == []
