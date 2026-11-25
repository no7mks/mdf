"""GitHub 和 GitLab 的 PR/MR、review 与 CI 快照。"""
from collections import Counter
import re
from urllib.parse import urlencode, urlsplit

from mdf_core.foundation.errors import MDFError


INTEGRATION_GATE_BOT = "integration-gate[bot]"
INTEGRATION_GATE_PUSH_SKIPS = {"Prepare Workspace", "matrix.job_id || 'Checks'", "build", "summary"}


def pages(forge, endpoint, key=None, **query):
    page = 1
    while True:
        raw = forge.api(f"{endpoint}?{urlencode(dict(query, per_page=100, page=page))}")
        rows = raw.get(key) if key and isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            raise MDFError("平台未返回完整的分页列表", code="forge_invalid_response")
        yield from rows
        if len(rows) < 100:
            if isinstance(raw, dict) and raw.get("total_count", 0) > (page - 1) * 100 + len(rows):
                raise MDFError("平台分页未覆盖全部结果", code="forge_invalid_response")
            return
        page += 1


def github_check(item, kind, *, url=None, attempt=None):
    status = item["status"]
    conclusion = item.get("conclusion") if status == "completed" else None
    if status == "completed" and not conclusion:
        raise MDFError("已结束的 GitHub 检查缺少 conclusion", code="forge_invalid_response")
    return {"kind": kind, "id": item.get("id", item.get("number")), "name": item.get("name"),
            "url": item.get("html_url") or item.get("details_url") or url, "status": status, "conclusion": conclusion,
            "attempt": attempt, "head": item.get("head_sha")}


def github_jobs(forge, run_endpoint, attempt, *, completed):
    newer_names = Counter()
    oldest = 1 if completed else attempt
    for number in range(attempt, oldest - 1, -1):
        jobs = list(pages(forge, f"{run_endpoint}/attempts/{number}/jobs", "jobs"))
        names = Counter(job["name"] for job in jobs)
        for job in jobs:
            name = job["name"]
            if name in newer_names:
                if names[name] != 1 or newer_names[name] != 1:
                    raise MDFError("无法按 job 名称归并 GitHub 部分重跑", code="forge_invalid_response")
            else:
                yield job, number
        newer_names = names | newer_names


def add_github_run(runs, run):
    run_id, attempt = run["id"], run["run_attempt"]
    if type(run_id) is not int or run_id <= 0 or type(attempt) is not int or attempt <= 0:
        raise MDFError("GitHub run 缺少有效 ID 或 attempt", code="forge_invalid_response")
    if run_id in runs:
        fields = ("run_attempt", "status", "conclusion", "check_suite_id", "head_sha")
        if any(runs[run_id].get(field) != run.get(field) for field in fields):
            raise MDFError("同一 GitHub run 的查询结果不一致", code="forge_invalid_response")
    runs[run_id] = run


def github_run_from_check(forge, project, runs_endpoint, item):
    # Actions 的 check 可能已可见，run 列表尚未更新，或 run 使用了不同的 head SHA。
    details = urlsplit(item.get("details_url") or "")
    path = re.fullmatch(re.escape("/" + project.removeprefix("repos/")) + r"/actions/runs/([0-9]+)(?:/job/[0-9]+)?",
                        details.path, re.IGNORECASE)
    if not path:
        raise MDFError("GitHub Actions check 缺少关联 run 证据", code="forge_invalid_response")
    run_id = int(path[1])
    run = forge.api(f"{runs_endpoint}/{run_id}")
    if run["id"] != run_id or run["check_suite_id"] != item["check_suite"]["id"]:
        raise MDFError("GitHub Actions check 与 run 的身份不一致", code="forge_invalid_response")
    return run


def github_run_matches_pull(pulls, number, head):
    return any(pr["number"] == number and pr["head"]["sha"] == head for pr in pulls)


def github_merge_run_belongs(run, raw, tracked_ids):
    head = raw["head"]["sha"]
    pulls = run.get("pull_requests", ())
    if (run["id"] in tracked_ids or run.get("head_sha") == head
            or (run.get("event") == "push" and run.get("head_sha") == raw["merge_commit_sha"])
            or github_run_matches_pull(pulls, raw["number"], head)):
        return True
    # A merge workflow can start on the old base SHA and finish after the merge.
    merged_at = raw.get("merged_at")
    created_at, updated_at = run.get("created_at"), run.get("updated_at")
    return bool(not pulls and merged_at and created_at and updated_at and created_at < merged_at <= updated_at)


