"""PR watch 的离线平台快照与退出条件。"""
import json

import pytest

from mdf_core.foundation.errors import MDFError
from mdf_core.integrations import pull_status
from mdf_core.lifecycle import pull_watch


MERGED = {"id": 1, "state": "merged", "source": "adhoc/docs", "target": "master", "head": "a" * 40, "merge_commit": "b" * 40}


@pytest.fixture
def merged_watch(monkeypatch, tmp_path):
    sleeps = []
    verified = []
    monkeypatch.setattr(pull_watch, "lookup_pull", lambda *args, **kwargs: (MERGED, MERGED["target"]))
    monkeypatch.setattr(pull_watch, "sleep", sleeps.append)
    monkeypatch.setattr(pull_watch, "git", lambda *args: None)
    monkeypatch.setattr(pull_watch, "verified_merge", lambda *args: verified.append(args[1]["merge_commit"]))
    report = tmp_path / "polls.jsonl"

    def run(*snapshots, initially_open=False):
        sequence = iter(snapshots)
        first = True

        def status(*_):
            nonlocal first
            checks = next(sequence)
            if isinstance(checks, MDFError):
                raise checks
            if initially_open and first:
                first = False
                return {"pull_request": {**MERGED, "state": "open"}, "checks": checks, "change_requests": [], "conflicts": False}
            return {"pull_request": MERGED, "checks": checks}

        monkeypatch.setattr(pull_watch, "pull_status", status)
        result = pull_watch.watch(tmp_path, MERGED["source"], None, [], False, report=report)
        assert list(sequence) == []
        return result["status"], sleeps, verified, [json.loads(line) for line in report.read_text().splitlines()]

    return run


def test_watch_immediately_rechecks_passing_merge(merged_watch):
    checks = [{"id": 1, "conclusion": "success"}, {"id": 2, "conclusion": "success"}]
    status, sleeps, verified, _ = merged_watch(checks, list(reversed(checks)))
    assert status == "merged"
    assert sleeps == []
    assert verified == [MERGED["merge_commit"]]


@pytest.mark.parametrize("conclusion, expected", [("success", "merged"), ("failure", "ci_failed")])
def test_watch_waits_for_merge_workflow(merged_watch, conclusion, expected):
    pending = [{"id": 9, "kind": "workflow", "head": "base", "conclusion": None}]
    finished = [{**pending[0], "conclusion": conclusion}]
    status, sleeps, _, _ = merged_watch(pending, finished, *([finished] if expected == "merged" else []))
    assert status == expected
    assert sleeps == [120]


@pytest.mark.parametrize("run_id, attempt, conclusion", [(10, 1, None), (9, 2, None), (9, 2, "success")])
def test_watch_restarts_after_new_run_or_attempt(merged_watch, run_id, attempt, conclusion):
    passing = [{"id": 9, "attempt": 1, "conclusion": "success"}]
    changed = [{"id": run_id, "attempt": attempt, "conclusion": conclusion}]
    if run_id == 10:
        changed = passing + changed
    finished = [dict(item, conclusion="success") for item in changed]
    status, sleeps, verified, _ = merged_watch(passing, changed, finished, finished)
    assert status == "merged"
    assert sleeps == [120]
    assert verified == [MERGED["merge_commit"]] * 2


@pytest.mark.parametrize("code", ["forge_failed", "forge_invalid_response"])
def test_watch_retries_uncertain_recheck_even_without_visible_ci(merged_watch, code):
    status, sleeps, verified, polls = merged_watch([], MDFError("查询不完整", code=code), [], [])
    assert status == "merged"
    assert sleeps == [120]
    assert verified == [MERGED["merge_commit"]] * 2
    assert polls[1]["code"] == code


@pytest.mark.parametrize("initially_open", [False, True])
def test_watch_waits_when_a_previously_associated_run_disappears(merged_watch, initially_open):
    checks = [{"kind": "workflow", "id": 9, "conclusion": "success"}]
    first = [{**checks[0], "conclusion": None}] if initially_open else checks
    status, sleeps, _, polls = merged_watch(first, [], [], checks, checks, initially_open=initially_open)
    assert status == "merged"
    assert sleeps == [120] * (3 if initially_open else 2)
    assert sum(poll.get("code") == "forge_invalid_response" for poll in polls) == 2


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


