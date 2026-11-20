"""交付 code-review 的范围、体积与 clear commit。"""
import math

from mdf_core.execution.modules import load_modules
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.foundation.paths import load_manifest
from mdf_core.foundation.yamlutil import parse_yaml
from mdf_core.lifecycle.delivery_state import locate
from mdf_core.reviewing.context import effective_rules, fingerprint
from mdf_core.reviewing.scope import review_document, review_changes
from mdf_core.workspace import clear_commits
from mdf_core.workspace.gitutil import branch_details, git_is_clean, repo_path, require_git_root
from mdf_core.workspace.merge_policy import git, manifest_at, sha
from mdf_core.workspace.project_rules import load_project_rule
from mdf_core.workspace.workflow_policy import trunk_branch

LINES_PER_REVIEWER = 1000


def delivery_of(repo):
    try:
        return locate(repo)[1]
    except MDFError:
        return None


def left_endpoint(repo, against, data, initial_base=None):
    if against:
        return sha(repo, against)
    if data is None:
        raise MDFError("非交付分支需要 --against 指定审查左端点", code="missing_review_base")
    if branch_details(data["branch"])["kind"] == "release":
        version = manifest_at(repo, trunk_branch(repo)).get("versioning", {}).get("latest_release")
        if not version:
            if initial_base:
                return sha(repo, initial_base)
            raise MDFError("首次 release 需要 --initial-base 指定审查左端点", code="missing_review_base")
        return sha(repo, f"refs/tags/v{version}")
    return sha(repo, data["start_commit"])


def rule_changes(repo, base, head, dirty):
    paths = {".mdf/modules.yaml", "AGENTS.md"}
    old_manifest = git(repo, "show", f"{base}:.mdf/manifest.yaml", check=False)
    old = parse_yaml(old_manifest.stdout) if not old_manifest.returncode else {}
    new = load_manifest(repo) if dirty else manifest_at(repo, head)
    old_rule = (old.get("rules") or {}).get("code-review")
    new_rule = (new.get("rules") or {}).get("code-review")
    paths.update(p for p in (old_rule, new_rule) if p)
    return old_rule != new_rule or bool(clear_commits.changed_paths(repo, base, head, dirty=dirty) & paths)


def numstat(repo, left, head, paths, dirty):
    if not paths:
        return []
    pathspec = [":(literal)" + p for p in paths]
    options = ("--no-renames", "--numstat", "-z")
    ranges = [("--cached", left), ()] if dirty else [(left, head)]
    rows = {}
    for args in ranges:
        out = git(repo, "diff", *options, *args, "--", *pathspec).stdout
        for row in filter(None, out.split("\0")):
            added, deleted, path = row.split("\t", 2)
            item = rows.setdefault(path, {"path": path, "added": 0, "deleted": 0})
            for key, value in (("added", added), ("deleted", deleted)):
                item[key] = None if value == "-" or item[key] is None else item[key] + int(value)
    if dirty:
        untracked = git(repo, "ls-files", "--others", "--exclude-standard", "-z", "--", *pathspec).stdout
        for path in filter(None, untracked.split("\0")):
            diff = git(repo, "diff", "--no-index", "--numstat", "--", "/dev/null", path, check=False)
            if diff.returncode == 1:
                added = diff.stdout.split("\t", 1)[0]
                if added.isdecimal():
                    item = rows.setdefault(path, {"path": path, "added": 0, "deleted": 0})
                    if item["added"] is not None:
                        item["added"] += int(added)
    return [rows.get(p, {"path": p, "added": None, "deleted": None}) for p in paths]


def build(repo, against, force, initial_base=None):
    data = delivery_of(repo)
    head = sha(repo, "HEAD")
    dirty = not git_is_clean(repo)
    rules, config = effective_rules(repo, head, head)
    clear = clear_commits.load(repo, "code_review")
    changed_rules = bool(clear and rule_changes(repo, clear, head, dirty))
    left = (clear if clear and data and not (against or force or changed_rules)
            else left_endpoint(repo, against, data, initial_base))
    if dirty:
        config = load_modules(repo)
        rules.update(project=load_project_rule(repo, load_manifest(repo), "code-review"),
                     modules=(repo / ".mdf/modules.yaml").read_text(encoding="utf-8"),
                     agents=(repo / "AGENTS.md").read_text(encoding="utf-8") if (repo / "AGENTS.md").is_file() else None)
        rules["scope"] = {"modules": rules["modules"]}
        changed = clear_commits.changed_paths(repo, left, dirty=True)
        paths = sorted(p for p in changed if config.owns(p) and not review_document(p) and not config.is_ignored(p))
    else:
        paths, _ = review_changes(repo, left, head, config)
    rows = numstat(repo, left, head, paths, dirty)
    lines = sum((r["added"] or 0) + (r["deleted"] or 0) for r in rows)
    skip = not dirty and not paths and not (force or changed_rules)
    reviewers = 0 if skip else max(1, math.ceil(lines / LINES_PER_REVIEWER))
    return {"left": left, "head": head, "policy_ref": head, "paths": paths, "net_increment": paths,
            "clear_commit": clear, "dirty": dirty, "rules_changed": changed_rules, "numstat": rows, "skip_review": skip,
            "size": {"lines": lines, "files": len(paths), "per_reviewer": LINES_PER_REVIEWER, "reviewers": reviewers},
            "project_rules": rules["project"], "rules_sha256": fingerprint(rules), "force": force}


def command_review_prepare(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    result = build(repo, args.against, args.force, args.initial_base)
    emit({"ok": True, "operation": "review-prepare", "result": result})


def command_review_record(args):
    """由完成语义审查的 owner 调用；只接受完整交付范围或完整 clear 增量。"""
    repo = repo_path(args.repo)
    require_git_root(repo)
    data = delivery_of(repo)
    left, head = sha(repo, args.against), sha(repo, args.head)
    clear = clear_commits.load(repo, "code_review")
    recorded = False
    if data and git_is_clean(repo) and args.head == head == sha(repo, "HEAD"):
        from mdf_core.reviewing.scope import source_modules
        config, _ = source_modules(repo, head)
        if args.failed:
            if clear and not rule_changes(repo, clear, head, False) and not review_changes(repo, clear, head, config)[0]:
                clear_commits.invalidate(repo, "code_review", head, expected=clear)
        else:
            normal = left if left == clear else left_endpoint(repo, None, data, args.initial_base)
            remaining, _ = review_changes(repo, clear or normal, head, config)
            baseline_delta = clear_commits.changed_paths(repo, left, clear) if clear and left != clear else set()
            if left in {clear, normal} and not baseline_delta.intersection(remaining):
                recorded = clear_commits.record(repo, "code_review", head, expected=clear)
    emit({"ok": True, "operation": "review-record", "result": {"recorded": recorded}})
