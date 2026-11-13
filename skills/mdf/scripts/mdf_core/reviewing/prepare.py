"""review-prepare：统一输出审查左端点、未审净增量、交互文件集、numstat、体积结论与生效规则；只读。"""
import math

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.lifecycle.catchup_plan import graph, surface, target_refs
from mdf_core.lifecycle.delivery_state import locate
from mdf_core.reviewing import credentials
from mdf_core.reviewing.context import effective_rules, fingerprint
from mdf_core.reviewing.scope import review_changes
from mdf_core.workspace.gitutil import ensure_clean, repo_path, require_git_root
from mdf_core.workspace.merge_policy import ancestor, git, sha

LINES_PER_REVIEWER = 1000


def left_endpoint(repo, against):
    if against:
        return sha(repo, against), None
    try:
        _, data = locate(repo)
    except MDFError as exc:
        raise MDFError("非交付分支需要 --against 指定审查左端点", code="missing_review_base") from exc
    return sha(repo, data["start_commit"]), data


def covered_paths(repo, paths, rules_sha256):
    """HEAD 上内容与已通过凭证完全一致（且规则相同）的路径；凭证只承认内容，不承认提交。"""
    heads = credentials.blob_ids(repo, "HEAD", paths)
    found = {}
    for record in credentials.records(repo, "code-review"):
        if record.get("decision") != "pass" or record.get("rules_sha256") != rules_sha256:
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
    left, data = left_endpoint(repo, against)
    head = sha(repo, "HEAD")
    if not ancestor(repo, left, head):
        raise MDFError("审查左端点必须是 HEAD 的祖先", code="invalid_review_base")
    refs = target_refs(repo, (data or {}).get("target"))
    policy_ref = sha(repo, refs[0]) if refs else head
    rules, config = effective_rules(repo, policy_ref, head)
    rules_sha256 = fingerprint(rules)
    paths, _ = review_changes(repo, left, head, config)
    covered = {} if force else covered_paths(repo, paths, rules_sha256)
    net = [p for p in paths if p not in covered]
    _, own, incoming = graph(repo, left, refs)
    interaction = sorted(set(p for p in surface(repo, own) if p in set(paths)) & surface(repo, incoming))
    rows = numstat(repo, left, net)
    lines = sum((r["added"] or 0) + (r["deleted"] or 0) for r in rows)
    reviewers = 0 if not net else max(1, math.ceil(lines / LINES_PER_REVIEWER))
    return {"left": left, "head": head, "policy_ref": policy_ref, "paths": paths,
            "net_increment": net, "covered": covered, "interaction": interaction, "numstat": rows,
            "size": {"lines": lines, "files": len(net), "per_reviewer": LINES_PER_REVIEWER, "reviewers": reviewers},
            "project_rules": rules["project"], "rules_sha256": rules_sha256, "force": force,
            "skip_review": not net and not interaction}


def command_review_prepare(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    emit({"ok": True, "operation": "review-prepare", "result": build(repo, args.against, args.force)})
