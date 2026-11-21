"""delivery route / complete-stage：按 objectives 清单路由，并只自动完成纯证据可判定的阶段。"""
import re

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.delivery_state import git, read_json, safe, split_objectives_steps
from mdf_core.workspace.merge_policy import sha

ITEM = re.compile(r"(?m)^- \[([ xX])\] (.+?)[ \t]*$")
AUTO = ("verify",)


def parse_items(text):
    _, steps, _ = split_objectives_steps(text)
    return [{"checked": mark != " ", "label": label, "name": label.split("（", 1)[0].strip()}
            for mark, label in ITEM.findall(steps)]


def _is(item, stage):
    return item["name"] == stage or item["name"].startswith(stage + " ")


def _objectives(repo, root):
    path = safe(repo, root / "objectives.md")
    return path, path.read_text(encoding="utf-8")


def _verify_evidence(repo, root, data, item):
    path = safe(repo, root / "verification-report.json")
    if not path.is_file():
        return None, ("缺少 verification-report.json", {"missing": "verification-report.json"})
    report = read_json(path)
    expected = {"stage": "verify", "expected_scope": "smart" if item["name"] == "verify smart" else "branch",
                "expected_branch": data["branch"], "actual_scope": report.get("scope"),
                "actual_branch": report.get("branch")}
    if (report.get("all_passed") is not True or report.get("scope") != expected["expected_scope"]
            or report.get("branch") != data["branch"]):
        return None, ("verification-report.json 未声称本分支本 scope 全部通过", expected)
    if report["scope"] == "branch":
        from mdf_core.execution.verification import recorded_suites, required_suites, suites_cover
        from mdf_core.workspace.gitutil import branch_details
        kind = branch_details(data["branch"])["kind"]
        if not suites_cover(recorded_suites(report), required_suites(kind)):
            return None, ("branch 报告未覆盖必选 suite", {**expected, "suites": report.get("suites")})
    else:
        results = report.get("results")
        if (not isinstance(results, list) or not results
                or any(not isinstance(item, dict) or item.get("passed") is False
                       or item.get("exit_code") != 0 for item in results)):
            return None, ("smart 报告需要非空且逐项通过的 results", expected)
    found = {"report": path.relative_to(repo).as_posix()}
    if report["scope"] == "branch":
        summary = safe(repo, root / "verification-report.md")
        if summary.is_file():
            found["summary"] = summary.relative_to(repo).as_posix()
    return found, None


def evidence(repo, root, data, item, stage):
    """返回 (证据, (原因, details))；证据为空表示该阶段不可自动完成。"""
    return _verify_evidence(repo, root, data, item)


def route(repo, root, data, yolo=False):
    _, text = _objectives(repo, root)
    items = parse_items(text)
    pending = [i for i in items if not i["checked"]]
    result = {"pending": [i["name"] for i in pending], "yolo": yolo, "next": None, "auto_completable": False}
    from mdf_core.lifecycle.catchup import pending_attempt
    catchup_index = next((n for n, item in enumerate(items) if item["name"] == "catch-up"), None)
    if (catchup_index is not None and all(item["checked"] for item in items[:catchup_index])
            and pending_attempt(repo, data["branch"])):
        return {**result, "next": "catch-up", "state": "ready",
                "pending": ["catch-up", *[name for name in result["pending"] if name != "catch-up"]]}
    from mdf_core.lifecycle.consolidation import pending_attempt as consolidation_pending
    consolidation_index = next((n for n, item in enumerate(items) if item["name"] == "consolidate"), None)
    if (consolidation_index is not None and all(item["checked"] for item in items[:consolidation_index])
            and consolidation_pending(repo, data["branch"])):
        return {**result, "next": "consolidate", "state": "ready",
                "pending": ["consolidate", *[name for name in result["pending"] if name != "consolidate"]]}
    if not pending:
        return _after_checklist(repo, data, result, yolo)
    head = pending[0]
    result["next"] = head["name"]
    if head["name"] == "design" and not yolo:
        return {**result, "state": "awaiting_design_approval"}
    if head["name"] == "人工工作":
        return {**result, "state": "awaiting_manual_work"}
    if head["name"] in {"pr", "close-out"} and not yolo:
        return {**result, "state": "awaiting_decision_confirmation"}
    stage = next((s for s in AUTO if _is(head, s)), None)
    if stage:
        found, _ = evidence(repo, root, data, head, stage)
        result["auto_completable"] = found is not None
    return {**result, "state": "ready"}


