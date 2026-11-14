"""PR watch 的离线平台快照与退出条件。"""
import pytest

from mdf_core.foundation.errors import MDFError
from mdf_core.integrations import pull_status
from mdf_core.lifecycle import pull_watch


@pytest.mark.parametrize("conclusion, expected", [("success", "merged"), ("failure", "ci_failed")])
def test_watch_waits_for_ci_after_merge(monkeypatch, tmp_path, conclusion, expected):
    pull = {"id": 1, "state": "merged", "source": "adhoc/docs", "target": "master", "head": "tip"}
    snapshots = iter([None, conclusion, conclusion])
    sleeps = []
    monkeypatch.setattr(pull_watch, "lookup_pull", lambda *args, **kwargs: (pull, pull["target"]))
    monkeypatch.setattr(pull_watch, "sleep", sleeps.append)
    monkeypatch.setattr(pull_watch, "pull_status", lambda *args: {
        "pull_request": pull, "checks": [{"conclusion": next(snapshots)}],
        "change_requests": [], "conflicts": False,
    })

    result = pull_watch.watch(tmp_path, pull["source"], None, [], False)
    assert result["status"] == expected
    assert sleeps == ([120, 120] if expected == "merged" else [120])


def test_watch_rejects_replacement_head(monkeypatch, tmp_path):
    pull = {"id": 1, "state": "open", "source": "adhoc/docs", "target": "master", "head": "a" * 40}
    monkeypatch.setattr(pull_watch, "lookup_pull", lambda *args, **kwargs: (pull, pull["target"]))
    snapshots = iter((pull, {**pull, "state": "merged", "head": "b" * 40}))
    monkeypatch.setattr(pull_watch, "pull_status", lambda *_: {
        "pull_request": next(snapshots), "checks": [], "change_requests": [], "conflicts": False,
    })
    monkeypatch.setattr(pull_watch, "sleep", lambda _: None)
    with pytest.raises(MDFError) as exc:
        pull_watch.watch(tmp_path, pull["source"], None, [], False, expected_head=pull["head"])
    assert exc.value.code == "pull_state_changed"


def test_github_snapshot_includes_originating_run_current_attempt_and_steps(monkeypatch):
    class Forge:
        endpoint = "repos/team/project/pulls"

        def api(self, endpoint):
            assert endpoint == "repos/team/project/actions/runs/9"
            return dict(id=9, status="completed", conclusion="failure", run_attempt=2, check_suite_id=4,
                        head_sha="base", html_url="https://forge.invalid/runs/9")

    def pages(forge, endpoint, key=None, **query):
        if endpoint.endswith("/attempts/2/jobs"):
            return [dict(id=3, name="test", status="completed", conclusion="failure", steps=[
                dict(name="test", number=1, status="completed", conclusion="failure")])]
        if endpoint.endswith("/attempts/1/jobs"):
            return [dict(id=1, name="test", status="completed", conclusion="failure"),
                    dict(id=2, name="lint", status="completed", conclusion="skipped")]
        assert "/jobs" not in endpoint
        return []

    monkeypatch.setattr(pull_status, "pages", pages)
    raw = dict(number=1, head=dict(sha="tip", ref="adhoc/docs"), mergeable=True, created_at="2026-11-14T00:00:00Z")
    result = pull_status.github_status(Forge(), "repos/team/project/pulls/1", raw, [9])
    assert [check["kind"] for check in result["checks"]] == ["workflow", "job", "step", "job"]
    assert [check["attempt"] for check in result["checks"]] == [2, 2, 2, 1]
    assert result["checks"][-1]["conclusion"] == "skipped"
    assert result["checks"][0]["head"] == "base"
    assert result["checks"][2]["job_id"] == 3


