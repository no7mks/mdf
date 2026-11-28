"""按固定历史或候选生成版本记录；预先验证全部写入，拒绝半归档。"""
from datetime import date
import json
from pathlib import Path
import re
import tempfile

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.semver import bump_kind, required_bump
from mdf_core.foundation.textutil import stable_semver
from mdf_core.lifecycle.closeout_render import (
    aggregate_change_metadata, render_version_change, update_changelog_text, update_manifest_release,
)
from mdf_core.lifecycle.delivery_state import read_json, safe, write_json
from mdf_core.reconciliation.context import metadata, state_path
from mdf_core.reconciliation.evidence import require_evidence
from mdf_core.reconciliation.history import OUTCOMES, children, document, plan_archive, tree_files, write_snapshot, merge_increment
from mdf_core.workspace.changelog_sync import insert_section, section
from mdf_core.workspace.gitutil import ensure_clean
from mdf_core.workspace.merge_policy import ancestor, git, sha
from mdf_core.workspace.workflow_policy import trunk_branch


def interval_commits(repo, release):
    head = release.get("release_commit") or release["head"]
    rev = f"{release['base']}..{head}" if release.get("base") else head
    return git(repo, "rev-list", "--reverse", rev).stdout.split()


def supplied_changes(repo, release, spec):
    commits = set(interval_commits(repo, release))
    changes = spec.get("changes")
    if not isinstance(changes, list) or not changes:
        raise MDFError("历史没有 Change，须按固定区间提供可核实的 changes", code="reconciliation_required",
                       details={"commits": sorted(commits)})
    snapshots, covered = {}, set()
    for change in changes:
        slug = change.get("slug")
        owned = change.get("commits")
        if (not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)
                or slug in snapshots or not isinstance(owned, list) or not owned or not set(owned) <= commits):
            raise MDFError("changes 需要唯一 slug 与区间内 commit", code="invalid_reconciliation")
        if covered & set(owned):
            raise MDFError("同一 commit 被重复分配到多个 Change", code="invalid_reconciliation")
        covered.update(owned)
        notes = change.get("release_notes")
        if not isinstance(notes, dict) or not notes:
            raise MDFError("changes 需要已查证的 release_notes，不能用平台标题猜测", code="invalid_reconciliation")
        meta = {"change_kind": "fix", "source_branch": f"adhoc/{slug}",
                **{key: change.get(key, []) for key in OUTCOMES}, "release_notes": notes,
                "breaking": change.get("breaking", False),
                "evidence": {"tests": [], "commands": [], "artifacts": [f"git:{commit}" for commit in owned]}}
        if meta["proposals"]:
            raise MDFError("区间补建不补造 PRP 归属；已有 PRP 使用原 Change 快照", code="invalid_reconciliation")
        body = "\n# 已核实的区间成果\n\n## 结果\n\n" + "\n".join(f"- {v}" for values in notes.values() for v in values)
        body += "\n\n## 已更新的当前文档\n\n当前事实另行核对。\n\n## 已知偏差\n\n外部历史验收按原始证据记录。\n"
        snapshots[slug] = {"CHANGE.md": document(meta, body)}
    omitted = set(spec.get("excluded_commits", []))
    if omitted:
        reasons = spec.get("exclusions", {})
        if any(not isinstance(reasons.get(c), str) or not reasons[c].strip() for c in omitted):
            raise MDFError("不生成 Change 的 commit 须逐项说明核对依据", code="invalid_reconciliation")
    if covered & omitted or covered | omitted != commits:
        raise MDFError("区间对账未完整覆盖 commits", code="invalid_reconciliation")
    return snapshots


