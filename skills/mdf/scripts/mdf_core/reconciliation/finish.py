"""复用 Git 合并、平台核验与发布原语，保持三类发布的既定顺序。"""
import contextlib
import io
import json
from pathlib import Path

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.yamlutil import read_frontmatter
from mdf_core.lifecycle.delivery_state import read_json, write_json
from mdf_core.lifecycle.pull_finish import (
    Forge, cleanup, cleanup_remote, origin, remote_source_head, sync_local, verified_merge,
)
from mdf_core.lifecycle.pull_publish import tag_release
from mdf_core.lifecycle.publish import find_merge, require_remote_merge
from mdf_core.lifecycle.release_publish import published_head
from mdf_core.reconciliation.context import state_path
from mdf_core.reconciliation.evidence import require_evidence, require_object_outcomes
from mdf_core.workspace.gitutil import current_branch, ensure_clean, primary_worktree, worktree_map
from mdf_core.workspace.merge_policy import ancestor, git, sha
from mdf_core.workspace.workflow_policy import trunk_branch


def captured(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()) as output:
        function(*args, **kwargs)
    return json.loads(output.getvalue())


def merge_local(repo, source, target):
    from mdf_core.workspace.gitflow import merge_preserving_checkout
    from mdf_core.workspace.merge_guard import capture
    work = worktree_map(repo).get(target) or primary_worktree(repo)
    ensure_clean(work)
    head = sha(repo, source)
    merged = find_merge(repo, target, head)
    if not merged and not ancestor(repo, head, target):
        merge_preserving_checkout(work, source, target, capture(repo, source, target))
        merged = find_merge(repo, target, head)
    return merged or sha(repo, target)


def clean_worktree(repo, state):
    from mdf_core.lifecycle.pull_finish import retained_owner
    source = state["source"]
    expected = Path(state["worktree"]) if state.get("worktree") else None
    owner = worktree_map(repo).get(source) or retained_owner(repo, source, state["head"], work=expected)
    if owner is None and expected and expected.exists() and expected != primary_worktree(repo):
        raise MDFError("原临时 worktree 的身份已变化，保留现场", code="reconcile_cleanup_required")
    if owner and owner != primary_worktree(repo):
        ensure_clean(owner)
        ignored = git(owner, "ls-files", "--others", "--ignored", "--exclude-standard", "-z").stdout.split("\0")
        foreign = [p for p in ignored if p and not p.startswith((".mdf/logs/", ".mdf/reports/", ".mdf/tmp/", ".mdf/cache/"))]
        if foreign:
            raise MDFError("临时工作区仍有需保留的 ignored 文件", code="reconcile_cleanup_required",
                           details={"worktree": str(owner), "paths": foreign})
    cleanup(repo, state)
    if owner and owner != primary_worktree(repo):
        git(primary_worktree(repo), "worktree", "remove", str(owner))


def cleanup_state(repo, state):
    if state["remote"]:
        require_remote_merge(repo, state["target"], state["merge_commit"])
    elif not ancestor(repo, state["merge_commit"], state["target"]):
        raise MDFError("本地目标不再包含已合入提交", code="reconcile_state_changed")
    if state["remote"]:
        cleanup_remote(repo, state["source"], state["head"])
    clean_worktree(repo, state)


def finish_cleanup(repo, plan):
    path = state_path(repo, plan["source"])
    state = plan["cleanup"]
    support_record = None
    if plan["record_mode"] == "ledgerless" and plan["release_line"].startswith("support/"):
        from mdf_core.lifecycle.publish import merge_record_path
        support_record = merge_record_path(repo, plan["source"], plan["version"])
    if plan["record_mode"] == "ledgerless":
        if published_head(repo, plan["version"], expected_oid=plan["tag_oid"]) != plan["release_head"]:
            raise MDFError("发布记录与 final tag 不符", code="tag_conflict")
    cleanup_state(repo, state)
    if support_record:
        write_json(support_record, {**read_json(support_record), "closed": True})
    write_json(path, {**plan, "completed": True})
    return {"completed": True, "source": plan["source"], "merge_commit": state["merge_commit"],
            "release_head": plan.get("release_head"), "version": plan.get("version"),
            "tag": f"v{plan['version']}" if plan.get("version") else None}


def save_cleanup(repo, plan, state, *, key="cleanup"):
    owner = state.get("retained_worktree") or worktree_map(repo).get(state["source"])
    state = {**state, "worktree": str(owner) if owner else state.get("worktree")}
    plan = {**plan, key: state}
    write_json(state_path(repo, plan["source"]), plan)
    return plan


