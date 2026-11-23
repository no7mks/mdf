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


@pytest.mark.parametrize("dispatch_conclusion", ["success", "failure", "skipped"])
def test_watch_accepts_skipped_entry_jobs_and_waits_for_dispatch(monkeypatch, tmp_path, dispatch_conclusion):
    pulls_endpoint = "repos/team/project/pulls"
    runs_endpoint = "repos/team/project/actions/runs"
    raw = dict(number=1, head=dict(sha=MERGED["head"], ref=MERGED["source"]), created_at="2026-11-14T00:00:00Z")
    entry = dict(id=10, event="pull_request_target", head_sha="workflow-ref", pull_requests=[raw],
                 run_attempt=1, check_suite_id=10, status="completed", conclusion="success")
    dispatch_results = iter([None, dispatch_conclusion, dispatch_conclusion])
    dispatch = dict(id=11, event="workflow_dispatch", head_sha="workflow-ref", run_attempt=1, check_suite_id=11)
    entry_jobs = ["Prepare Workspace", "Checks", "build", "summary"]

    class Forge:
        github = True
        endpoint = pulls_endpoint

        def api(self, path):
            if path == f"{pulls_endpoint}/1":
                return raw
            assert path == f"{runs_endpoint}/11"
            conclusion = next(dispatch_results)
            dispatch.update(status="in_progress" if conclusion is None else "completed", conclusion=conclusion)
            return dispatch

        def normalize(self, response):
            assert response == raw
            return MERGED

    def pages(forge, path, key=None, **query):
        if path == runs_endpoint and query.get("event") == "pull_request_target":
            return [entry]
        if path == f"{runs_endpoint}/10/attempts/1/jobs":
            return [dict(id=job_id, name=name, status="completed", conclusion="skipped", steps=[
                dict(name="conditional", number=1, status="completed", conclusion="skipped")])
                for job_id, name in enumerate(entry_jobs, 20)]
        if path == f"{runs_endpoint}/11/attempts/1/jobs":
            return [dict(id=24, name="build", status=dispatch["status"], conclusion=dispatch["conclusion"])]
        return []

    sleeps = []
    monkeypatch.setattr(pull_status, "pages", pages)
    monkeypatch.setattr(pull_watch, "lookup_pull", lambda *args, **kwargs: (MERGED, MERGED["target"]))
    monkeypatch.setattr(pull_watch, "sleep", sleeps.append)
    monkeypatch.setattr(pull_watch, "git", lambda *args: None)
    monkeypatch.setattr(pull_watch, "verified_merge", lambda *args: None)

    result = pull_watch.watch(tmp_path, MERGED["source"], Forge(), [11], False)
    assert result["status"] == ("merged" if dispatch_conclusion == "success" else "ci_failed")
    assert sleeps == [120]
    assert [check["name"] for check in result["checks"]
            if check["kind"] == "job" and check["run_id"] == 10 and check["conclusion"] == "skipped"] == entry_jobs
    if dispatch_conclusion != "success":
        assert [(check["kind"], check["id"]) for check in result["failures"]] == [("workflow", 11), ("job", 24)]


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


@pytest.fixture
def github_gate_snapshot(monkeypatch):
    pulls_endpoint = "repos/team/project/pulls"
    runs_endpoint = "repos/team/project/actions/runs"
    merged_at = "2026-11-14T00:03:00Z"

    def make_forge(event, conclusion, listed, *, actions_check_first=True, merged=True):
        raw = dict(number=1, head=dict(sha=MERGED["head"], ref=MERGED["source"]), created_at="2026-11-14T00:00:00Z",
                   merged=merged, mergeable=True, merged_at=merged_at if merged else None, merge_commit_sha=MERGED["merge_commit"],
                   merged_by=dict(login="github-actions[bot]") if merged else None)

        def run(run_id, event, *, created_at=merged_at, conclusion="success", pull_requests=()):
            return dict(id=run_id, event=event, head_sha=MERGED["merge_commit"], check_suite_id=run_id, run_attempt=1,
                        status="completed" if conclusion else "in_progress", conclusion=conclusion, created_at=created_at,
                        updated_at="2026-11-14T00:06:00Z", pull_requests=pull_requests)

        runs = {
            10: dict(run(10, "workflow_dispatch", created_at="2026-11-14T00:01:00Z"), head_sha="base"),
            11: run(11, "push"),
            12: run(12, event, created_at="2026-11-14T00:04:00Z", conclusion=conclusion),
            13: run(13, "workflow_dispatch", pull_requests=[dict(number=1, head=dict(sha=MERGED["head"]))]),
            14: run(14, "repository_dispatch"),
        }
        queried_jobs = []

        class Forge:
            github = True
            endpoint = pulls_endpoint

            def api(self, path):
                if path == f"{pulls_endpoint}/1":
                    return raw
                prefix, run_id = path.rsplit("/", 1)
                assert prefix == runs_endpoint
                return runs[int(run_id)]

            def normalize(self, response):
                assert response == raw
                return MERGED if merged else {**MERGED, "state": "open", "merge_commit": None}

        def pages(forge, path, key=None, **query):
            if path == runs_endpoint and query.get("head_sha") == MERGED["merge_commit"]:
                return [runs[11], runs[13], runs[14], *([runs[12]] if listed else [])]
            if path.endswith(f'/commits/{MERGED["merge_commit"]}/check-runs'):
                check_ids = [20, 21] if actions_check_first else [21, 20]
                return [dict(id=check_id, status=runs[run_id]["status"], conclusion=runs[run_id]["conclusion"],
                             app=None if check_id == 21 else dict(slug="github-actions"), check_suite=dict(id=run_id),
                             details_url=f"https://forge.invalid/team/project/actions/runs/{run_id}/job/{check_id}")
                        for check_id, run_id in [(check_ids[0], 12), (check_ids[1], 12), (22, 14)]]
            if key == "jobs":
                run_id = int(path.split("/")[-4])
                queried_jobs.append(run_id)
                return [dict(id=100 + run_id, name="test", status=runs[run_id]["status"], conclusion=runs[run_id]["conclusion"])]
            return []

        monkeypatch.setattr(pull_status, "pages", pages)
        return Forge(), queried_jobs

    return make_forge


