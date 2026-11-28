"""对完整 push 第一父链的每次落地操作做确定性审计。"""
import json
from pathlib import Path
from urllib.parse import urlencode
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.foundation.textutil import stable_semver
from mdf_core.lifecycle.delivery_state import read_json
from mdf_core.workspace.gitutil import repo_path, require_git_root
from mdf_core.workspace.pm import require_pm_merge
from mdf_core.workspace.merge_policy import (
    ancestor, commit_paths, configured, document, git, paths, planning_only, sha, trivial,
)
from mdf_core.workspace.workflow_switch import MANIFEST, SWITCH_BRANCH, valid_switch_source


def _source(repo, incoming, name, evidence, source_prefix):
    snapshot = evidence.get("sources", {}).get(name)
    if not snapshot:
        return False
    try:
        recorded = sha(repo, snapshot)
        current = sha(repo, f"{source_prefix}/{name}")
        return ancestor(repo, incoming, recorded) and ancestor(repo, recorded, current)
    except MDFError:
        return False


def _policy(repo, before):
    from mdf_core.workspace.workflow_policy import GITHUB_FLOW, workflow_config
    config = workflow_config(repo, before)
    return config["trunk"], config["model"] == GITHUB_FLOW


def _support_parent(repo, commit):
    listed = git(repo, "for-each-ref", "--points-at", commit, "--format=%(refname:short)", check=False).stdout.split()
    return any(name.startswith("support/") or name.startswith("origin/support/") for name in listed)


def _from_support(repo, commit, parents, evidence):
    if any(str(pull.get("source", "")).startswith("support/") and pull.get("merge_commit") == commit
           for pull in evidence.get("pull_requests", [])):
        return True
    return len(parents) == 2 and _support_parent(repo, parents[1])


def _platform_merge(commit, branch, head, evidence):
    return next((pull for pull in evidence.get("pull_requests", [])
                 if pull.get("state") == "merged" and pull.get("target") == branch
                 and pull.get("merge_commit") == commit and pull.get("head") == head
                 and pull.get("source") and pull.get("id") and pull.get("url")), None)


def _support_merge_start(repo, branch, commit, parents):
    from mdf_core.lifecycle.closeout_render import expected_tag_message
    from mdf_core.lifecycle.support_line import SHA_RE
    from mdf_core.workspace.gitutil import branch_details, unreleased_slug

    if not branch.startswith("support/") or len(parents) != 2:
        return None
    base, head = parents
    if not ancestor(repo, base, head) or paths(repo, head, commit):
        return None
    from mdf_core.reconciliation.context import metadata
    for path in paths(repo, base, head):
        parts = path.split("/")
        if len(parts) != 3 or parts[0] != "changes" or parts[2] != "CHANGE.md" or stable_semver(parts[1]) is None:
            continue
        try:
            data, _ = metadata(git(repo, "show", f"{head}:{path}").stdout)
            if (data.get("record_mode") == "ledgerless" and data.get("change_kind") == "hotfix"
                    and data.get("release_line") == branch and data.get("source_branch", "").startswith("hotfix/")):
                previous = data.get("previous_version")
                start = sha(repo, f"refs/tags/v{previous}")
                if ancestor(repo, start, base):
                    expected_tag_message(repo, parts[1], commit)
                    return start
        except (MDFError, TypeError, ValueError):
            continue
    for path in paths(repo, base, head):
        parts = path.split("/")
        if len(parts) != 3 or parts[0] != "changes" or parts[2] != "delivery.json":
            continue
        version = parts[1]
        semver = stable_semver(version)
        if semver is None or branch != f"support/{semver[0]}.{semver[1]}":
            continue
        try:
            if git(repo, "cat-file", "-e", f"{base}:{path}", check=False).returncode == 0:
                continue
            git(repo, "cat-file", "-e", f"{head}:changes/{version}/CHANGE.md")
            expected_tag_message(repo, version, commit)
            record = git(repo, "show", f"{head}:{path}").stdout
            data = json.loads(record)
            details = branch_details(data["branch"])
            start = data["start_commit"]
            if (details["kind"] == "hotfix" and details["version"] in (None, version)
                    and data.get("slug") == unreleased_slug(details) and data.get("version") == version
                    and data.get("base_branch") == branch and data.get("support", {}).get("branch") == branch
                    and SHA_RE.fullmatch(start) and ancestor(repo, start, base)):
                return start
        except (MDFError, AttributeError, KeyError, TypeError, ValueError):
            continue
    return None