def _after_checklist(repo, root_data, result, yolo):
    """清单完毕后，PR phase 由 Agent 核对平台与关联 CI。"""
    from mdf_core.workspace.merge_policy import configured_delivery

    def gated(nxt):
        confirm = nxt in {"pr", "close-out"} and not yolo
        return {**result, "next": nxt, "state": "awaiting_decision_confirmation" if confirm else "ready"}

    from mdf_core.workspace.workflow_policy import target_for
    from mdf_core.lifecycle.publish import find_merge
    from mdf_core.workspace.gitutil import branch_details
    from mdf_core.workspace.workflow_policy import is_github_flow
    source = root_data["branch"]
    target = target_for(repo, source, data=root_data)
    mode = configured_delivery(repo, source, data=root_data)["mode"]
    target_ref = f"refs/remotes/origin/{target}" if mode == "pr" else f"refs/heads/{target}"
    exists = git(repo, "rev-parse", "--verify", target_ref, check=False).returncode == 0
    merged = find_merge(repo, target_ref, sha(repo, "HEAD")) if exists else None
    if merged is None:
        return gated("pr" if mode == "pr" else "merge")
    details = branch_details(source)
    versioned = details["kind"] in {"release", "hotfix"}
    if versioned and mode == "local":
        from mdf_core.lifecycle.publish import remote_contains_merge
        if not remote_contains_merge(repo, target, merged):
            return gated("merge")
    from mdf_core.lifecycle.support_line import support_hotfix
    if support_hotfix(repo, source, data=root_data):
        return support_completion(repo, source, details["version"] or root_data.get("version"), result, yolo)
    if versioned and not is_github_flow(repo):
        from mdf_core.lifecycle.release_publish import published_head
        try:
            published_head(repo, details["version"] or root_data.get("version"))
        except MDFError:
            return gated("publish")
    return gated("close-out")


def support_completion(repo, source, version, result, yolo):
    from mdf_core.lifecycle.publish import require_support_merge, support_merge_record
    from mdf_core.lifecycle.release_publish import published_head
    receipt = support_merge_record(repo, source, version)
    if not receipt:
        return {**result, "next": "merge", "state": "ready"}
    version, record = receipt
    merged = require_support_merge(repo, record)
    ref = f"refs/tags/v{version}"
    if (not record.get("published") or git(repo, "rev-parse", "--verify", ref, check=False).returncode
            or not git(repo, "ls-remote", "origin", ref).stdout.strip()):
        return {**result, "next": "publish", "state": "ready", "source": source, "version": version}
    if published_head(repo, version) != merged:
        raise MDFError("final tag 与 support merge 不符", code="tag_conflict")
    if record.get("closed"):
        return {**result, "next": None, "state": "completed", "source": source, "version": version}
    from mdf_core.workspace.changelog_sync import require_synced
    try:
        require_synced(repo, version, merged)
    except MDFError as exc:
        if exc.code != "changelog_sync_required":
            raise
        return {**result, "next": "sync-changelog", "state": "ready", "source": source, "version": version}
    if not record.get("closed"):
        return {**result, "next": "close-out", "state": "ready" if yolo else "awaiting_decision_confirmation",
                "source": source, "version": version}
    return {**result, "next": None, "state": "completed", "source": source, "version": version}