def test_gitlab_snapshot_waits_for_child_pipeline(monkeypatch):
    class Forge:
        endpoint = "projects/team%2Fproject/merge_requests"

        def api(self, endpoint):
            if endpoint == "projects/2/pipelines/9":
                return dict(id=9, status="success", sha="tip")
            assert endpoint == "projects/3/pipelines/10"
            return dict(id=10, status="waiting_for_callback", sha="child")

    def pages(forge, endpoint, key=None, **query):
        if endpoint == "projects/2/pipelines/9/bridges":
            return [dict(id=5, status="success", downstream_pipeline=dict(project_id=3, id=10))]
        return []

    monkeypatch.setattr(pull_status, "pages", pages)
    raw = dict(target_project_id=2, state="opened", sha="tip", head_pipeline=dict(id=9),
               detailed_merge_status="ci_still_running")
    checks = pull_status.gitlab_status(Forge(), "projects/team%2Fproject/merge_requests/1", raw, [])["checks"]
    assert [check["project_id"] for check in checks] == [2, 2, 3]
    assert checks[-1]["conclusion"] is None


def test_github_snapshot_tracks_merge_commit_status_and_old_change_request(monkeypatch):
    class Forge:
        endpoint = "repos/team/project/pulls"

    def pages(forge, endpoint, key=None, **query):
        if endpoint.endswith("/reviews"):
            return [dict(id=6, state="CHANGES_REQUESTED", user=dict(login="reviewer"), commit_id="old-tip")]
        if endpoint.endswith("/commits/merged/status"):
            return [dict(id=1, context="external", state="pending")]
        return []

    monkeypatch.setattr(pull_status, "pages", pages)
    raw = dict(number=1, head=dict(sha="tip", ref="adhoc/docs"), created_at="2026-11-14T00:00:00Z",
               merged_at="2026-11-14T01:00:00Z", merge_commit_sha="merged")
    snapshot = pull_status.github_status(Forge(), "repos/team/project/pulls/1", raw, [])
    assert snapshot["change_requests"] == ["6"]
    assert snapshot["checks"][0]["head"] == "merged"
    assert snapshot["checks"][0]["conclusion"] is None


def test_github_skipped_step_waits_for_running_job(monkeypatch):
    class Forge:
        endpoint = "repos/team/project/pulls"

    def pages(forge, endpoint, key=None, **query):
        if query.get("head_sha") == "tip":
            return [dict(id=9, status="in_progress", run_attempt=2, check_suite_id=4)]
        if endpoint.endswith("/attempts/2/jobs"):
            return [dict(id=3, name="test", status="in_progress", steps=[
                dict(name="conditional", number=1, status="completed", conclusion="skipped")])]
        assert "/attempts/" not in endpoint
        return []

    monkeypatch.setattr(pull_status, "pages", pages)
    raw = dict(number=1, head=dict(sha="tip", ref="adhoc/docs"), created_at="2026-11-14T00:00:00Z")
    snapshot = pull_status.github_status(Forge(), "repos/team/project/pulls/1", raw, [])
    assert all(check["conclusion"] is None for check in snapshot["checks"])


def test_handled_review_only_suppresses_the_same_request(monkeypatch, tmp_path):
    pull = {"id": 1, "state": "open", "source": "adhoc/docs", "target": "master", "head": "tip"}
    requests = iter([["6"], ["6", "7"]])
    sleeps = []
    monkeypatch.setattr(pull_watch, "lookup_pull", lambda *args, **kwargs: (pull, pull["target"]))
    monkeypatch.setattr(pull_watch, "sleep", sleeps.append)
    monkeypatch.setattr(pull_watch, "pull_status", lambda *args: {
        "pull_request": pull, "checks": [], "change_requests": next(requests), "conflicts": False,
    })
    result = pull_watch.watch(tmp_path, pull["source"], None, [], False, handled_reviews=["6"])
    assert result["status"] == "changes_requested"
    assert result["change_requests"] == ["6", "7"]
    assert sleeps == [120]


def test_pagination_rejects_incomplete_platform_results():
    class Forge:
        def api(self, endpoint):
            return dict(total_count=101, jobs=[dict(id=1)])

    with pytest.raises(MDFError, match="分页未覆盖全部结果"):
        list(pull_status.pages(Forge(), "jobs", "jobs"))
