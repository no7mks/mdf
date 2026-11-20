"""feature 纳入 ODR 后统一验收，不补做来源交付。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import start_repo, commit
from test_late_decision import start_odr, start_feature


def accept_release(python_exe, odr, *, summary=None):
    version = git(odr, "branch", "--show-current").stdout.strip().split("/", 1)[1]
    root = odr / "changes/unreleased" / version
    data = json.loads((root / "delivery.json").read_text())
    if summary is None:
        notes = [item["scope"] for item in data.get("scope", [])] or ["本版功能更新"]
        summary = {"release_notes": {"Changed": notes}, "breaking": False}
    (root / "release-notes.json").write_text(json.dumps(summary, ensure_ascii=False))
    objectives = root / "objectives.md"
    text = objectives.read_text()
    for step in ("lint", "code-review", "verify branch", "fact audit"):
        text = text.replace(f"- [ ] {step}", f"- [x] {step}")
    objectives.write_text(text)
    (root / "fact-audit.md").write_text("# Fact audit\n\n已核对整版范围，无未解决问题。\n")
    if git(odr, "status", "--porcelain").stdout.strip():
        commit(odr)
    seed_verify_branch(python_exe, odr)
    payload(mdf(python_exe, "delivery", "accept", "--repo", str(odr)))
    if git(odr, "status", "--porcelain").stdout.strip():
        commit(odr)


@pytest.mark.parametrize("mode", ["local", "pr"])
@pytest.mark.parametrize("manual", [False, True])
def test_feature_inclusion_defers_acceptance_and_preserves_context(python_exe, tmp_path, monkeypatch, mode, manual):
    from support_pull import Platform, squash_pending
    from mdf_core.lifecycle import pull_finish
    from mdf_core.foundation.yamlutil import read_frontmatter
    repo, remote = start_repo(tmp_path)
    replace(repo / "docs/bugs" / BUG_NAME, "status: open", "status: closed\nfixed_in: 1.3.0")
    if mode == "pr":
        manifest = repo / ".mdf/manifest.yaml"
        manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
    commit(repo)
    git(repo, "branch", "-f", "develop", "master")
    git(repo, "push", "origin", "master", "develop")
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    identity = {"provider": "github", "host": "forge.invalid", "project": "team/project", "origin": str(remote)}
    monkeypatch.setattr(pull_finish, "origin", lambda *_: identity)
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    odr = start_odr(python_exe, repo, tmp_path)
    if mode == "pr":
        git(odr, "push", "origin", "on-demand-release/1.3.0")
    if manual:
        from test_manual_feature import objectives
        obj = tmp_path / "manual.md"
        obj.write_text(objectives())
        result = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature", "--manual",
                             "--name", "service-health", "--from-master", "--target", "on-demand-release/1.3.0",
                             "--objectives-file", str(obj)))
        work = Path(result["worktree"])
    else:
        work = start_feature(python_exe, repo, tmp_path, "--target", "on-demand-release/1.3.0")
    root = work / "changes/unreleased/service-health"
    original = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    (work / "feature.py").write_text("feature = True\n")
    commit(work)
    if mode == "pr":
        squash_pending(work)
        payload(mdf(python_exe, "incremental-integration", "--repo", str(work)))
        from support_delivery import seed_consolidation
        seed_consolidation(work)
        squash_pending(work)
        payload(mdf(python_exe, "pr", "--repo", str(work)))
        platform.merge(1, tmp_path)
    payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work)))
    assert read_frontmatter(odr / "docs/proposals" / PRP_NAME)[0]["status"] == "ready"
    assert payload(mdf(python_exe, "delivery", "checkpoint", "--repo", str(odr)))["result"]["ready"]
    assert "odr_acceptance_pending" in mdf(python_exe, "delivery", "accept", "--repo", str(odr)).stderr
    assert "odr_acceptance_pending" in mdf(python_exe, "release-closeout", "--repo", str(odr),
                                           "--release-date", "2026-11-07").stderr
    accept_release(python_exe, odr)
    assert read_frontmatter(odr / "docs/proposals" / PRP_NAME)[0]["status"] == ("ready" if manual else "implemented")
    payload(mdf(python_exe, "release-closeout", "--repo", str(odr), "--release-date", "2026-11-07"))
    archived = odr / "changes/1.3.0/service-health"
    assert {p.name: p.read_bytes() for p in archived.iterdir() if p.is_file()} == original
    assert not (archived / "CHANGE.md").exists()
    commit(odr)
    if mode == "pr":
        squash_pending(odr)
        payload(mdf(python_exe, "pr", "--repo", str(odr)))
        platform.merge(2, tmp_path)
    assert payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(odr)))["targets"] == ["master", "develop"]


@pytest.mark.parametrize("failure", ["missing_review", "missing_fact", "failed_tests", "smoke_only", "other_branch"])
def test_failed_odr_acceptance_keeps_prp_ready(python_exe, tmp_path, failure):
    from support_delivery import local_repo
    from mdf_core.foundation.yamlutil import read_frontmatter
    repo = local_repo(tmp_path)
    odr = start_odr(python_exe, repo, tmp_path)
    work = start_feature(python_exe, repo, tmp_path, "--target", "on-demand-release/1.3.0")
    payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work)))
    root = odr / "changes/unreleased/1.3.0"
    obj = root / "objectives.md"
    obj.write_text(obj.read_text().replace("[ ]", "[x]").replace("[x] ODR 统一验收", "[ ] ODR 统一验收"))
    if failure != "missing_review":
        (root / "code-review.md").write_text("整版 review 通过。\n")
    if failure != "missing_fact":
        (root / "fact-audit.md").write_text("整版 fact audit 通过。\n")
    report = {"branch": "on-demand-release/1.3.0", "scope": "branch", "suites": ["release"], "all_passed": True}
    if failure == "failed_tests":
        report["all_passed"] = False
    elif failure == "smoke_only":
        report["suites"] = ["smoke"]
    elif failure == "other_branch":
        report["branch"] = "feature/service-health"
    (root / "verification-report.json").write_text(json.dumps(report))
    commit(odr)
    assert "odr_acceptance_pending" in mdf(python_exe, "delivery", "accept", "--repo", str(odr)).stderr
    assert read_frontmatter(odr / "docs/proposals" / PRP_NAME)[0]["status"] == "ready"
    assert "[ ] ODR 统一验收" in obj.read_text()
    assert not git(odr, "status", "--porcelain").stdout.strip()


def test_scope_inclusion_allows_verification_without_source_reports(python_exe, tmp_path):
    from support_delivery import local_repo
    from test_odr_scope import start_scope
    repo = local_repo(tmp_path)
    entries = [dict(id="fix", kind="direct", scope="本版修复", source="ODR")]
    odr = start_scope(python_exe, repo, tmp_path, entries)
    (odr / "fix.py").write_text("fixed = True\n")
    commit(odr)
    entries[0]["commits"] = [git(odr, "rev-parse", "HEAD").stdout.strip()]
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps(entries))
    payload(mdf(python_exe, "delivery", "scope", "--repo", str(odr), "--scope-file", str(scope)))
    commit(odr)
    assert payload(mdf(python_exe, "delivery", "checkpoint", "--repo", str(odr)))["result"]["ready"]
    seed_verify_branch(python_exe, odr)
    assert "odr_acceptance_pending" in mdf(python_exe, "delivery", "accept", "--repo", str(odr)).stderr
    accept_release(python_exe, odr)
    entries[0]["scope"] = "扩大的修复范围"
    scope.write_text(json.dumps(entries))
    payload(mdf(python_exe, "delivery", "scope", "--repo", str(odr), "--scope-file", str(scope)))
    assert "[ ] ODR 统一验收" in (odr / "changes/unreleased/1.3.0/objectives.md").read_text()