def github_verified_gate_push(run, pull, checks):
    merge = pull.get("merge_commit_sha")
    return (
        pull.get("merged") is True and bool(merge)
        and (pull.get("merged_by") or {}).get("login") == INTEGRATION_GATE_BOT
        and run.get("event") == "push" and run["status"] == "completed" and run.get("conclusion") == "success"
        and run.get("head_sha") == merge and run.get("head_branch") == pull["base"]["ref"]
        and (run.get("actor") or {}).get("login") == INTEGRATION_GATE_BOT
        and run.get("path") == ".github/workflows/integration-gate-checks.yml"
        and any(check["kind"] == "commit_status" and check["head"] == merge
                and check["name"] == "integration-gate/verified-merge" and check["conclusion"] == "success" for check in checks)
    )


def github_status(forge, endpoint, raw, origin_runs, known_runs=()):
    number, head = raw["number"], raw["head"]["sha"]
    project = forge.endpoint.removesuffix("/pulls")
    reviews = {}
    for review in pages(forge, f"{endpoint}/reviews"):
        if review["state"] in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            reviews[review["user"]["login"]] = {
                "id": review["id"], "state": review["state"], "head": review.get("commit_id"),
                "url": review.get("html_url"),
            }
    runs_endpoint = f"{project}/actions/runs"
    heads = [head]
    if ((raw.get("merged_at") or raw.get("merged") or raw.get("mergeable") is True)
            and raw.get("merge_commit_sha") and raw["merge_commit_sha"] != head):
        heads.append(raw["merge_commit_sha"])
    known_ids = {run_id for kind, _, run_id in known_runs if kind == "workflow"}
    origin_ids = set(origin_runs)
    tracked_ids = origin_ids | known_ids
    runs, excluded_suites = {}, set()
    for sha in heads:
        for run in pages(forge, runs_endpoint, "workflow_runs", head_sha=sha):
            if sha == head or github_merge_run_belongs(run, raw, tracked_ids):
                add_github_run(runs, run)
            else:
                excluded_suites.add(run["check_suite_id"])
    for event in ("pull_request", "pull_request_target"):
        for run in pages(forge, runs_endpoint, "workflow_runs", event=event, branch=raw["head"]["ref"],
                         created=f'>={raw["created_at"]}'):
            if github_run_matches_pull(run["pull_requests"], number, head):
                add_github_run(runs, run)
    for run_id in sorted(origin_ids | (known_ids - runs.keys())):
        run = forge.api(f"{runs_endpoint}/{run_id}")
        if run["id"] != run_id:
            raise MDFError("GitHub 未返回指定的 run", code="forge_invalid_response")
        add_github_run(runs, run)
    checks = []
    workflow_suites = {run["check_suite_id"] for run in runs.values()}
    for sha in heads:
        commit = f"{project}/commits/{sha}"
        commit_checks = []
        for item in pages(forge, f"{commit}/check-runs", "check_runs"):
            suite = (item.get("check_suite") or {}).get("id")
            commit_checks.append((suite, item))
            if suite in workflow_suites or (sha != head and suite in excluded_suites):
                continue
            if (item.get("app") or {}).get("slug") != "github-actions":
                continue
            run = github_run_from_check(forge, project, runs_endpoint, item)
            if sha != head and not github_merge_run_belongs(run, raw, tracked_ids):
                excluded_suites.add(suite)
                continue
            add_github_run(runs, run)
            workflow_suites.add(suite)
        # Resolve suite ownership before emitting any checks, regardless of page order.
        for suite, item in commit_checks:
            if sha != head and suite in excluded_suites and suite not in workflow_suites:
                continue
            if suite not in workflow_suites or item["status"] != "completed":
                checks.append(github_check(item, "check"))
        for item in pages(forge, f"{commit}/status", "statuses"):
            status = item["state"]
            checks.append({"kind": "commit_status", "id": item["id"], "name": item["context"],
                           "url": item.get("target_url"), "status": status, "head": sha,
                           "conclusion": None if status == "pending" else status})
    if (raw.get("merged_by") or {}).get("login") == "github-actions[bot]":
        merged_at = raw.get("merged_at")
        if not merged_at or not any(run["created_at"] <= merged_at <= run["updated_at"] for run in runs.values()):
            raise MDFError("GitHub Actions 已执行合并，但尚无关联 run 证据", code="forge_invalid_response")
    for run_id, run in sorted(runs.items()):
        attempt = run["run_attempt"]
        checks.append({**github_check(run, "workflow", attempt=attempt), "event": run.get("event")})
        jobs = list(github_jobs(forge, f"{runs_endpoint}/{run_id}", attempt, completed=run["status"] == "completed"))
        expected_gate_skips = github_verified_gate_push(run, raw, checks) and any(
            job["name"] == "ig-entry" and job["status"] == "completed" and job.get("conclusion") == "success" for job, _ in jobs
        )
        for job, job_attempt in jobs:
            job_check = {**github_check(job, "job", attempt=job_attempt), "run_id": run_id}
            if expected_gate_skips and job_check["conclusion"] == "skipped" and job["name"] in INTEGRATION_GATE_PUSH_SKIPS:
                job_check["expected_skip"] = True
            checks.append(job_check)
            for step in job.get("steps", []):
                check = github_check(step, "step", url=job.get("html_url"), attempt=job_attempt)
                check.update(job_id=job["id"], run_id=run_id)
                if check["conclusion"] == "skipped":
                    check["conclusion"] = None if job["status"] != "completed" else job["conclusion"]
                checks.append(check)
    changes = [str(review["id"]) for review in reviews.values() if review["state"] == "CHANGES_REQUESTED"]
    return {"checks": checks, "reviews": reviews, "change_requests": changes,
            "conflicts": raw.get("mergeable") is False}