def classify(repo, commit, branch, evidence, source_prefix, *, trunk, github):
    parents = git(repo, "show", "-s", "--format=%P", commit).stdout.split()
    changed = commit_paths(repo, commit)
    if github and branch == trunk and _from_support(repo, commit, parents, evidence):
        return "violation", "support_merge_forbidden", changed
    if len(parents) == 2:
        if github and _support_merge_start(repo, branch, commit, parents):
            return "pass", "local_support_merge", changed
        if pull := _platform_merge(commit, branch, parents[1], evidence):
            from mdf_core.workspace.reconcile_channel import is_reconcile
            if (github and str(pull["source"]).startswith("pm/")) or is_reconcile(pull["source"]):
                if branch != trunk:
                    return "violation", "invalid_pm_target", changed
                try:
                    require_pm_merge(repo, parents[0], parents[1], commit, pull["source"])
                except MDFError as exc:
                    if exc.code != "pm_paths_forbidden":
                        raise
                    return "violation", exc.code, exc.details["paths"]
            return "pass", "platform_merge", changed
        if not github and branch == "develop":
            if _source(repo, parents[1], trunk, evidence, source_prefix) and not changed:
                return "pass", "trunk_backmerge", changed
        if not github and branch == trunk:
            if (_source(repo, parents[1], "planning", evidence, source_prefix)
                    and planning_only(repo, parents[0], parents[1])
                    and all(document(p) for p in paths(repo, parents[0], commit))):
                return "pass", "planning_documents", changed
        return "needs-review", "missing_merge_evidence", changed
    if len(parents) > 2:
        return "needs-review", "unsupported_merge", changed
    if (not github and branch in {trunk, "develop"} and all(document(p) for p in changed)
            and _source(repo, commit, "planning", evidence, source_prefix)):
        return "pass", "planning_documents", changed
    if not github and branch == "develop" and all(trivial(repo, p) for p in changed):
        return "pass", "maintenance", changed
    return "violation", "direct_trunk_commit", changed


def _auditable(branch, trunk, github):
    if github:
        return branch == trunk or branch.startswith("support/")
    return branch in {trunk, "develop"}


def _audit_commit(repo, base, commit, branch, evidence, source_prefix, policy):
    trunk, github = policy
    changed = paths(repo, base, commit)
    if MANIFEST in changed:
        new_policy = _policy(repo, commit)
        if new_policy != _policy(repo, base):
            parents = git(repo, "show", "-s", "--format=%P", commit).stdout.split()
            if len(parents) < 2:
                return "violation", "direct_trunk_commit", changed, policy
            if branch == "develop" and not new_policy[1] and len(parents) == 2:
                if (_policy(repo, parents[1]) == new_policy
                        and _source(repo, parents[1], new_policy[0], evidence, source_prefix)
                        and not commit_paths(repo, commit)):
                    return "pass", "trunk_backmerge", changed, new_policy
                return "needs-review", "missing_merge_evidence", changed, policy
            if len(parents) != 2 or new_policy[0] != branch or paths(repo, parents[1], commit):
                return "violation", "invalid_workflow_switch", changed, policy
            pull = _platform_merge(commit, branch, parents[1], evidence)
            if pull is None:
                return "needs-review", "missing_merge_evidence", changed, policy
            if pull["source"] != SWITCH_BRANCH or not valid_switch_source(repo, base, parents[1], branch):
                return "violation", "invalid_workflow_switch", changed, policy
            return "pass", "platform_merge", changed, new_policy
    if not _auditable(branch, trunk, github):
        return "violation", "workflow_switch_required", changed, policy
    return (*classify(repo, commit, branch, evidence, source_prefix, trunk=trunk, github=github), policy)