@pytest.mark.parametrize("explicit_origin", [True, False])
def test_github_snapshot_directly_queries_origin_or_previously_seen_run(monkeypatch, explicit_origin):
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
    origins, known = ([9], []) if explicit_origin else ([], [("workflow", None, 9)])
    result = pull_status.github_status(Forge(), "repos/team/project/pulls/1", raw, origins, known)
    assert [check["kind"] for check in result["checks"]] == ["workflow", "job", "step", "job"]
    assert [check["attempt"] for check in result["checks"]] == [2, 2, 2, 1]
    assert result["checks"][-1]["conclusion"] == "skipped"
    assert result["checks"][0]["head"] == "base"
    assert result["checks"][2]["job_id"] == 3


@pytest.mark.parametrize("use_known_pipeline", [False, True])
def test_gitlab_snapshot_waits_for_child_pipeline(monkeypatch, use_known_pipeline):
    class Forge:
        endpoint = "projects/team%2Fproject/merge_requests"

        def api(self, endpoint):
            if endpoint == "projects/2/pipelines/9":
                return dict(id=9, status="success", sha="tip")
            assert endpoint == "projects/3/pipelines/10"
            return dict(id=10, status="waiting_for_callback", sha="child")

    def pages(forge, endpoint, key=None, **query):
        if not use_known_pipeline and endpoint == "projects/2/pipelines/9/bridges":
            return [dict(id=5, status="success", downstream_pipeline=dict(project_id=3, id=10))]
        return []

    monkeypatch.setattr(pull_status, "pages", pages)
    raw = dict(target_project_id=2, state="opened", sha="tip", head_pipeline=dict(id=9),
               detailed_merge_status="ci_still_running")
    known = [("pipeline", 3, 10)] if use_known_pipeline else []
    checks = pull_status.gitlab_status(Forge(), "projects/team%2Fproject/merge_requests/1", raw, [], known)["checks"]
    assert [check["project_id"] for check in checks] == ([2, 3] if use_known_pipeline else [2, 2, 3])
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


@pytest.mark.parametrize("visible_link", [True, False])
def test_github_check_links_to_merge_workflow_on_another_sha(monkeypatch, visible_link):
    class Forge:
        endpoint = "repos/team/project/pulls"

        def api(self, endpoint):
            assert endpoint == "repos/team/project/actions/runs/42"
            return dict(id=42, name="Auto-merge", head_sha="base", run_attempt=1, status="in_progress", check_suite_id=8)

    def pages(forge, endpoint, key=None, **query):
        if endpoint.endswith("/commits/merged/check-runs"):
            return [dict(id=7, status="completed", conclusion="success", app=dict(slug="github-actions"),
                         check_suite=dict(id=8), details_url="https://forge.invalid/team/project/actions/runs/42/job/7"
                         if visible_link else None)]
        return []

    monkeypatch.setattr(pull_status, "pages", pages)
    raw = dict(number=1, head=dict(sha="tip", ref="adhoc/docs"), created_at="2026-11-14T00:00:00Z",
               merged=True, merge_commit_sha="merged")
    if not visible_link:
        with pytest.raises(MDFError, match="缺少关联 run 证据"):
            pull_status.github_status(Forge(), "repos/team/project/pulls/1", raw, [])
        return
    checks = pull_status.github_status(Forge(), "repos/team/project/pulls/1", raw, [])["checks"]
    assert [(check["id"], check["head"], check["conclusion"]) for check in checks] == [(42, "base", None)]


@pytest.mark.parametrize("has_earlier_ci", [False, True])
def test_github_actions_merge_without_visible_merge_run_has_incomplete_evidence(monkeypatch, has_earlier_ci):
    class Forge:
        endpoint = "repos/team/project/pulls"

    def pages(forge, endpoint, key=None, **query):
        if has_earlier_ci and query.get("head_sha") == "tip":
            return [dict(id=9, run_attempt=1, check_suite_id=8, created_at="2026-11-14T00:01:00Z",
                         updated_at="2026-11-14T00:02:00Z")]
        return []

    monkeypatch.setattr(pull_status, "pages", pages)
    raw = dict(number=1, head=dict(sha="tip", ref="adhoc/docs"), created_at="2026-11-14T00:00:00Z",
               merged_at="2026-11-14T00:03:00Z", merge_commit_sha="merged", merged_by=dict(login="github-actions[bot]"))
    with pytest.raises(MDFError, match="尚无关联 run 证据"):
        pull_status.github_status(Forge(), "repos/team/project/pulls/1", raw, [])


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