@pytest.mark.parametrize("event, listed, actions_check_first", [
    ("workflow_dispatch", True, True), ("workflow_dispatch", False, True),
    ("workflow_dispatch", False, False), ("schedule", True, True),
])
def test_github_snapshot_excludes_unrelated_merge_commit_runs(github_gate_snapshot, event, listed, actions_check_first):
    forge, queried_jobs = github_gate_snapshot(event, None, listed, actions_check_first=actions_check_first)
    snapshot = pull_status.pull_status(forge, 1, [10], [("workflow", None, 14)])
    assert [(check["kind"], check["id"]) for check in snapshot["checks"]] == [
        (kind, run_id + offset) for run_id in (10, 11, 13, 14) for kind, offset in (("workflow", 0), ("job", 100))
    ]
    assert queried_jobs == [10, 11, 13, 14]


def test_github_open_pr_keeps_associated_check_runs_on_test_merge_sha(github_gate_snapshot):
    forge, queried_jobs = github_gate_snapshot("workflow_dispatch", "failure", False, actions_check_first=False, merged=False)
    snapshot = pull_status.pull_status(forge, 1, [])
    assert [(check["kind"], check["id"]) for check in snapshot["checks"]] == [
        ("workflow", 11), ("job", 111), ("workflow", 13), ("job", 113)
    ]
    assert queried_jobs == [11, 13]


@pytest.mark.parametrize("conclusion, listed, actions_check_first", [
    (None, True, True), ("failure", False, True), (None, False, False), ("failure", False, False),
])
def test_watch_merges_without_waiting_for_next_gate_run(
        monkeypatch, tmp_path, github_gate_snapshot, conclusion, listed, actions_check_first):
    forge, queried_jobs = github_gate_snapshot("workflow_dispatch", conclusion, listed, actions_check_first=actions_check_first)
    monkeypatch.setattr(pull_watch, "lookup_pull", lambda *args, **kwargs: (MERGED, MERGED["target"]))
    monkeypatch.setattr(pull_watch, "git", lambda *args: None)
    monkeypatch.setattr(pull_watch, "verified_merge", lambda *args: None)

    def unexpected_sleep(seconds):
        pytest.fail(f"已合并的 PR 不应等待其他 PR 的 CI（sleep {seconds}s）")

    monkeypatch.setattr(pull_watch, "sleep", unexpected_sleep)
    result = pull_watch.watch(tmp_path, MERGED["source"], forge, [10, 14], False)
    assert result["status"] == "merged"
    assert queried_jobs == [10, 11, 13, 14] * 2


@pytest.mark.parametrize("visible_link", [True, False])
def test_github_check_links_to_merge_workflow_on_another_sha(monkeypatch, visible_link):
    class Forge:
        endpoint = "repos/team/project/pulls"

        def api(self, endpoint):
            assert endpoint == "repos/team/project/actions/runs/42"
            return dict(id=42, name="Auto-merge", head_sha="base", run_attempt=1, status="in_progress", check_suite_id=8,
                        event="workflow_dispatch", created_at="2026-11-14T00:01:00Z", updated_at="2026-11-14T00:04:00Z")

    def pages(forge, endpoint, key=None, **query):
        if endpoint.endswith("/commits/merged/check-runs"):
            return [dict(id=7, status="completed", conclusion="success", app=dict(slug="github-actions"),
                         check_suite=dict(id=8), details_url="https://forge.invalid/team/project/actions/runs/42/job/7"
                         if visible_link else None)]
        return []

    monkeypatch.setattr(pull_status, "pages", pages)
    raw = dict(number=1, head=dict(sha="tip", ref="adhoc/docs"), created_at="2026-11-14T00:00:00Z",
               merged=True, merged_at="2026-11-14T00:03:00Z", merge_commit_sha="merged")
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
