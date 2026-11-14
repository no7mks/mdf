"""只读轮询已记录的 PR/MR；返回平台状态和返工证据。"""
import json
from time import sleep

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.integrations.pull_status import pull_status
from mdf_core.lifecycle.delivery_state import read_json
from mdf_core.lifecycle.publish import state_path
from mdf_core.lifecycle.pull_finish import Forge, confirm_pull, origin
from mdf_core.workspace.gitutil import current_branch, repo_path, require_git_root
from mdf_core.workspace.merge_policy import configured


def watch(repo, source, forge, identity, origin_runs, allow_skipped, *, handled_reviews=(), report=None):
    accepted = {"success"} | ({"skipped", "neutral"} if allow_skipped else set())
    handled = set(handled_reviews)
    path = state_path(repo, source)
    previous = None
    while True:
        state = read_json(path) if path.is_file() else {}
        if state.get("mode") != "pr" or state.get("identity") != identity or state.get("source") != source:
            raise MDFError("找不到与当前 origin 和 source 匹配的 PR/MR 记录", code="pull_state_changed")
        number = (state.get("pull") or {}).get("id")
        if not number:
            raise MDFError("先用 pr 创建或恢复 PR/MR，再开始轮询", code="pull_not_recorded")
        snapshot = pull_status(forge, number, origin_runs)
        pull = snapshot["pull_request"]
        if pull["id"] != number or pull["state"] not in {"open", "closed", "merged"}:
            raise MDFError("无法确认 PR/MR 状态", code="forge_invalid_response")
        confirm_pull(state, pull)
        result = {"source": source, **snapshot}
        if report is not None:
            with report.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")
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
        if pull["state"] == "merged" and all(item["conclusion"] in accepted for item in checks):
            if snapshot == previous:
                return {**result, "status": "merged"}
            previous = snapshot
        else:
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
        result = watch(repo, source, Forge(repo, identity), identity, args.origin_run, args.allow_skipped,
                       handled_reviews=args.handled_review, report=args.log_path / "polls.jsonl")
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    emit({"ok": True, "operation": "pr-watch", **result})
