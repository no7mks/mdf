"""历史对象归属只读核对；不回滚已演进的当前对象。"""
from pathlib import Path

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.yamlutil import read_frontmatter
from mdf_core.reconciliation.context import metadata
from mdf_core.workspace.merge_policy import git


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
