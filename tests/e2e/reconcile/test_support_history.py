"""support 外部历史可不在 trunk 上，导入不污染当前主线事实。"""
import json

import pytest

from mdf_test_support import git, payload
from support_reconcile import repository, change, prepare, spec_file, apply, call
from support_github_flow import error_of
from mdf_core.foundation.errors import MDFError
from mdf_core.inspection.validate_release import validate_release_history
from mdf_core.foundation.paths import load_manifest
from mdf_core.foundation.yamlutil import read_frontmatter


def support_history(tmp_path):
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "support/1.2", "v1.2.0")
    patch = change(repo, "patch")
    git(repo, "tag", "v1.2.1")
    git(repo, "switch", "master")
    change(repo, "trunk_future")
    return repo, patch


def test_support_external_tag_import_preserves_trunk(python_exe, tmp_path):
    repo, patch = support_history(tmp_path)
    before = {p.relative_to(repo): p.read_bytes() for p in (repo / "docs").rglob("*.md")}
    manifest = (repo / ".mdf/manifest.yaml").read_bytes()
    work = prepare(python_exe, repo, "1.2.1", "--support", "1.2")
    spec = spec_file(tmp_path, work, patch)
    data = json.loads(spec.read_text())
    data["changes"][0]["release_notes"] = {"Fixed": ["维护线外部修复"]}
    spec.write_text(json.dumps(data))
    payload(apply(python_exe, work, spec, "1.2.1"))
    root = work / "changes/1.2.1"
    assert not any(p.is_dir() for p in root.iterdir())
    meta, _ = read_frontmatter(root / "CHANGE.md")
    assert meta["release_commit"] == patch and meta["release_line"] == "support/1.2"
    assert (work / ".mdf/manifest.yaml").read_bytes() == manifest
    assert {p: (work / p).read_bytes() for p in before} == before
    findings = []
    validate_release_history(work, load_manifest(work), findings)
    assert not findings, [f.as_dict() for f in findings]
    from mdf_core.lifecycle.closeout_render import require_tag_content
    with pytest.raises(MDFError, match="annotated"):
        require_tag_content(work, "1.2.1")


def test_explicit_commit_must_belong_to_declared_support(python_exe, tmp_path):
    repo, _ = support_history(tmp_path)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    failed = call(python_exe, repo, "inspect", "--version", "1.2.2", "--commit", head, "--support", "1.2")
    assert error_of(failed)["error"] == "invalid_release_commit"
    assert not git(repo, "status", "--porcelain").stdout