def prepare_records(repo, release, spec, release_date):
    version = release["version"]
    historical = release["record_mode"] == "post_hoc"
    head = release.get("release_commit") or release["head"]
    original_root = tree_files(repo, head, f"changes/{version}/CHANGE.md")
    original_meta = metadata(original_root[f"changes/{version}/CHANGE.md"])[0] if original_root else {}
    if historical:
        kind = original_meta.get("change_kind") or spec.get("change_kind", release["kind"])
        source = original_meta.get("source_branch") or spec.get("source_branch", release["source"])
        if kind not in {"release", "hotfix"}:
            raise MDFError("历史发布类型须为 release 或 hotfix", code="invalid_reconciliation")
        if original_meta and any(key in spec and spec[key] != original_meta.get(key) for key in ("change_kind", "source_branch")):
            raise MDFError("记录说明与历史发布身份冲突", code="invalid_reconciliation")
        release = {**release, "kind": kind, "source": source}
    if spec.get("commit") != head:
        raise MDFError("记录说明必须绑定 inspect 给出的固定 commit", code="reconcile_state_changed")
    snapshots = children(repo, release) if release["kind"] == "release" else {}
    if release["kind"] == "hotfix":
        if original_root:
            snapshots = {"historical-hotfix": {"CHANGE.md": original_root[f"changes/{version}/CHANGE.md"]}}
    if not snapshots:
        snapshots = supplied_changes(repo, release, spec)
    elif not historical and spec.get("changes"):
        incoming = supplied_changes(repo, release, spec)
        if release["kind"] == "hotfix":
            # hotfix 仍然只生成版本根；多个区间项先按原聚合规则汇总。
            notes, breaking, proposals, fixed, closed, deferred, adrs, evidence = aggregate_change_metadata(
                metadata(files["CHANGE.md"])[0] for files in incoming.values())
            additions = {"release_notes": {k: v for k, v in notes.items() if v} or "none", "breaking": breaking,
                         "proposals": sorted(proposals), "fixed": sorted(fixed), "closed": sorted(closed),
                         "deferred": sorted(deferred), "adrs": sorted(adrs), "evidence": evidence}
            snapshots = {"historical-hotfix": {"CHANGE.md": merge_increment(
                original_root[f"changes/{version}/CHANGE.md"], document(additions, ""))}}
        else:
            for slug, files in incoming.items():
                if slug in snapshots:
                    files = {**snapshots[slug], "CHANGE.md": merge_increment(snapshots[slug]["CHANGE.md"], files["CHANGE.md"])}
                snapshots[slug] = files
    metas = [metadata(files["CHANGE.md"])[0] for files in snapshots.values()]
    from mdf_core.reconciliation.objects import require_historical_objects
    require_historical_objects(repo, release, metas)
    notes, breaking, proposals, fixed, closed, deferred, adrs, evidence = aggregate_change_metadata(metas)
    categories = {key for key, values in notes.items() if values}
    previous = release["previous_version"]
    before = (0, 0, 0) if previous == "none" else stable_semver(previous)
    minimum, actual = required_bump(before, categories or {"none"}, breaking), bump_kind(before, stable_semver(version))
    if {"patch": 1, "minor": 2, "major": 3}[actual] < {"patch": 1, "minor": 2, "major": 3}[minimum]:
        raise MDFError("版本提升不满足已查证的变更类别", code="invalid_version")
    is_hotfix = release["kind"] == "hotfix"
    writes, removals = ({}, []) if is_hotfix else plan_archive(repo, release, snapshots)
    root = render_version_change(
        version, None if previous == "none" else previous, release_date, release["kind"], [] if is_hotfix else sorted(snapshots),
        categories, breaking, minimum, actual, [], proposals, fixed, closed, deferred, adrs, {}, [], {},
        release_notes=notes, evidence=evidence, source_branch=release["source"],
    )
    meta, body = metadata(root)
    meta.update(record_mode=release["record_mode"], release_line=release["release_line"])
    if historical:
        meta["release_commit"] = head
        if release.get("release_tag"):
            meta["release_tag"] = release["release_tag"]
    trunk_fixes = original_meta.get("trunk_fixes") or spec.get("trunk_fixes")
    if trunk_fixes:
        meta["trunk_fixes"] = trunk_fixes
    body = body.replace("发布收口已完成。", "已记录可核实成果；对象状态与发布验收另行核对。")
    body = body.replace("## 已知偏差\n\n无。", "## 已知偏差\n\n本记录不证明外部测试、code-review 或对象转换已通过；缺失的验收证据须另行补齐。")
    body = body.replace("确定性的全量审计：已通过（由 Core 验证）。", "历史材料一致性由 Core 检查；当前 fact 以独立证据为准。")
    root_path = f"changes/{version}/CHANGE.md"
    root_text = document(meta, body)
    existing = repo / root_path
    if existing.exists():
        old, _ = metadata(existing.read_text())
        if old.get("record_mode") != release["record_mode"] or (historical and old.get("release_commit") != head):
            raise MDFError("已有版本记录归属不同", code="collision")
    writes[root_path] = root_text
    reconciliation = "# 发布区间对账\n\n" + f"- 固定 commit：`{head}`\n- 基线：`{release.get('base') or 'none'}`\n\n"
    reconciliation += "## 已核对 commits\n\n" + "\n".join(f"- `{c}`" for c in interval_commits(repo, release)) + "\n"
    fact = spec["fact"]
    reconciliation += f"\n## 当前事实审阅\n\n- commit：`{fact['commit']}`\n- tree：`{fact['tree']}`\n"
    reconciliation += "当前工作区的审阅不作为历史发布快照的验收。\n\n"
    reconciliation += "\n".join(f"- {artifact}" for check in fact["checks"] for artifact in check["artifacts"]) + "\n"
    writes[f"changes/{version}/release-reconciliation.md"] = reconciliation
    excerpt = section(update_changelog_text("# Changelog\n", version=version, release_date=release_date, notes=notes), version)
    changelog = (repo / "CHANGELOG.md").read_text()
    if existing.exists() and not historical:
        old_section = section(changelog, version)
        changelog = changelog.replace(old_section, excerpt, 1)
    else:
        changelog = insert_section(changelog, version, excerpt)
    writes["CHANGELOG.md"] = changelog
    from mdf_core.workspace.gitutil import current_branch
    foreign_support = (release["release_line"].startswith("support/") and current_branch(repo) != release["release_line"]
                       and release["record_mode"] != "ledgerless")
    if foreign_support:
        writes = {p: text for p, text in writes.items() if not p.startswith("changes/unreleased/")}
        removals = []
    else:
        manifest = repo / ".mdf/manifest.yaml"
        current = parse_latest(manifest.read_text())
        latest = version if not current or stable_semver(current) < stable_semver(version) else current
        writes[".mdf/manifest.yaml"] = update_manifest_release(manifest.read_text(), latest)
    return writes, removals


