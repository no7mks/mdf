"""sync 的 PR/MR 计划、提交与同名 fast-forward。"""
import re

from mdf_core.foundation.errors import MDFError
from mdf_core.integrations.forge import Forge, origin
from mdf_core.lifecycle.pull_finish import confirm_pull, remote_source_head, sync_local, verified_merge
from mdf_core.workspace.gitutil import ensure_clean, worktree_map
from mdf_core.workspace.merge_policy import ancestor, configured, git, local_head, sha
from mdf_core.workspace.workflow_policy import integration_branch, is_github_flow, sync_trunks


def settings(repo):
    candidates = [configured(repo)]
    for branch in (name for name in sync_trunks(repo) if name != "planning"):
        ref = f"refs/remotes/origin/{branch}"
        if not git(repo, "cat-file", "-e", f"{ref}:.mdf/manifest.yaml", check=False).returncode:
            candidates.append(configured(repo, ref))
    providers = {item["provider"] for item in candidates if item["mode"] == "pr"}
    if len(providers) > 1:
        raise MDFError("PR mode 的 provider 不一致", code="invalid_closeout")
    return {"mode": "pr", "provider": providers.pop()} if providers else {"mode": "local"}


def plans(repo, branches):
    """按当前 Git refs 预览需要 PR/MR 的同步。"""
    from mdf_core.inspection.push_audit import audit
    config = settings(repo)
    result = {}
    from mdf_core.workspace.merge_policy import trivial_commits
    integ = integration_branch(repo)
    github = is_github_flow(repo)
    protected = tuple(name for name in sync_trunks(repo) if name != "planning")
    handoff = "trunk_pr" if github else "dev_pr"
    for branch in protected:
        if config["mode"] != "pr":
            continue
        info = branches[branch]
        prefix = f"codex/sync/{branch}-{info['local']}-"
        if branch != integ:
            refs = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/codex/sync").stdout.splitlines()
            sources = [name for name in refs if re.fullmatch(re.escape(prefix) + r"[0-9a-f]{40}", name)]
            if len(sources) > 1:
                _changed("多个 sync source 对应当前目标提交")
            if sources:
                source = sources[0]
                result[branch] = {"action": "resume_pr", "source": source, "head": info["local"],
                                  "base": source.removeprefix(prefix), "source_head": local_head(repo, source),
                                  "provider": config["provider"]}
                continue
        report = None
        if branch == integ and info["relation"] == "ahead" and not github:
            if trivial_commits(repo, info["remote"], info["local"]):
                continue
        if info["relation"] == "ahead":
            evidence = {"sources": {name: sha(repo, f"refs/heads/{name}") for name in sync_trunks(repo) if name != integ},
                        "pull_requests": []}
            report = audit(repo, branch, info["remote"], info["local"], evidence, source_prefix="refs/heads")
            if any(item["reason"] == "local_support_merge" for item in report["commits"]):
                result[branch] = {"action": "delivery_merge", "head": info["local"], "base": info["remote"], "audit": report}
                continue
            if report["verdict"] == "pass" and report.get("reason") != "local_mode":
                continue
        elif info["relation"] != "diverged":
            continue
        result[branch] = {"action": handoff if branch == integ else "create_pr", "head": info["local"], "base": info["remote"],
                          "provider": config["provider"], "audit": report}
    return result


def _changed(message):
    raise MDFError(message + "；保留现场", code="pull_state_changed")


def advance(repo, plan, remote_tips):
    """保持目标不动，平台合并核验通过后才 fast-forward。"""
    config = settings(repo)
    results = {}
    for branch, item in plan.items():
        if item["action"] in {"dev_pr", "trunk_pr"}:
            from mdf_core.workspace.dev_pr import prepare
            results[branch] = prepare(repo, expected_head=item["head"], expected_base=item["base"])
            continue
        if config["mode"] != "pr" or config["provider"] != item["provider"]:
            _changed("PR mode 配置在同步期间变化")
        original, base = item["head"], item["base"]
        source = item.get("source", f"codex/sync/{branch}-{original}-{base}")
        head = item.get("source_head", original)
        if sha(repo, f"refs/heads/{branch}") != original or not ancestor(repo, original, head):
            _changed("本地目标或 sync source 历史在同步期间变化")
        occupant = worktree_map(repo).get(source)
        if occupant:
            ensure_clean(occupant)
        if local_head(repo, source) is None:
            git(repo, "branch", source, head)
        elif local_head(repo, source) != head:
            _changed("sync source 在同步期间变化")
        forge = Forge(repo, origin(repo, config["provider"]))
        pull = forge.find(source, None)
        if pull is not None and (pull["source"] != source or pull["target"] != branch):
            _changed("平台 PR/MR 的 source 或 target 已变化")
        if pull is None or pull["state"] == "open":
            remote = remote_source_head(repo, source)
            if remote is not None and not (ancestor(repo, original, remote) and ancestor(repo, remote, head)):
                _changed("远端 sync source branch 已变化")
            if pull is not None and (remote is None or not ancestor(repo, pull["head"], head)):
                _changed("未合并 PR/MR 的 source 已变化")
            if remote != head:
                git(repo, "push", "--no-follow-tags", "origin", f"{head}:refs/heads/{source}")
            if pull is None:
                pull = forge.create(source, branch, f"chore(sync): 同步本地 {branch} 增量",
                                    "MDF sync；合并时请保留双亲 merge commit。")
            else:
                pull = forge.get(pull["id"])
        confirm_pull(pull, source, branch, head)
        status = "waiting_for_merge" if pull["state"] == "open" else "closed_without_merge"
        merged = None
        if pull["state"] == "merged":
            git(repo, "fetch", "origin", "--prune")
            if any(sha(repo, f"refs/remotes/origin/{name}") != tip for name, tip in remote_tips.items()):
                from mdf_core.workspace.sync import _preview
                raise MDFError("同步期间远端 tip 已变化，请重新确认", code="sync_plan_changed",
                               details=_preview(repo, pr=True))
            merged = verified_merge(repo, pull, source, branch, head)
            if not ancestor(repo, base, merged + "^1") or sha(repo, f"refs/heads/{branch}") != original:
                _changed("目标分支在同步期间变化或历史已改写")
            sync_local(repo, branch)
            status = "completed"
        results[branch] = {"status": status, "pull_request": pull, "source": source,
                           "head": head, "merge_commit": merged}
    return results
