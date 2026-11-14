"""GitHub 和 GitLab 的 PR/MR、review 与 CI 快照。"""
from collections import Counter
from urllib.parse import urlencode

from mdf_core.foundation.errors import MDFError


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


def github_status(forge, endpoint, raw, origin_runs):
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
    if ((raw.get("merged_at") or raw.get("mergeable") is True)
            and raw.get("merge_commit_sha") and raw["merge_commit_sha"] != head):
        heads.append(raw["merge_commit_sha"])
    runs = {run["id"]: run for sha in heads for run in pages(forge, runs_endpoint, "workflow_runs", head_sha=sha)}
    for event in ("pull_request", "pull_request_target"):
        for run in pages(forge, runs_endpoint, "workflow_runs", event=event, branch=raw["head"]["ref"],
                         created=f'>={raw["created_at"]}'):
            if any(pr["number"] == number and pr["head"]["sha"] == head for pr in run["pull_requests"]):
                runs[run["id"]] = run
    for run_id in origin_runs:
        runs[run_id] = forge.api(f"{runs_endpoint}/{run_id}")
    checks = []
    for run_id, run in sorted(runs.items()):
        attempt = run["run_attempt"]
        checks.append(github_check(run, "workflow", attempt=attempt))
        for job, job_attempt in github_jobs(forge, f"{runs_endpoint}/{run_id}", attempt,
                                            completed=run["status"] == "completed"):
            checks.append({**github_check(job, "job", attempt=job_attempt), "run_id": run_id})
            for step in job.get("steps", []):
                check = github_check(step, "step", url=job.get("html_url"), attempt=job_attempt)
                check.update(job_id=job["id"], run_id=run_id)
                if check["conclusion"] == "skipped":
                    check["conclusion"] = None if job["status"] != "completed" else job["conclusion"]
                checks.append(check)
    workflow_suites = {run["check_suite_id"] for run in runs.values()}
    for sha in heads:
        commit = f"{project}/commits/{sha}"
        for item in pages(forge, f"{commit}/check-runs", "check_runs"):
            if (item.get("check_suite") or {}).get("id") not in workflow_suites:
                checks.append(github_check(item, "check"))
        for item in pages(forge, f"{commit}/status", "statuses"):
            status = item["state"]
            checks.append({"kind": "commit_status", "id": item["id"], "name": item["context"],
                           "url": item.get("target_url"), "status": status, "head": sha,
                           "conclusion": None if status == "pending" else status})
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


def gitlab_status(forge, endpoint, raw, origin_runs):
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
    seen, checks = set(), []
    while pending:
        owner, pipeline_id = min(pending)
        pending.remove((owner, pipeline_id))
        seen.add((owner, pipeline_id))
        pipeline = f"projects/{owner}/pipelines/{pipeline_id}"
        checks.append({**gitlab_check(forge.api(pipeline), "pipeline"), "project_id": owner})
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


def pull_status(forge, number, origin_runs):
    endpoint = f"{forge.endpoint}/{number}"
    raw = forge.api(endpoint)
    try:
        pull = forge.normalize(raw)
        if pull["state"] == "closed":
            return {"pull_request": pull}
        get_status = github_status if forge.github else gitlab_status
        return {"pull_request": pull, **get_status(forge, endpoint, raw, origin_runs)}
    except (KeyError, TypeError, AttributeError) as exc:
        raise MDFError("平台状态响应缺少必要字段", code="forge_invalid_response") from exc
