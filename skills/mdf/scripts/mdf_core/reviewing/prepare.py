"""review-prepare：统一输出审查左端点、未审净增量、交互文件集、numstat、体积结论与生效规则；只读。"""
import math

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.execution.modules import load_modules
from mdf_core.lifecycle.catchup_plan import graph, surface, target_refs
from mdf_core.lifecycle.delivery_state import locate
from mdf_core.reviewing import credentials
from mdf_core.reviewing.context import effective_rules, fingerprint
from mdf_core.reviewing.scope import review_changes
from mdf_core.workspace.gitutil import branch_details, ensure_clean, repo_path, require_git_root
from mdf_core.workspace.merge_policy import ancestor, git, sha

LINES_PER_REVIEWER = 1000


def delivery_of(repo):
    """当前交付的 (材料目录, delivery.json)；非交付分支为 (None, None)。"""
    try:
        return locate(repo)
    except MDFError:
        return None, None


def left_endpoint(repo, against, data):
    if against:
        return sha(repo, against)
    if data is None:
        raise MDFError("非交付分支需要 --against 指定审查左端点", code="missing_review_base")
    return sha(repo, data["start_commit"])


def covered_paths(repo, paths, rules_sha256, requirements):
    """HEAD 上内容、规则与需求均与已通过凭证一致的路径；凭证只承认内容，不承认提交。无交付身份时不复用。"""
    heads = credentials.blob_ids(repo, "HEAD", paths)
    found = {}
    for record in credentials.records(repo, "code-review"):
        if (record.get("decision") != "pass" or record.get("rules_sha256") != rules_sha256
                or requirements is None or record.get("requirements_digest") != requirements):
            continue
        for path, blob_id in heads.items():
            if blob_id is not None and record.get("files", {}).get(path) == blob_id:
                found.setdefault(path, record["key"])
    return found


def numstat(repo, left, paths):
    rows = []
    if paths:
        out = git(repo, "diff", "--no-renames", "--numstat", "-z", left, "HEAD", "--",
                  *(":(literal)" + p for p in paths)).stdout
        for row in filter(None, out.split("\0")):
            added, deleted, path = row.split("\t", 2)
            rows.append({"path": path, "added": None if added == "-" else int(added),
                         "deleted": None if deleted == "-" else int(deleted)})
    return rows


def build(repo, against, force):
    ensure_clean(repo)
    root, data = delivery_of(repo)
    left = left_endpoint(repo, against, data)
    head = sha(repo, "HEAD")
    if not ancestor(repo, left, head):
        raise MDFError("审查左端点必须是 HEAD 的祖先", code="invalid_review_base")
    refs = target_refs(repo, (data or {}).get("target"))
    policy_ref = sha(repo, refs[0]) if refs else head
    rules, scope_config = effective_rules(repo, policy_ref, head)
    rules_sha256 = fingerprint(rules)
    paths, _ = review_changes(repo, left, head, scope_config)
    config = load_modules(repo)
    objectives = (root / "objectives.md").read_text(encoding="utf-8") if root else ""
    requirements = credentials.requirements_digest(repo, "HEAD", objectives, data) if data else None
    reuse, covered = None, {}
    if not force and data and branch_details(data.get("branch", ""))["kind"] in {"release", "on-demand-release"}:
        identity = credentials.code_identity(repo, "HEAD", paths, rules_sha256, objectives, data)
        reuse = credentials.reuse_analysis(repo, data["branch"], identity, config)
        net = reuse["net_increment"]
        covered = {p: None for p in paths if p not in net}
    elif not force:
        covered = covered_paths(repo, paths, rules_sha256, requirements)
        net = [p for p in paths if p not in covered]
    else:
        net = paths
    _, own, incoming = graph(repo, left, refs)
    path_set = set(paths)
    interaction = sorted(set(p for p in surface(repo, own) if p in path_set) & surface(repo, incoming))
    interaction_modules = config.interacting(config.modules_for_paths(repo, sorted(surface(repo, own) & path_set)),
                                             config.modules_for_paths(repo, sorted(surface(repo, incoming) & path_set)))
    rows = numstat(repo, left, net)
    lines = sum((r["added"] or 0) + (r["deleted"] or 0) for r in rows)
    reviewers = 0 if not net else max(1, math.ceil(lines / LINES_PER_REVIEWER))
    return {"left": left, "head": head, "policy_ref": policy_ref, "paths": paths,
            "net_increment": net, "covered": covered, "interaction": interaction,
            "interaction_modules": interaction_modules, "reuse": reuse, "numstat": rows,
            "size": {"lines": lines, "files": len(net), "per_reviewer": LINES_PER_REVIEWER, "reviewers": reviewers},
            "project_rules": rules["project"], "rules_sha256": rules_sha256, "force": force,
            "skip_review": not net and not interaction and not interaction_modules
            and (reuse is None or not (reuse["combined_impact"] or reuse["combined_modules"]))}


def command_review_prepare(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    emit({"ok": True, "operation": "review-prepare", "result": build(repo, args.against, args.force)})
