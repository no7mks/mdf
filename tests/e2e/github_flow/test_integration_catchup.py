"""独立集成分支的正常增量验收入口与阶段归属。"""
from mdf_test_support import *  # noqa: F403
from support_github_flow import commit, publish_release, error_of
from test_publish_stage import release


def test_integration_has_materials_plan_review_verify_and_completion(python_exe, tmp_path, monkeypatch):
    repo, remote, _platform, work = release(python_exe, tmp_path, monkeypatch)
    (work / "src/release.py").write_text("release_change = True\n")
    commit(work)
    published = publish_release(python_exe, work)
    integrated = payload(mdf(python_exe, "release-integrate", "--repo", str(work)))
    integ = Path(integrated["worktree"])
    assert integrated["next_intent"] == "catch-up"
    plan = payload(mdf(python_exe, "catch-up-plan", "--repo", str(integ)))["result"]
    assert all(plan[k]["action"] == "skip" for k in ("review", "verify", "fact"))
    route = payload(mdf(python_exe, "delivery", "route", "--repo", str(integ)))["result"]
    assert route["next"] == "catch-up" and route["auto_completable"]
    payload(mdf(python_exe, "delivery", "complete-stage", "--stage", "catch-up", "--repo", str(integ)))
    objective = "changes/unreleased/1.3.0/objectives.md"
    assert "- [x] catch-up" in (integ / objective).read_text()
    assert "- [ ] catch-up" in (work / objective).read_text()
    (repo / "src/service.py").write_text("main_change = True\n")
    commit(repo)
    git(repo, "push", "origin", "main")
    direct = mdf(python_exe, "pr", "--repo", str(work))
    assert error_of(direct)["error"] == "integration_required"
    payload(mdf(python_exe, "release-integrate", "--repo", str(work)))
    assert "- [ ] catch-up" in (integ / objective).read_text()
    plan = payload(mdf(python_exe, "catch-up-plan", "--repo", str(integ)))["result"]
    assert plan["verify"]["action"] == "smart"
    payload(mdf(python_exe, "review-prepare", "--repo", str(integ), "--against", plan["base"]))
    report = "changes/unreleased/1.3.0/catch-up-verification-report.json"
    payload(mdf(python_exe, "verify", "--repo", str(integ), "--scope", "smart", "--paths", "src/service.py",
                "--report-file", report))
    assert (integ / report).is_file()
    commit(integ)
    context = payload(mdf(python_exe, "review-context", "--repo", str(integ),
                          "--source", integrated["branch"], "--head", "HEAD", "--policy-ref", "origin/main"))["result"]
    assert context["kind"] == "integration" and context["target"] == "main"
    assert context["delivery_base"] == published
    assert "src/service.py" in context["paths"]
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == published
