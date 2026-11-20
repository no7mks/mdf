"""交付材料、对象状态和版本聚合的统一完成入口。"""
import contextlib
import io
import json

from mdf_core.foundation.errors import MDFError, emit, has_errors, serialize_findings
from mdf_core.lifecycle.delivery_state import locate, read_json, write_json
from mdf_core.lifecycle.stage_route import parse_items, _tick
from mdf_core.workspace.gitutil import branch_details, current_branch, ensure_clean, repo_path, require_git_root
from mdf_core.workspace.merge_policy import git, sha, ancestor
from mdf_core.workspace.squash import common_dir


def record_path(repo, source):
    return common_dir(repo) / "mdf/consolidate" / (source + ".json")


def require_consolidated(repo, source):
    path = record_path(repo, source)
    state = read_json(path) if path.is_file() else {}
    head = state.get("head")
    if not head or git(repo, "cat-file", "-e", head, check=False).returncode:
        raise MDFError("先执行 consolidate 收敛交付材料", code="consolidation_required")
    changed = git(repo, "diff", "--name-only", head, "HEAD").stdout.splitlines()
    if changed:
        raise MDFError("consolidate 后有新增内容，完成增量验收并重新 consolidate", code="consolidation_required")
    return head


def update_child_objects(repo, root, data):
    from mdf_core.foundation.yamlutil import read_frontmatter, set_frontmatter_field
    from mdf_core.lifecycle.closeout_objects import active_objects
    path = root / "CHANGE.md"
    if not path.is_file():
        raise MDFError("consolidate 需要本次 CHANGE.md", code="missing_change")
    change, _ = read_frontmatter(path)
    if change.get("source_branch") != data["branch"]:
        raise MDFError("Change 与交付分支不符", code="invalid_change")
    objects = active_objects(repo)
    owned = set()
    proposal = data.get("proposal")
    from mdf_core.lifecycle.late_decision import target_for
    deferred_prp = target_for(repo, data["branch"], data=data).startswith("on-demand-release/")
    if proposal and not deferred_prp:
        if change.get("proposals") != [proposal] or proposal not in objects:
            raise MDFError("Change 必须引用本次唯一 PRP", code="invalid_proposal")
        kind, path, meta = objects[proposal]
        if kind != "proposal" or meta.get("status") not in {"ready", "implemented"}:
            raise MDFError("PRP 尚未就绪或状态不符", code="invalid_proposal")
        path.write_text(set_frontmatter_field(path.read_text(), "status", "implemented"))
        owned.add(path.relative_to(repo).as_posix())
    for identifier in change.get("fixed", []):
        if identifier not in objects:
            raise MDFError("Change 引用了不存在的 Bug", code="invalid_change")
        kind, path, meta = objects[identifier]
        if kind != "bug" or meta.get("status") not in {"open", "fixed", "closed"}:
            raise MDFError("修复 outcome 与 Bug 状态不符", code="invalid_change")
        if meta["status"] == "open":
            report = read_json(root / "verification-report.json")
            if report.get("all_passed") is not True:
                raise MDFError("更新 fixed 需要通过的验收证据", code="verification_report_not_reusable")
            path.write_text(set_frontmatter_field(path.read_text(), "status", "fixed"))
            owned.add(path.relative_to(repo).as_posix())
    return owned


def release_paths(repo, result, version):
    owned = {"CHANGELOG.md", ".mdf/manifest.yaml", f"changes/{version}/CHANGE.md", f"changes/{version}/delivery.json"}
    owned.update(result.get("rewrites", []))
    from mdf_core.lifecycle.closeout_objects import active_objects
    objects = active_objects(repo)
    for identifiers in result.get("outcomes", {}).values():
        for identifier in identifiers:
            if identifier in objects:
                owned.add(objects[identifier][1].relative_to(repo).as_posix())
    for move in result.get("moves", []):
        source, target = move["from"], move["to"]
        for path in filter(None, git(repo, "ls-files", "-z", "--", source).stdout.split("\0")):
            owned.add(path)
            owned.add(target + path[len(source):])
    return owned


def consolidate(repo, args):
    from mdf_core.inspection import doctor
    ensure_clean(repo)
    source = current_branch(repo)
    root, data = locate(repo)
    if data["branch"] != source:
        raise MDFError("该阶段须在交付 owner 工作分支执行", code="stage_branch")
    path = root / "objectives.md"
    text = path.read_text()
    items = parse_items(text)
    item = next((i for i in items if i["name"] == "consolidate"), None)
    if item is None:
        raise MDFError("objectives 缺少 consolidate", code="invalid_objectives")
    pending = [i["name"] for i in items[:items.index(item)] if not i["checked"]]
    if pending:
        raise MDFError("consolidate 前置未完成", code="stage_prerequisite", details={"pending": pending})
    details = branch_details(source)
    versioned = details["kind"] in {"release", "hotfix", "on-demand-release"}
    version = details["version"] or data.get("version")
    result = None
    owned = set()
    if versioned:
        if not (repo / "changes" / str(version) / "CHANGE.md").exists():
            from mdf_core.lifecycle.commands_release import command_release_closeout
            args.require_release_notes = True
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                command_release_closeout(args)
            result = json.loads(captured.getvalue())
            owned.update(release_paths(repo, result, result["version"]))
    else:
        owned.update(update_child_objects(repo, root, data))
    root, data = locate(repo)
    version = details["version"] or data.get("version")
    if versioned:
        from mdf_core.lifecycle.closeout_render import changelog_excerpt
        changelog_excerpt((repo / "CHANGELOG.md").read_text(), version)
    findings = doctor.collect_findings(repo, full=True) if result is None else []
    if has_errors(findings):
        raise MDFError("consolidate 文档检查未通过，保留材料供修复", code="post_validation_failed",
                       details={"findings": serialize_findings(findings)})
    path = root / "objectives.md"
    text = path.read_text()
    item = next(i for i in parse_items(text) if i["name"] == "consolidate")
    path.write_text(_tick(text, item, "consolidate", {}))
    owned.add(path.relative_to(repo).as_posix())
    from mdf_core.lifecycle.commands_release import written_paths
    changed = written_paths(repo)
    foreign = sorted(set(changed) - owned)
    if foreign:
        raise MDFError("出现本次 consolidate 之外的改动，保留现场", code="unrelated_staged_changes", details={"paths": foreign})
    if changed:
        git(repo, "add", "-A", "--", *changed)
        git(repo, "commit", "--only", "-m", "docs(delivery): 收敛交付材料与对象记录", "--", *changed)
    head = sha(repo, "HEAD")
    write_json(record_path(repo, source), {"head": head, "version": version, "incremental": args.incremental})
    if not args.incremental:
        from mdf_core.lifecycle.target_integration import state_path
        integration_path = state_path(repo, source)
        state = read_json(integration_path) if integration_path.is_file() else {}
        if not state or state.get("accepted_head"):
            write_json(integration_path, {"base": head})
    return {"completed": True, "head": sha(repo, "HEAD"), "release": result}


def command_consolidate(args):
    from mdf_core.lifecycle.pull_finish import finish_lock
    repo = repo_path(args.repo)
    require_git_root(repo)
    with finish_lock(repo):
        result = consolidate(repo, args)
    emit({"ok": True, "operation": "consolidate", **result})