def parse_latest(text):
    from mdf_core.foundation.yamlutil import parse_yaml
    return parse_yaml(text).get("versioning", {}).get("latest_release")


def validate_writes(repo, writes, removals, version):
    from mdf_core.inspection.validate_change_schema import validate_change_file
    # 校验文件放在临时目录，但 Git 来源核验仍使用实际仓库。
    with tempfile.TemporaryDirectory(prefix=".mdf-reconcile-check-", dir=repo) as directory:
        for rel, text in writes.items():
            safe(repo, rel)
            if not rel.endswith("/CHANGE.md"):
                continue
            path = Path(directory) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            write_snapshot(path, text)
            findings = []
            # 结构校验使用候选文本；Git 来源校验在发布身份检查中完成。
            validate_change_file(repo, path, findings, expected_slug=version if len(Path(rel).parts) == 3 else Path(rel).parent.name,
                                 root=len(Path(rel).parts) == 3)
            if findings:
                raise MDFError("补账材料未满足现有 Change 契约", code="invalid_reconciliation",
                               details={"findings": [f.as_dict() for f in findings]})
    for rel in removals:
        safe(repo, rel)


def apply(repo, args):
    ensure_clean(repo)
    plan = read_json(state_path(repo))
    same_candidate = sha(repo, "HEAD") == plan.get("record_head")
    if args.version in plan.get("recorded_versions", []) and (plan["record_mode"] == "post_hoc" or same_candidate):
        if plan["record_mode"] == "ledgerless":
            from mdf_core.lifecycle.catchup import remote_head
            remote = remote_head(repo, plan["source"])
            if remote and not ancestor(repo, remote, "HEAD"):
                raise MDFError("远端同名分支领先；先同步并补验", code="catchup_required")
        tree = git(repo, "rev-parse", f"HEAD:changes/{args.version}").stdout.strip()
        if (tree != plan.get("record_trees", {}).get(args.version)
                or section((repo / "CHANGELOG.md").read_text(), args.version) != plan.get("record_sections", {}).get(args.version)):
            raise MDFError("已补账材料被修改；保留现场核对", code="reconcile_state_changed")
        return {"recorded": True, "already_recorded": True, "version": args.version, "head": sha(repo, "HEAD")}
    if plan.get("published"):
        raise MDFError("固定候选已发布；当前增量走审查与事实补检，不重写该版本记录", code="release_already_published")
    try:
        date.fromisoformat(args.release_date)
    except (ValueError, TypeError):
        raise MDFError("release-date 需要 YYYY-MM-DD", code="invalid_arguments") from None
    spec = read_json(Path(args.record_file)) if args.record_file else {}
    head = sha(repo, "HEAD")
    require_evidence(repo, spec.get("fact"), head, {"fact"})
    if plan["record_mode"] == "ledgerless":
        from mdf_core.lifecycle.catchup import remote_head
        remote = remote_head(repo, plan["source"])
        if remote and not ancestor(repo, remote, head):
            raise MDFError("远端同名分支领先；先同步并补验", code="catchup_required")
        release = {**plan, "head": head}
    else:
        release = next((r for r in plan["releases"] if r["version"] == args.version), None)
    if not release or release["version"] != args.version:
        raise MDFError("version 不在本次补账计划内", code="invalid_version")
    writes, removals = prepare_records(repo, release, spec, args.release_date)
    if plan["record_mode"] == "post_hoc":
        from mdf_core.execution.verification_inputs import input_patterns, is_input
        from mdf_core.workspace.reconcile_channel import MANIFEST
        patterns = input_patterns(repo)
        declared = input_patterns(repo, include_fixed=False)
        forbidden = [p for p in set(writes) | set(removals)
                     if is_input(p, declared if p == MANIFEST else patterns)]
        if forbidden:
            raise MDFError("补账计划命中验证输入，不写入", code="pm_paths_forbidden", details={"paths": sorted(forbidden)})
    validate_writes(repo, writes, removals, args.version)
    ensure_clean(repo)
    if sha(repo, "HEAD") != head:
        raise MDFError("补账计划期间 HEAD 改变", code="reconcile_state_changed")
    for rel, text in writes.items():
        path = safe(repo, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_snapshot(path, text)
    for rel in removals:
        safe(repo, rel).unlink()
    boundary = repo / "changes/unreleased"
    for parent in sorted({(repo / rel).parent for rel in removals}, key=lambda p: len(p.parts), reverse=True):
        while parent != boundary and parent.is_relative_to(boundary) and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    git(repo, "add", "-A", "--", *sorted(set(writes) | set(removals)))
    if git(repo, "diff", "--cached", "--quiet", check=False).returncode:
        expected_tree = git(repo, "write-tree").stdout.strip()
        changed = set(git(repo, "diff", "--cached", "--name-only", head).stdout.splitlines())
        if changed - (set(writes) | set(removals)):
            raise MDFError("出现不属于本次记录的暂存内容", code="reconcile_state_changed")
        git(repo, "commit", "-m", f"docs(reconcile): 核对 {args.version} 发布记录")
        if (git(repo, "show", "-s", "--format=%P", "HEAD").stdout.split() != [head]
                or git(repo, "rev-parse", "HEAD^{tree}").stdout.strip() != expected_tree):
            raise MDFError("记录提交夹带其他内容，保留现场重新核对", code="reconcile_state_changed")
    completed = list(dict.fromkeys([*plan.get("recorded_versions", []), args.version]))
    trees = {**plan.get("record_trees", {}), args.version: git(repo, "rev-parse", f"HEAD:changes/{args.version}").stdout.strip()}
    sections = {**plan.get("record_sections", {}), args.version: section((repo / "CHANGELOG.md").read_text(), args.version)}
    write_json(state_path(repo), {**plan, "recorded_versions": completed, "record_head": sha(repo, "HEAD"),
                                  "record_trees": trees, "record_sections": sections})
    return {"recorded": True, "version": args.version, "head": sha(repo, "HEAD"), "next_intent": "reconcile finish",
            "object_states_advanced": False, "publication_completed": False}
