"""ODR 新纳入、候选返工与版本级发布声明。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import start_repo, commit
from test_late_decision import start_feature
from test_odr_acceptance import accept_release


def prepare(python_exe, tmp_path, *, version="1.3.0"):
    repo, remote = start_repo(tmp_path)
    replace(repo / "docs/bugs" / BUG_NAME, "status: open", f"status: closed\nfixed_in: {version}")
    commit(repo)
    git(repo, "branch", "-f", "develop", "master")
    git(repo, "push", "origin", "master", "develop")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "on-demand-release",
                       "--version", version, "--feature", "feature/service-health",
                       "--objectives-file", str(write_release_objectives(tmp_path))))
    odr = Path(data["worktree"])
    work = start_feature(python_exe, repo, tmp_path, "--target", data["branch"])
    (work / "feature.py").write_text("value = 1\n")
    commit(work)
    payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work)))
    return repo, remote, odr, work


@pytest.mark.parametrize("mode", ["local", "pr"])
def test_new_feature_commits_require_new_odr_acceptance(python_exe, tmp_path, mode):
    from mdf_core.lifecycle.late_decision import checkpoint
    from mdf_core.foundation.errors import MDFError
    repo, remote, odr, work = prepare(python_exe, tmp_path)
    accept_release(python_exe, odr)
    root = odr / "changes/unreleased/1.3.0"
    reports = {name: (root / name).read_bytes()
               for name in ("code-review.md", "verification-report.json", "fact-audit.md")}
    git(work, "checkout", "-b", "feature/service-health")
    (work / "feature.py").write_text("value = 2\n")
    commit(work)
    if mode == "local":
        payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work)))
    else:
        from support_pull import Platform
        from mdf_core.lifecycle.pull_finish import sync_local
        git(odr, "push", "origin", "on-demand-release/1.3.0")
        git(work, "push", "origin", "feature/service-health")
        platform = Platform()
        platform.repo, platform.remote = repo, remote
        platform.create("feature/service-health", "on-demand-release/1.3.0", "修复", "追加修复")
        platform.merge(1, tmp_path)
        git(odr, "fetch", "origin")
        sync_local(odr, "on-demand-release/1.3.0")
    assert all((root / name).read_bytes() == content for name, content in reports.items())
    with pytest.raises(MDFError, match="验收"):
        checkpoint(odr, required=True, release=True)
    accept_release(python_exe, odr)
    assert checkpoint(odr, required=True, release=True)["ready"]


@pytest.mark.parametrize("foreign", [False, "version", "membership", "published"])
def test_archived_candidate_can_be_reaccepted_without_downgrading_prp(python_exe, tmp_path, foreign):
    from mdf_core.documents.proposals import records
    from mdf_core.foundation.yamlutil import set_frontmatter_field
    repo, _remote, odr, _work = prepare(python_exe, tmp_path)
    manifest = odr / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
    commit(odr)
    accept_release(python_exe, odr)
    payload(mdf(python_exe, "release-closeout", "--repo", str(odr), "--release-date", "2026-11-07"))
    commit(odr)
    root = odr / "changes/1.3.0"
    obj = root / "objectives.md"
    obj.write_text(obj.read_text().replace("[x] ODR 统一验收", "[ ] ODR 统一验收"))
    path, metadata, _ = records(odr)[PRP_ID]
    assert metadata["status"] == "released"
    if foreign == "version":
        path.write_text(set_frontmatter_field(path.read_text(), "released_in", "9.9.9"))
    elif foreign == "membership":
        change = root / "CHANGE.md"
        change.write_text(change.read_text().replace("proposals: [prp-0001]", "proposals: []"))
    elif foreign == "published":
        git(odr, "tag", "v1.3.0")
    commit(odr)
    before = path.read_bytes()
    result = mdf(python_exe, "delivery", "accept", "--repo", str(odr))
    if foreign:
        assert "invalid_proposal" in result.stderr
        assert not git(odr, "status", "--porcelain").stdout.strip()
    else:
        assert payload(result)["result"]["accepted"]
        assert "[x] ODR 统一验收" in obj.read_text()
    assert path.read_bytes() == before


@pytest.mark.parametrize("version,category,breaking,allowed", [
    ("1.2.1", "Fixed", False, True),
    ("1.3.0", "Changed", True, False),
    ("2.0.0", "Removed", True, True),
])
def test_odr_release_summary_controls_notes_and_semver(python_exe, tmp_path, version, category, breaking, allowed):
    from mdf_core.foundation.yamlutil import read_frontmatter
    _repo, _remote, odr, _work = prepare(python_exe, tmp_path, version=version)
    notes = {category: ["已确认的本版变更"]}
    accept_release(python_exe, odr, summary={"release_notes": notes, "breaking": breaking})
    result = mdf(python_exe, "release-closeout", "--repo", str(odr), "--release-date", "2026-11-07")
    if not allowed:
        assert "insufficient_bump" in result.stderr
        return
    payload(result)
    root = odr / "changes" / version
    metadata, _ = read_frontmatter(root / "CHANGE.md")
    assert metadata["release_notes"] == notes
    assert metadata["breaking"] is breaking
    assert (root / "release-notes.json").is_file()


@pytest.mark.parametrize("summary", [None, {"release_notes": {"Unknown": ["说明"]}, "breaking": False},
                                      {"release_notes": {"Fixed": []}, "breaking": False},
                                      {"release_notes": {"Removed": ["移除接口"]}, "breaking": False},
                                      {"release_notes": {"Fixed": ["修复"]}, "breaking": "false"}])
def test_release_summary_must_be_valid_before_acceptance(python_exe, tmp_path, summary):
    _repo, _remote, odr, _work = prepare(python_exe, tmp_path)
    accept_release(python_exe, odr)
    root = odr / "changes/unreleased/1.3.0"
    path = root / "release-notes.json"
    if summary is None:
        path.unlink()
    else:
        path.write_text(json.dumps(summary))
    commit(odr)
    result = mdf(python_exe, "delivery", "accept", "--repo", str(odr))
    assert "invalid_release_summary" in result.stderr
    assert not git(odr, "status", "--porcelain").stdout.strip()


def test_archived_summary_change_requires_candidate_update(python_exe, tmp_path):
    _repo, _remote, odr, _work = prepare(python_exe, tmp_path)
    manifest = odr / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
    commit(odr)
    accept_release(python_exe, odr)
    payload(mdf(python_exe, "release-closeout", "--repo", str(odr), "--release-date", "2026-11-07"))
    root = odr / "changes/1.3.0"
    (root / "release-notes.json").write_text(json.dumps({"release_notes": {"Removed": ["移除接口"]}, "breaking": True}))
    commit(odr)
    result = mdf(python_exe, "delivery", "accept", "--repo", str(odr))
    assert "invalid_release_summary" in result.stderr
    assert not git(odr, "status", "--porcelain").stdout.strip()