def start_cleanup(repo, plan, state):
    plan = save_cleanup(repo, plan, state)
    return finish_cleanup(repo, plan)


def require_ci(repo, forge, source, pull):
    from mdf_core.lifecycle.pull_watch import watch
    result = watch(repo, source, forge, [], False, number=pull["id"], expected_head=pull["head"])
    if result["status"] != "merged":
        raise MDFError("PR 的 CI/review 尚未完成", code="reconcile_ci_pending", details=result)


def finish_records(repo, plan, args):
    from mdf_core.workspace.reconcile_channel import require_history
    source, target = plan["source"], plan["target"]
    required = {r["version"] for r in plan["releases"]}
    if set(plan.get("recorded_versions", [])) != required:
        raise MDFError("先逐版完成 apply", code="reconciliation_required")
    from mdf_core.reconciliation.validation import require_record
    for version in sorted(required):
        require_record(repo, plan, version)
    proof = read_json(Path(args.evidence_file)) if args.evidence_file else None
    require_evidence(repo, proof, sha(repo, "HEAD"), {"fact", "lint"})
    require_history(repo, plan["base_head"], "HEAD")
    if plan["settings"]["mode"] == "pr":
        from mdf_core.lifecycle.pull_finish import _finish
        result = captured(_finish, repo, source, plan["settings"], phase="pr", number=None)
        if not result.get("completed"):
            return {**result, "next_intent": "pr-watch"}
        from mdf_core.lifecycle import pull_finish
        forge = pull_finish.Forge(repo, pull_finish.origin(repo, plan["settings"]["provider"]))
        require_ci(repo, forge, source, result["pull_request"])
        def journal(at, state):
            save_cleanup(at, plan, {**state, "remote": True})
        captured(_finish, repo, source, plan["settings"], phase="close-out", number=result["pull_request"]["id"], before_cleanup=journal)
        return finish_cleanup(repo, read_json(state_path(repo, source)))
    if source == "planning":
        from mdf_core.workspace.planning import command_planning_land
        from types import SimpleNamespace
        return {**captured(command_planning_land, SimpleNamespace(repo=str(repo))), "completed": True}
    merged = merge_local(repo, source, target)
    head = sha(repo, source)
    return start_cleanup(repo, plan, {"source": source, "head": head, "target": target, "merge_commit": merged, "remote": False})


def publish_candidate(repo, plan, state, head):
    version, source = plan["version"], plan["source"]
    from mdf_core.lifecycle.support_line import recheck_before_publish
    if not state.get("published"):
        recheck_before_publish(repo, source, version, target=plan["release_line"], head=head)
    remote = remote_source_head(repo, source)
    if remote and not ancestor(repo, remote, head):
        raise MDFError("远端同名分支领先，先同步并补验", code="catchup_required")
    release_head = state.get("release_head", head)
    if release_head != head and not ancestor(repo, release_head, head):
        raise MDFError("固定发布候选丢失", code="release_head_changed")
    ref = f"refs/tags/v{version}"
    remote_tag = git(repo, "ls-remote", "origin", ref).stdout.strip()
    if not state.get("published") and not remote_tag and release_head != head:
        raise MDFError("未发布的固定候选已与当前 source 不同，保留现场重新核对", code="release_head_changed")
    if not remote_tag and remote and not ancestor(repo, remote, release_head):
        raise MDFError("远端 source 超出固定发布候选，不改写共享历史", code="catchup_required")
    local_tag = git(repo, "rev-parse", "--verify", ref, check=False)
    expected_oid = state.get("tag_oid")
    if expected_oid and ((remote_tag and remote_tag.split()[0] != expected_oid)
                         or (not local_tag.returncode and local_tag.stdout.strip() != expected_oid)):
        raise MDFError("final tag 对象已改变", code="tag_conflict")
    state["release_head"] = release_head
    write_json(state_path(repo), {**plan, **state})
    if remote_tag and git(repo, "rev-parse", "--verify", ref, check=False).returncode:
        git(repo, "fetch", "--no-tags", "origin", f"{ref}:{ref}")
    tag_state = {"release_head": release_head, "merge_commit": release_head}
    early = plan["workflow"] == "github-flow" and plan["kind"] == "release"
    tag_release(repo, tag_state, version, source=source if early and not remote_tag else None, expected_remote=remote)
    if state.get("tag_oid") and state["tag_oid"] != tag_state["tag_oid"]:
        raise MDFError("final tag 对象已改变", code="tag_conflict")
    if published_head(repo, version, expected_oid=tag_state["tag_oid"]) != release_head:
        raise MDFError("final tag 与固定候选不符", code="tag_conflict")
    state.update(published=True, tag_oid=tag_state["tag_oid"])
    write_json(state_path(repo), {**plan, **state})


