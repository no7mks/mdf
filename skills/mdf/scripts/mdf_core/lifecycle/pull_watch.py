"""轮询 PR/MR、核验合并历史并返回返工证据。"""
import json
import re
from time import sleep

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.integrations.pull_status import pull_status
from mdf_core.lifecycle.pull_finish import Forge, confirm_pull, lookup_pull, origin, verified_merge
from mdf_core.workspace.gitutil import current_branch, repo_path, require_git_root
from mdf_core.workspace.merge_policy import configured, git


def record_poll(report, result):
    if report is not None:
        with report.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")


def watch(repo, source, forge, origin_runs, allow_skipped, *, number=None, expected_head=None, handled_reviews=(), report=None):
    accepted = {"success"} | ({"skipped", "neutral"} if allow_skipped else set())
    handled = set(handled_reviews)
    if expected_head is not None and re.fullmatch(r"[0-9a-f]{40}", expected_head) is None:
        raise MDFError("--head 需要完整 commit SHA", code="invalid_arguments")
    target = previous = None
    associated_runs = set()
    while True:
        try:
            if target is None:
                pull, target = lookup_pull(repo, forge, source, number=number)
                if pull is None:
                    raise MDFError("先用 pr 创建 PR/MR，再开始轮询", code="pull_not_recorded")
                number = pull["id"]
                expected_head = expected_head or pull["head"]
                confirm_pull(pull, source, target, expected_head)
            snapshot = pull_status(forge, number, origin_runs, associated_runs)
        except MDFError as exc:
            if exc.code not in {"forge_failed", "forge_invalid_response"}:
                raise
            record_poll(report, {"source": source, "error": str(exc), "code": exc.code})
            previous = None
            sleep(120)
            continue
        pull = snapshot["pull_request"]
        if (pull["id"] != number or pull["source"] != source or pull["target"] != target
                or pull["state"] not in {"open", "closed", "merged"}):
            raise MDFError("无法确认 PR/MR 身份或状态", code="forge_invalid_response")
        confirm_pull(pull, source, target, expected_head)
        result = {"source": source, **snapshot}
        record_poll(report, result)
        if pull["state"] == "closed":
            return {**result, "status": "closed_without_merge"}

        checks = snapshot["checks"]
        failures = [item for item in checks if item["conclusion"] is not None and item["conclusion"] not in accepted]
        if failures:
            return {**result, "status": "ci_failed", "failures": failures}
        if pull["state"] == "open" and (snapshot.get("review_identity_unknown")
                                      or any(review not in handled for review in snapshot["change_requests"])):
            return {**result, "status": "changes_requested"}
        if pull["state"] == "open" and snapshot["conflicts"]:
            return {**result, "status": "merge_conflict"}
        runs = {(item["kind"], item.get("project_id"), item["id"])
                for item in checks if item.get("kind") in {"workflow", "pipeline"}}
        missing_runs = not associated_runs <= runs
        if missing_runs:
            record_poll(report, {"source": source, "code": "forge_invalid_response", "error": "此前已关联的运行未出现在查询结果中"})
        associated_runs.update(runs)
        if pull["state"] == "merged" and not missing_runs and all(item["conclusion"] in accepted for item in checks):
            merged = pull.get("merge_commit")
            if isinstance(merged, str) and re.fullmatch(r"[0-9a-f]{40}", merged):
                # Ignore pagination order. Compare run IDs, attempts and CI status along with the PR identity.
                evidence = (pull, sorted(json.dumps(check, sort_keys=True) for check in checks))
                if evidence == previous:
                    return {**result, "status": "merged"}
                if previous is None:
                    try:
                        git(repo, "fetch", "--no-tags", "--no-write-fetch-head", "--no-recurse-submodules", "--refmap=",
                            "origin", f"+refs/heads/{target}:refs/remotes/origin/{target}")
                        verified_merge(repo, pull, source, target, expected_head)
                    except MDFError as exc:
                        if exc.code != "command_failed":
                            raise
                        record_poll(report, {"source": source, "error": str(exc), "code": exc.code})
                    else:
                        previous = evidence
                        continue
            else:
                record_poll(report, {"source": source, "code": "forge_invalid_response", "error": "缺少有效的 merge commit SHA"})
        previous = None
        sleep(120)


def command_pr_watch(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    settings = configured(repo)
    if settings["mode"] != "pr":
        raise MDFError("pr-watch 仅适用于 PR mode", code="invalid_closeout")
    if any(run_id <= 0 for run_id in args.origin_run):
        raise MDFError("--origin-run 需要正整数 ID", code="invalid_run_id")
    identity = origin(repo, settings["provider"])
    source = args.source or current_branch(repo)
    try:
        result = watch(repo, source, Forge(repo, identity), args.origin_run, args.allow_skipped,
                       number=args.pull, expected_head=args.head, handled_reviews=args.handled_review, report=args.log_path / "polls.jsonl")
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    emit({"ok": True, "operation": "pr-watch", **result})