def gitlab_check(item, kind):
    status = item["status"]
    active = {"created", "waiting_for_resource", "preparing", "pending", "running", "scheduled",
              "waiting_for_callback", "canceling"}
    conclusion = None if status in active else status
    if status == "failed" and item.get("allow_failure"):
        conclusion = "success"
    if status == "manual":
        conclusion = "skipped" if item.get("allow_failure") else None
    return {"kind": kind, "id": item["id"], "name": item.get("name"), "url": item.get("web_url"),
            "status": status, "conclusion": conclusion, "head": item.get("sha")}


def gitlab_status(forge, endpoint, raw, origin_runs, known_runs=()):
    project = raw["target_project_id"]
    pipelines_endpoint = f"{forge.endpoint.removesuffix('/merge_requests')}/pipelines"
    head = raw["sha"]
    head_pipeline = raw.get("head_pipeline") or {}
    mr_heads = {head, head_pipeline.get("sha")} - {None}
    ids = {item["id"] for item in pages(forge, f"{endpoint}/pipelines") if item["sha"] in mr_heads}
    ids.update(item["id"] for item in pages(forge, pipelines_endpoint, sha=head))
    if raw["state"] == "merged" and raw.get("merge_commit_sha") and raw["merge_commit_sha"] != head:
        ids.update(item["id"] for item in pages(forge, pipelines_endpoint, sha=raw["merge_commit_sha"]))
    ids.update(origin_runs)
    if head_pipeline:
        ids.add(head_pipeline["id"])
    pending = {(project, pipeline_id) for pipeline_id in ids}
    pending.update((owner, pipeline_id) for kind, owner, pipeline_id in known_runs if kind == "pipeline")
    seen, checks = set(), []
    while pending:
        owner, pipeline_id = min(pending)
        pending.remove((owner, pipeline_id))
        seen.add((owner, pipeline_id))
        pipeline = f"projects/{owner}/pipelines/{pipeline_id}"
        item = forge.api(pipeline)
        if item["id"] != pipeline_id:
            raise MDFError("GitLab 未返回指定的 pipeline", code="forge_invalid_response")
        checks.append({**gitlab_check(item, "pipeline"), "project_id": owner})
        for job in pages(forge, f"{pipeline}/jobs"):
            checks.append({**gitlab_check(job, "job"), "project_id": owner, "pipeline_id": pipeline_id})
        for bridge in pages(forge, f"{pipeline}/bridges"):
            checks.append({**gitlab_check(bridge, "bridge"), "project_id": owner, "pipeline_id": pipeline_id})
            downstream = bridge.get("downstream_pipeline")
            if downstream:
                key = (downstream.get("project_id") or owner, downstream["id"])
                if key not in seen:
                    pending.add(key)
    status = raw["detailed_merge_status"]
    reviewers = list(pages(forge, f"{endpoint}/reviewers"))
    requesting = {row["user"]["id"] for row in reviewers if row["state"] == "requested_changes"}
    changes = {}
    if requesting:
        for note in pages(forge, f"{endpoint}/notes", sort="desc"):
            if note.get("system") and note.get("body") == "requested changes":
                reviewer = note["author"]["id"]
                if reviewer in requesting:
                    changes.setdefault(reviewer, str(note["id"]))
    incomplete = bool(requesting - changes.keys()) or (status == "requested_changes" and not changes)
    return {"checks": checks, "reviews": {"status": status, "reviewers": reviewers},
            "change_requests": sorted(changes.values()), "review_identity_unknown": incomplete,
            "conflicts": raw.get("has_conflicts") is True or status == "conflict"}


def pull_status(forge, number, origin_runs, known_runs=()):
    endpoint = f"{forge.endpoint}/{number}"
    raw = forge.api(endpoint)
    try:
        pull = forge.normalize(raw)
        if pull["state"] == "closed":
            return {"pull_request": pull}
        get_status = github_status if forge.github else gitlab_status
        return {"pull_request": pull, **get_status(forge, endpoint, raw, origin_runs, known_runs)}
    except (KeyError, TypeError, AttributeError) as exc:
        raise MDFError("平台状态响应缺少必要字段", code="forge_invalid_response") from exc
