"""对完整 push 第一父链的每次落地操作做确定性审计。"""
from pathlib import Path
from urllib.parse import urlencode
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.lifecycle.delivery_state import read_json
from mdf_core.workspace.gitutil import repo_path, require_git_root
from mdf_core.workspace.pm import require_pm_merge
from mdf_core.workspace.merge_policy import (
    ancestor, commit_paths, configured, document, git, paths, planning_only, sha, trivial,
)


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


def classify(repo, commit, branch, evidence, source_prefix, *, trunk, github):
    parents = git(repo, "show", "-s", "--format=%P", commit).stdout.split()
    changed = commit_paths(repo, commit)
    if github and branch == trunk and _from_support(repo, commit, parents, evidence):
        return "violation", "support_merge_forbidden", changed
    if len(parents) == 2:
        for pull in evidence.get("pull_requests", []):
            if (pull.get("state") == "merged" and pull.get("target") == branch
                    and pull.get("merge_commit") == commit and pull.get("head") == parents[1]
                    and pull.get("source") and pull.get("id") and pull.get("url")):
                if github and str(pull["source"]).startswith("pm/"):
                    if branch != trunk:
                        return "violation", "invalid_pm_target", changed
                    try:
                        require_pm_merge(repo, parents[0], parents[1], commit)
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


def audit(repo, branch, before, after, evidence=None, *, source_prefix="refs/remotes/origin"):
    evidence = evidence or {}
    trunk, github = _policy(repo, before)
    if not _auditable(branch, trunk, github):
        allowed = f"{trunk} 与 support/*" if github else f"{trunk} 与 develop"
        raise MDFError(f"audit-push 仅接受 {allowed}", code="invalid_audit_target")
    result = {"schema_version": 3, "operation": "audit-push", "branch": branch,
              "push_before": before, "push_after": after, "policy_ref": before, "commits": []}
    try:
        before, after = sha(repo, before), sha(repo, after)
        result.update(push_before=before, push_after=after, policy_ref=before)
        settings = configured(repo, before)
        if settings["mode"] != "pr":
            result.update(verdict="pass", reason="local_mode")
            return result
        if before not in git(repo, "rev-list", "--first-parent", after).stdout.split():
            result.update(verdict="violation", reason="rewritten_trunk")
            return result
        for commit in git(repo, "rev-list", "--reverse", "--first-parent", f"{before}..{after}").stdout.split():
            verdict, reason, changed = classify(
                repo, commit, branch, evidence, source_prefix, trunk=trunk, github=github)
            result["commits"].append({"commit": commit, "verdict": verdict, "reason": reason, "paths": changed})
    except (MDFError, TypeError, AttributeError) as exc:
        result.update(verdict="needs-review", reason=str(exc))
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
    settings = configured(repo, before)
    forge = Forge(repo, origin(repo, settings["provider"]))
    git(repo, "fetch", "origin", "--prune")
    wanted = set(git(repo, "rev-list", "--first-parent", "--merges", f"{sha(repo, before)}..{sha(repo, after)}").stdout.split())
    evidence = {"sources": {}, "pull_requests": []}
    trunk, github = _policy(repo, before)
    names = (trunk,) if github else (trunk, "develop", "planning")
    for name in names:
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