def _staged(repo):
    return {p for p in git(repo, "diff", "--cached", "--name-only", "-z").stdout.split("\0") if p}


def _tick(text, item, stage, found):
    label = item["label"]
    step = rf"(?m)^- \[[ xX]\] {re.escape(label)}[ \t]*$"
    checked = f"- [x] {label}"
    before, steps, after = split_objectives_steps(text)
    return before + re.sub(step, lambda _: checked, steps, count=1) + after


def _already_done(repo, rel, text, item, stage):
    if not item["checked"]:
        return False
    if git(repo, "status", "--porcelain", "--", rel).stdout.strip():
        return False
    return True


def _dirty_names(repo):
    raw = git(repo, "status", "--porcelain", "-z").stdout.split("\0")
    names = []
    index = 0
    while index < len(raw):
        entry = raw[index]
        index += 1
        if len(entry) < 4:
            continue
        names.append(entry[3:])
        if "R" in entry[:2]:
            index += 1
    return names


def complete_stage(repo, root, data, stage):
    from mdf_core.workspace.gitutil import current_branch, git_in_progress_head
    if git_in_progress_head(repo):
        raise MDFError("存在未完成的 merge、cherry-pick 或 revert", code="unfinished_merge")
    if current_branch(repo) != data["branch"]:
        raise MDFError("complete-stage 须在 owner worktree 执行", code="not_owner")
    if stage not in AUTO:
        raise MDFError(f"{stage} 不是纯证据可判定的阶段，仅支持 {', '.join(AUTO)}", code="invalid_stage")
    path, text = _objectives(repo, root)
    rel = path.relative_to(repo).as_posix()
    items = parse_items(text)
    item = next((i for i in items if _is(i, stage)), None)
    if item is None:
        raise MDFError(f"objectives 中没有 {stage} 步骤", code="invalid_stage")
    found, reason = evidence(repo, root, data, item, stage)
    if found is None:
        raise MDFError(reason[0], code="stage_evidence_missing", details=reason[1])
    if _already_done(repo, rel, text, item, stage):
        return {"stage": stage, "completed": True, "already_completed": True, "commit": sha(repo, "HEAD")}
    earlier = [i["name"] for i in items[:items.index(item)] if not i["checked"]]
    if earlier:
        raise MDFError(f"{stage} 前置未完成: {', '.join(earlier)}", code="stage_prerequisite",
                       details={"stage": stage, "pending": earlier})
    owned = {rel, *(found[k] for k in ("report", "summary") if k in found)}
    unrelated = sorted(_staged(repo) - owned)
    if unrelated:
        raise MDFError("index 存在本阶段之外的已暂存改动，已保留现场未做任何修改",
                       code="unrelated_staged_changes", details={"paths": unrelated})
    desired = _tick(text, item, stage, found)
    if git(repo, "status", "--porcelain", "--", rel).stdout.strip():
        if path.read_text(encoding="utf-8") != desired:
            raise MDFError("objectives.md 存在未提交改动，不代为提交", code="dirty_stage_files")
    else:
        path.write_text(desired, encoding="utf-8")
    changed = [p for p in sorted(owned) if git(repo, "status", "--porcelain", "--", p).stdout.strip()]
    git(repo, "add", "--", *changed)
    extra = sorted(_staged(repo) - owned)
    if extra:
        git(repo, "reset", "-q", "--", *changed)
        raise MDFError("暂存集超出本阶段白名单", code="unrelated_staged_changes", details={"paths": extra})
    git(repo, "commit", "-q", "-m", f"docs(delivery): 完成 {stage} 阶段", "--", *changed)
    if stage == "verify" and item["name"] != "verify smart":
        from mdf_core.execution.module_verify import record_completed_playbook_clear

        record_completed_playbook_clear(repo, read_json(safe(repo, found["report"])), owned)
    return {"stage": stage, "completed": True, "already_completed": False, "commit": sha(repo, "HEAD"),
            "paths": changed, "evidence": found}
