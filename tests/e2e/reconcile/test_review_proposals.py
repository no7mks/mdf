"""缺少 child 时保留可核实的 feature/bugfix 来源和已有 PRP。"""
import json

import pytest

from mdf_test_support import git, payload
from support_reconcile import repository, change, prepare, spec_file, apply
from mdf_core.foundation.yamlutil import read_frontmatter


@pytest.mark.parametrize("kind", ["feature", "bugfix"])
def test_external_change_keeps_real_source_and_existing_object(python_exe, tmp_path, kind):
    repo = repository(tmp_path)
    slug = "service-health" if kind == "feature" else "bug-cd34"
    source = "feature/service-health" if kind == "feature" else "bugfix/bug-CD34"
    git(repo, "switch", "-c", source)
    source_head = change(repo)
    git(repo, "switch", "master")
    git(repo, "merge", "--no-ff", "--no-edit", source)
    released = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "tag", "v1.3.0")
    work = prepare(python_exe, repo)
    spec = spec_file(tmp_path, work, released, [source_head, released])
    data = json.loads(spec.read_text())
    data["changes"][0].update(slug=slug, change_kind=kind, source_branch=source, source_head=source_head,
                              proposals=["prp-0001"] if kind == "feature" else [], fixed=["bug-CD34"] if kind == "bugfix" else [])
    spec.write_text(json.dumps(data))
    payload(apply(python_exe, work, spec))
    meta, _ = read_frontmatter(work / f"changes/1.3.0/{slug}/CHANGE.md")
    assert meta["source_branch"] == source and meta["change_kind"] == kind
    assert meta["proposals"] == data["changes"][0]["proposals"]
    assert "status: ready" in (work / "docs/proposals/prp-0001-service-health.md").read_text()
    assert "status: open" in (work / "docs/bugs/bug-CD34-unreleased-timeout.md").read_text()


@pytest.mark.parametrize("invalid", ["no-source-proof", "object-not-in-history", "wrong-source-head"])
def test_cannot_bind_unproven_proposal_to_historical_change(python_exe, tmp_path, invalid):
    repo = repository(tmp_path)
    head = change(repo)
    git(repo, "tag", "v1.3.0")
    if invalid == "object-not-in-history":
        original = repo / "docs/proposals/prp-0001-service-health.md"
        (repo / "docs/proposals/prp-0002-later.md").write_text(original.read_text().replace("prp-0001", "prp-0002"))
        from support_delivery import commit
        commit(repo)
        git(repo, "branch", "feature/later", head)
    work = prepare(python_exe, repo)
    spec = spec_file(tmp_path, work, head)
    data = json.loads(spec.read_text())
    item = data["changes"][0]
    item.update(slug="service-health", change_kind="feature", source_branch="feature/service-health", proposals=["prp-0001"])
    if invalid == "object-not-in-history":
        item.update(slug="later", source_branch="feature/later", proposals=["prp-0002"], source_head=head)
    elif invalid == "wrong-source-head":
        item["source_head"] = git(repo, "rev-parse", "v1.2.0^{commit}").stdout.strip()
    spec.write_text(json.dumps(data))
    assert apply(python_exe, work, spec).returncode != 0
    assert not (work / "changes/1.3.0").exists()


@pytest.mark.parametrize("forge_result", [None, "valid", "wrong-source", "wrong-head", "open"])
def test_merge_parent_alone_cannot_prove_a_deleted_branch_name(python_exe, tmp_path, monkeypatch, forge_result):
    repo = repository(tmp_path)
    source = "feature/service-health" if forge_result == "valid" else "feature/unrelated"
    git(repo, "switch", "-c", source)
    source_head = change(repo)
    git(repo, "switch", "master")
    git(repo, "merge", "--no-ff", "--no-edit", source)
    released = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "branch", "-d", source)
    git(repo, "tag", "v1.3.0")
    work = prepare(python_exe, repo)
    spec = spec_file(tmp_path, work, released, [source_head, released])
    data = json.loads(spec.read_text())
    item = data["changes"][0]
    item.update(slug="service-health", change_kind="feature", source_branch="feature/service-health",
                source_head=source_head, proposals=["prp-0001"])
    if forge_result is not None:
        item["pull_request"] = {"provider": "github", "number": 1}
        from mdf_core.integrations import forge
        pull = {"source": "feature/unrelated" if forge_result == "wrong-source" else "feature/service-health",
                "head": released if forge_result == "wrong-head" else source_head, "merge_commit": released,
                "state": "open" if forge_result == "open" else "merged", "url": "https://forge.invalid/pull/1"}
        from types import SimpleNamespace
        monkeypatch.setattr(forge, "origin", lambda *_: {})
        monkeypatch.setattr(forge, "Forge", lambda *_: SimpleNamespace(get=lambda number: pull))
    spec.write_text(json.dumps(data))
    result = apply(python_exe, work, spec)
    if forge_result == "valid":
        payload(result)
        meta, _ = read_frontmatter(work / "changes/1.3.0/service-health/CHANGE.md")
        assert meta["proposals"] == ["prp-0001"]
    else:
        assert result.returncode != 0, result.stdout
        assert not (work / "changes/1.3.0").exists()