def integrate_target(repo, plan, head):
    target = plan["release_line"]
    git(repo, "fetch", "--no-tags", "origin", f"refs/heads/{target}:refs/remotes/origin/{target}")
    target_head = sha(repo, f"refs/remotes/origin/{target}")
    if ancestor(repo, target_head, head):
        return target_head
    result = git(repo, "merge", "--no-ff", "--no-edit", "-m", "chore(reconcile): 集成发布目标并等待增量验收", target_head, check=False)
    if result.returncode:
        raise MDFError("目标集成冲突；保留现场解决后补验", code="merge_conflict")
    from mdf_core.lifecycle.incremental_plan import build_plan
    increment = build_plan(repo, repo, {"branch": plan["source"], "start_commit": plan["head"]}, explicit_base=head)
    raise MDFError("目标已集成；按增量 plan 补审补验并刷新记录及外部证据", code="integration_required", details=increment)


def finish_release(repo, plan, args):
    source, version, target = plan["source"], plan["version"], plan["release_line"]
    from mdf_core.reconciliation.context import require_no_ledger
    from mdf_core.reconciliation.validation import require_record
    require_no_ledger(repo, source, version)
    head = sha(repo, "HEAD")
    if plan.get("merge_commit"):
        from mdf_core.lifecycle.publish import remote_contains_merge
        if remote_contains_merge(repo, target, plan["merge_commit"]):
            parents = git(repo, "show", "-s", "--format=%P", plan["merge_commit"]).stdout.split()
            if len(parents) != 2 or parents[1] != head:
                raise MDFError("实际合入后 source 已变化，保留现场，不发布另一个候选", code="pull_state_changed")
    proof = read_json(Path(args.evidence_file)) if args.evidence_file else None
    suite = "release" if plan["kind"] == "release" else "smoke"
    require_evidence(repo, proof, head, {"lint", "build", "quick", suite, "code-review", "fact"})
    if version not in plan.get("recorded_versions", []):
        raise MDFError("先 apply 记录本版成果", code="reconciliation_required")
    early_publish = plan["workflow"] == "github-flow" and plan["kind"] == "release"
    if early_publish and not plan.get("published") and plan.get("release_head") and head != plan["release_head"]:
        raise MDFError("未发布的固定候选已与当前 source 不同，保留现场重新核对", code="release_head_changed")
    if not plan.get("published") and head != plan.get("record_head"):
        raise MDFError("候选已有新增提交；先重新 apply 对账，再补齐验收证据", code="reconciliation_required")
    require_record(repo, plan, version)
    meta, _ = read_frontmatter(repo / "changes" / version / "CHANGE.md")
    require_object_outcomes(repo, meta)
    state = {key: plan[key] for key in ("release_head", "published", "tag_oid", "merge_commit") if key in plan}
    support = target.startswith("support/")
    for branch in (target, *(["develop"] if plan["workflow"] == "gitflow" else [])):
        if work := worktree_map(repo).get(branch):
            ensure_clean(work)
    if early_publish:
        publish_candidate(repo, plan, state, head)
    git(repo, "fetch", "--no-tags", "origin", f"refs/heads/{target}:refs/remotes/origin/{target}")
    existing_merge = find_merge(repo, f"refs/remotes/origin/{target}", head)
    if existing_merge:
        parents = git(repo, "show", "-s", "--format=%P", existing_merge).stdout.split()
        if not ancestor(repo, parents[0], head) or git(repo, "diff", "--quiet", head, existing_merge, check=False).returncode:
            raise MDFError("实际合并未保留已验收的目标集成", code="integration_required")
        target_head = parents[0]
    else:
        target_head = integrate_target(repo, plan, head)
    use_pr = plan["settings"]["mode"] == "pr" and not support
    if use_pr:
        from mdf_core.workspace.squash import require_ready
        require_ready(repo, source)
        from mdf_core.lifecycle import pull_finish
        forge = pull_finish.Forge(repo, pull_finish.origin(repo, plan["settings"]["provider"]))
        pull = forge.find(source, target)
        remote = remote_source_head(repo, source)
        if remote and not ancestor(repo, remote, head):
            raise MDFError("远端 source 已前进", code="catchup_required")
        if not pull or pull["state"] == "open":
            git(repo, "push", "--no-follow-tags", "origin", f"{head}:refs/heads/{source}")
            pull = forge.create(source, target, f"chore(release): 发布 {version}", "经外部 evidence 核验的 reconcile 发布。") if not pull else forge.get(pull["id"])
        if pull["state"] != "merged":
            return {"completed": False, "pull_request": pull, "next_intent": "pr-watch"}
        require_ci(repo, forge, source, pull)
        git(repo, "fetch", "origin", "--prune")
        merged = verified_merge(repo, pull, source, target, head)
        sync_local(repo, target)
    else:
        if not existing_merge and not state.get("merge_commit") and ancestor(repo, target, target_head):
            sync_local(repo, target)
        if sha(repo, target) not in {target_head, state.get("merge_commit")} and not existing_merge:
            raise MDFError("本地目标与远端不同，先同步目标", code="publish_state_changed")
        merged = existing_merge or merge_local(repo, source, target)
        if git(repo, "diff", "--quiet", head, merged, check=False).returncode:
            raise MDFError("实际合并包含未验收内容", code="integration_required")
        state["merge_commit"] = merged
        write_json(state_path(repo), {**plan, **state})
        git(repo, "push", "--atomic", "--no-follow-tags", "origin", f"{merged}:refs/heads/{target}", f"{head}:refs/heads/{source}")
        require_remote_merge(repo, target, merged)
    state["merge_commit"] = merged
    if not early_publish:
        # Gitflow 与 support 只给已核验、实际合入的双亲 merge 打 tag。
        publish_candidate(repo, plan, state, merged)
    if support:
        from mdf_core.lifecycle.publish import merge_record_path
        write_json(merge_record_path(repo, source, version), {
            "source": source, "head": head, "target": target, "merge_commit": merged, "published": True, "closed": False,
        })
    if support and plan["settings"]["mode"] == "pr":
        from mdf_core.workspace.changelog_sync import prepare as prepare_sync, trunk_policy, require_synced, complete as complete_sync
        record = {"merge_commit": merged}
        if plan.get("sync_cleanup"):
            cleanup_state(repo, plan["sync_cleanup"])
            complete_sync(repo, version, record)
            plan = {k: v for k, v in plan.items() if k != "sync_cleanup"}
            write_json(state_path(repo), {**plan, **state})
        try:
            require_synced(repo, version, merged)
        except MDFError as exc:
            if exc.code != "changelog_sync_required":
                raise
            sync = prepare_sync(repo, source, version, record, trunk_policy(repo))
            from mdf_core.lifecycle import pull_finish
            work = Path(sync["worktree"])
            settings = plan["settings"]
            result = captured(pull_finish._finish, work, sync["source"], settings, phase="pr", number=None)
            if not result.get("completed"):
                return {**result, "next_intent": "pr-watch"}
            forge = pull_finish.Forge(repo, pull_finish.origin(repo, settings["provider"]))
            require_ci(repo, forge, sync["source"], result["pull_request"])
            def journal(at, sync_state):
                save_cleanup(at, {**plan, **state}, {**sync_state, "remote": True}, key="sync_cleanup")
            captured(pull_finish._finish, work, sync["source"], settings, phase="close-out", number=None, before_cleanup=journal)
            pending = read_json(state_path(repo))
            cleanup_state(repo, pending["sync_cleanup"])
            complete_sync(repo, version, record)
            plan = {k: v for k, v in pending.items() if k != "sync_cleanup"}
            write_json(state_path(repo), plan)
    if plan["workflow"] == "gitflow" and not ancestor(repo, merged, "develop"):
        merge_local(repo, merged, "develop")
    result = start_cleanup(repo, {**plan, **state}, {
        "source": source, "head": head, "target": target, "merge_commit": merged, "remote": True,
    })
    return result


def finish(repo, args):
    ensure_clean(repo)
    path = state_path(repo, args.source)
    plan = read_json(path)
    if plan.get("completed"):
        return {"completed": True, "already_completed": True, "source": plan["source"]}
    if args.record_only:
        return {"recorded": bool(plan.get("recorded_versions")), "completed": False, "record_only": True}
    if not args.yolo:
        return {"completed": False, "state": "awaiting_publication_confirmation", "next_intent": "reconcile finish --yolo"}
    if plan.get("cleanup"):
        return finish_cleanup(repo, plan)
    from mdf_core.workspace.workflow_policy import is_github_flow
    from mdf_core.workspace.merge_policy import configured
    workflow = "github-flow" if is_github_flow(repo) else "gitflow"
    if (plan["source"] != current_branch(repo) or plan["workflow"] != workflow
            or plan["settings"] != configured(repo)):
        raise MDFError("reconcile 的工作分支或 workflow 已变化", code="reconcile_state_changed")
    result = finish_records(repo, plan, args) if plan["record_mode"] == "post_hoc" else finish_release(repo, plan, args)
    if result.get("completed"):
        write_json(path, {**read_json(path), "completed": True})
    return result
