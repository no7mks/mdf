"""历史对象归属只读核对；不回滚已演进的当前对象。"""
from pathlib import Path
import re

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.yamlutil import read_frontmatter
from mdf_core.reconciliation.context import metadata
from mdf_core.workspace.merge_policy import ancestor, git, sha


def proposal_at(repo, ref, identifier):
    from mdf_core.foundation.constants import OBJECT_FILE_RE
    found = []
    for path in git(repo, "ls-tree", "-r", "--name-only", ref, "--", "docs/proposals").stdout.splitlines():
        match = OBJECT_FILE_RE.fullmatch(Path(path).name)
        if match and match.group(1) == identifier:
            meta, _ = metadata(git(repo, "show", f"{ref}:{path}").stdout)
            if meta.get("id") == identifier and meta.get("type") == "proposal":
                found.append((meta, match.group(2)))
    if len(found) != 1:
        raise MDFError("指定快照缺少唯一的真实 PRP", code="invalid_reconciliation", details={"id": identifier, "ref": ref})
    return found[0]


def supplied_pull(repo, change, source, head, candidate):
    identity = change.get("pull_request")
    if identity is None:
        return None
    if (not isinstance(identity, dict) or set(identity) != {"provider", "number"}
            or identity["provider"] not in {"github", "gitlab"}
            or type(identity["number"]) is not int or identity["number"] <= 0):
        raise MDFError("pull_request 需要 provider 和正整数 number", code="invalid_reconciliation")
    from mdf_core.integrations import forge
    pull = forge.Forge(repo, forge.origin(repo, identity["provider"])).get(identity["number"])
    if (pull["state"] != "merged" or pull["source"] != source or pull["head"] != head
            or pull["merge_commit"] not in change["commits"] or not ancestor(repo, pull["merge_commit"], candidate)):
        raise MDFError("平台 PR 的来源、状态或 SHA 与区间不一致", code="invalid_reconciliation")
    return pull


def require_supplied_source(repo, release, change, meta):
    source, head = meta["source_branch"], change.get("source_head")
    candidate = release.get("release_commit") or release["head"]
    owned = change["commits"]
    if (not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", str(head))
            or head not in owned or sha(repo, head) != head or not ancestor(repo, head, candidate)):
        raise MDFError("真实来源需要区间内的固定 source_head", code="invalid_reconciliation")
    source_known = any(not git(repo, "rev-parse", "--verify", ref, check=False).returncode and ancestor(repo, head, ref)
                       for ref in (f"refs/heads/{source}", f"refs/remotes/origin/{source}"))
    merges = {c for c in owned if (parents := git(repo, "show", "-s", "--format=%P", c).stdout.split())
              and len(parents) == 2 and parents[1] == head}
    pull = supplied_pull(repo, change, source, head, candidate)
    if not source_known and pull is None:
        raise MDFError("声明的分支缺少同名 ref 或已核实 PR 来源证明", code="invalid_reconciliation")
    if pull is not None:
        meta["evidence"]["artifacts"].append(pull["url"])
    if any(not ancestor(repo, c, head) and c not in merges for c in owned):
        raise MDFError("changes 包含不属于该 source 的 commit", code="invalid_reconciliation")
    proposals = meta["proposals"]
    if not proposals:
        return
    if not isinstance(proposals, list) or len(proposals) != 1 or meta["change_kind"] != "feature":
        raise MDFError("feature 只绑定一个已核实 PRP", code="invalid_reconciliation")
    for ref in (head, candidate):
        proposal, slug = proposal_at(repo, ref, proposals[0])
        if slug != change["slug"] or proposal.get("status") not in {"ready", "implemented", "released"}:
            raise MDFError("历史 PRP 与 feature 的归属或状态不符", code="invalid_reconciliation")


def require_historical_objects(repo, release, records):
    if release["record_mode"] != "post_hoc":
        return
    keys = ("proposals", "closed", "deferred") if release["release_line"].startswith("support/") else (
        "proposals", "fixed", "closed", "deferred")
    identifiers = {item for record in records for key in keys for item in record.get(key, [])}
    if not identifiers:
        return
    head = release["release_commit"]
    old, current = {}, {}
    for rel in git(repo, "ls-tree", "-r", "--name-only", head, "--", "docs/proposals", "docs/bugs").stdout.splitlines():
        if not rel.endswith(".md"):
            continue
        meta, body = metadata(git(repo, "show", f"{head}:{rel}").stdout)
        if meta.get("id") in identifiers:
            old[meta["id"]] = (meta, body)
    for root in (repo / "docs/proposals", repo / "docs/bugs"):
        for path in root.rglob("*.md"):
            meta, body = read_frontmatter(path)
            if meta.get("id") in identifiers:
                current[meta["id"]] = (meta, body)
    progression = {"status", "released_in", "fixed_in", "found_in"}
    for identifier in identifiers:
        if identifier not in old or identifier not in current:
            raise MDFError("历史对象归属缺失，不能根据当前对象补造", code="ambiguous_release", details={"id": identifier})
        before, old_body = old[identifier]
        now, body = current[identifier]
        same_fields = {k: v for k, v in before.items() if k not in progression} == {k: v for k, v in now.items() if k not in progression}
        reopened = before.get("status") in {"closed", "released", "rejected"} and now.get("status") != before.get("status")
        if not same_fields or old_body != body or reopened:
            raise MDFError("当前对象已继续演进，历史归属须先澄清；不改写当前状态", code="ambiguous_release", details={"id": identifier})