def audit(repo, branch, before, after, evidence=None, *, source_prefix="refs/remotes/origin"):
    evidence = evidence or {}
    result = {"schema_version": 3, "operation": "audit-push", "branch": branch,
              "push_before": before, "push_after": after, "policy_ref": before, "commits": []}
    try:
        new_support = branch.startswith("support/") and before == "0" * 40
        if new_support:
            after = sha(repo, after)
            parents = git(repo, "show", "-s", "--format=%P", after).stdout.split()
            start = _support_merge_start(repo, branch, after, parents)
            if start is None or not _policy(repo, start)[1]:
                return {**result, "verdict": "violation", "reason": "invalid_support_creation"}
            before = start
        before, after = sha(repo, before), sha(repo, after)
        result.update(push_before=result["push_before"] if new_support else before, push_after=after, policy_ref=before)
        settings = configured(repo, before)
        policy = _policy(repo, before)
        trunk, github = policy
        if not _auditable(branch, trunk, github):
            after_trunk, after_github = _policy(repo, after) if settings["mode"] == "pr" else policy
            if branch != after_trunk and (branch != "develop" or after_github):
                allowed = f"{trunk} 与 support/*" if github else f"{trunk} 与 develop"
                raise MDFError(f"audit-push 仅接受 {allowed}", code="invalid_audit_target")
        if settings["mode"] != "pr":
            result.update(verdict="pass", reason="local_mode")
            return result
        if before not in git(repo, "rev-list", "--first-parent", after).stdout.split():
            result.update(verdict="violation", reason="rewritten_trunk")
            return result
        base = before
        for commit in git(repo, "rev-list", "--reverse", "--first-parent", f"{before}..{after}").stdout.split():
            verdict, reason, changed, policy = _audit_commit(repo, base, commit, branch, evidence, source_prefix, policy)
            result["commits"].append({"commit": commit, "verdict": verdict, "reason": reason, "paths": changed})
            base = commit
    except (MDFError, TypeError, AttributeError, ValueError) as exc:
        if isinstance(exc, MDFError) and exc.code == "invalid_audit_target":
            raise
        verdict = "violation" if any(c["verdict"] == "violation" for c in result["commits"]) else "needs-review"
        result.update(verdict=verdict, reason=str(exc))
        return result
    verdicts = {item["verdict"] for item in result["commits"]}
    result["verdict"] = "violation" if "violation" in verdicts else "needs-review" if "needs-review" in verdicts else "pass"
    return result


def command_audit_push(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    evidence = read_json(Path(args.evidence_file)) if args.evidence_file else {}
    if args.collect_evidence:
        try:
            evidence = collect(repo, args.branch, args.before, args.after)
        except (MDFError, KeyError, TypeError, ValueError) as exc:
            emit({"ok": True, "result": {"verdict": "needs-review", "reason": str(exc),
                                         "push_before": args.before, "push_after": args.after}})
            return
    result = audit(repo, args.branch, args.before, args.after, evidence)
    emit({"ok": True, "result": result})


def collect(repo, branch, before, after):
    """CI controller 显式请求时采集平台事实；默认离线审计不访问网络。"""
    from mdf_core.integrations.forge import Forge, origin
    evidence = {"sources": {}, "pull_requests": []}
    if branch.startswith("support/") and before == "0" * 40:
        return evidence
    settings = configured(repo, before)
    before, after = sha(repo, before), sha(repo, after)
    wanted = set(git(repo, "rev-list", "--first-parent", "--merges", f"{before}..{after}").stdout.split())
    trunk, github = _policy(repo, before)
    if github and branch.startswith("support/"):
        wanted = {commit for commit in wanted if not _support_merge_start(
            repo, branch, commit, git(repo, "show", "-s", "--format=%P", commit).stdout.split(),
        )}
        if not wanted:
            return evidence
    forge = Forge(repo, origin(repo, settings["provider"]))
    # 新 trunk 的切换只依赖平台 Merge 证据，CI checkout 已包含 push 的 Git 对象。
    names = {trunk, "develop", "planning"} if not github and _auditable(branch, trunk, github) else set()
    if branch == "develop":
        next_trunk, next_github = _policy(repo, after)
        if not next_github:
            names.add(next_trunk)
    if names:
        git(repo, "fetch", "origin", "--prune")
    for name in sorted(names):
        ref = git(repo, "rev-parse", "--verify", f"refs/remotes/origin/{name}", check=False)
        if not ref.returncode:
            evidence["sources"][name] = ref.stdout.strip()
    page = 1
    while wanted:
        query = ({"state": "closed", "base": branch} if forge.github else
                 {"state": "merged", "target_branch": branch, "scope": "all"})
        rows = forge.api(forge.endpoint + "?" + urlencode({**query, "per_page": 100, "page": page}))
        if not isinstance(rows, list):
            raise MDFError("平台列表无效", code="forge_invalid_response")
        for row in rows:
            if row.get("merge_commit_sha") not in wanted:
                continue
            item = forge.get(row["number"] if forge.github else row["iid"])
            if item["state"] == "merged":
                evidence["pull_requests"].append(item)
                wanted.discard(item["merge_commit"])
        if len(rows) < 100:
            break
        page += 1
    return evidence
