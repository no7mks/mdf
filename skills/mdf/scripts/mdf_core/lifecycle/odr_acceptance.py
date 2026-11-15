"""ODR 统一验收与来源上下文：不补齐 feature 的交付进度。"""
import re

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.delivery_state import read_json, safe, split_objectives_steps
from mdf_core.workspace.gitutil import ensure_clean

ACCEPTANCE = "ODR 统一验收"
INCLUSION_BASE = re.compile(r"(?m)^<!-- odr-inclusion-base: ([0-9a-f]{40}) -->$")


def set_acceptance(text, checked):
    before, steps, after = split_objectives_steps(text)
    mark = "x" if checked else " "
    steps = re.sub(rf"(?m)^- \[[ x]\] {ACCEPTANCE}$", f"- [{mark}] {ACCEPTANCE}", steps)
    return before + steps + after


def feature_records(repo, root, data):
    container = root if root.parent.name == "changes" else root.parent
    result = {}
    for source in data.get("features", []):
        folder = safe(repo, container / source.split("/", 1)[1])
        record = read_json(safe(repo, folder / "delivery.json"))
        from mdf_core.workspace.workflow_policy import trunk_branch
        if (record.get("branch") != source or record.get("base_branch") != trunk_branch(repo)
                or record.get("target") != data["branch"]):
            raise MDFError("ODR 来源身份不匹配", code="invalid_delivery")
        result[source] = (folder, record)
    return result


def require_acceptance(repo, root, data, *, accepted=True, included=()):
    from mdf_core.execution.verification import recorded_suites, required_suites, suites_cover
    objectives = safe(repo, root / "objectives.md").read_text()
    _, checklist, _ = split_objectives_steps(objectives)
    checked = re.findall(r"(?m)^- \[x\] (.+)$", checklist)
    stages = ("lint", "code-review", "verify branch", "fact audit")
    if any(not any(item == stage or item.startswith(stage + "（") for item in checked) for stage in stages):
        raise MDFError("ODR 须先完成 lint、review、verify branch 与 fact audit", code="odr_acceptance_pending")
    if accepted and ACCEPTANCE not in checked:
        raise MDFError("ODR 尚未确认统一验收，请执行 delivery accept", code="odr_acceptance_pending")
    for name in ("code-review.md", "fact-audit.md", "verification-report.json"):
        path = safe(repo, root / name)
        if not path.is_file() or not path.read_text().strip():
            raise MDFError(f"ODR 缺少 {name}", code="odr_acceptance_pending")
    report = read_json(root / "verification-report.json")
    if (report.get("branch") != data["branch"] or report.get("scope") != "branch"
            or report.get("all_passed") is not True
            or not suites_cover(recorded_suites(report), required_suites("on-demand-release"))):
        raise MDFError("ODR 需要通过整版 release suite", code="odr_acceptance_pending")
    release_summary(repo, root, data)
    if accepted:
        from mdf_core.workspace.merge_policy import ancestor
        bases = INCLUSION_BASE.findall(objectives)
        if (len(bases) != 1 or not ancestor(repo, bases[0], "HEAD")
                or any(ancestor(repo, commit, "HEAD") and not ancestor(repo, commit, bases[0]) for commit in included)):
            raise MDFError("新增纳入范围尚未统一验收", code="odr_acceptance_pending")
        from mdf_core.documents.proposals import records
        proposals = records(repo)
        for _folder, record in feature_records(repo, root, data).values():
            if not record.get("manual"):
                proposal = proposals.get(record.get("proposal"))
                if proposal is None or proposal[1].get("status") not in {"implemented", "released"}:
                    raise MDFError("ODR PRP 尚未完成统一验收", code="odr_acceptance_pending")


def accept(repo):
    from mdf_core.lifecycle.delivery_state import locate
    from mdf_core.lifecycle.late_decision import checkpoint
    from mdf_core.documents.proposals import records
    from mdf_core.foundation.yamlutil import set_frontmatter_field
    from mdf_core.inspection.validate_records import unsatisfied_depends_on
    ensure_clean(repo)
    checkpoint(repo, required=True)
    root, data = locate(repo)
    require_acceptance(repo, root, data, accepted=False)
    proposals = records(repo)
    selected = set()
    for _folder, record in feature_records(repo, root, data).values():
        if record.get("manual"):
            continue
        identifier = record.get("proposal")
        if identifier not in proposals:
            raise MDFError("ODR 来源 PRP 缺失", code="invalid_proposal")
        metadata = proposals[identifier][1]
        if metadata.get("status") not in {"ready", "implemented"} and not current_candidate(repo, root, data, metadata):
            raise MDFError("ODR 来源 PRP 状态不正确", code="invalid_proposal")
        selected.add(identifier)
    projected = {identifier: {**meta, **({"status": "implemented"} if identifier in selected else {})}
                 for identifier, (_path, meta, _body) in proposals.items()}
    for identifier in selected:
        if unsatisfied_depends_on(projected[identifier].get("depends_on", []), projected):
            raise MDFError("ODR 来源存在未满足的 PRP 依赖", code="unreleased_dependency")
    path = safe(repo, root / "objectives.md")
    text = path.read_text()
    _, checklist, _ = split_objectives_steps(text)
    if not re.search(rf"(?m)^- \[[ x]\] {ACCEPTANCE}$", checklist):
        raise MDFError("ODR 缺少统一验收步骤", code="invalid_delivery")
    # 全部检查通过后才写入，保留 feature 的 objectives 与报告原样。
    for identifier in selected:
        proposal_path, meta, _ = proposals[identifier]
        if meta.get("status") != "released":
            proposal_text = proposal_path.read_bytes().decode("utf-8")
            updated = set_frontmatter_field(proposal_text, "status", "implemented")
            proposal_path.write_bytes(updated.encode("utf-8"))
    from mdf_core.workspace.merge_policy import git
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    text = INCLUSION_BASE.sub("", text).rstrip()
    text = set_acceptance(text, True)
    path.write_text(text + f"\n\n<!-- odr-inclusion-base: {base} -->\n")
    return {"accepted": True, "proposals": sorted(selected)}


def source_contexts(repo, version):
    root = safe(repo, repo / "changes/unreleased" / version)
    data = read_json(root / "delivery.json")
    return feature_records(repo, root, data)


def current_candidate(repo, root, data, metadata):
    """只承认当前尚未发布的 PR 候选已经归档的 PRP。"""
    from mdf_core.workspace.merge_policy import configured, git
    from mdf_core.foundation.yamlutil import read_frontmatter
    version = data["branch"].split("/", 1)[1]
    if (root != repo / "changes" / version or configured(repo)["mode"] != "pr"
            or metadata.get("status") != "released" or metadata.get("released_in") != version
            or git(repo, "rev-parse", "--verify", f"refs/tags/v{version}", check=False).returncode == 0):
        return False
    change, _ = read_frontmatter(safe(repo, root / "CHANGE.md"))
    return (change.get("version") == version and change.get("source_branch") == data["branch"]
            and change.get("change_kind") == "on-demand-release" and metadata.get("id") in change.get("proposals", []))


def release_summary(repo, root, data):
    """无 child Change 的贡献使用 ODR 自己的发布声明，不猜测分类。"""
    from mdf_core.foundation.constants import CHANGELOG_CATEGORIES
    path = safe(repo, root / "release-notes.json")
    required = bool(data.get("scope")) or any(
        not (folder / "CHANGE.md").is_file() for folder, _ in feature_records(repo, root, data).values())
    if not path.is_file():
        if required:
            raise MDFError("ODR 需要 release-notes.json 声明发布分类与 breaking", code="invalid_release_summary")
        return {}, False
    summary = read_json(path)
    notes, breaking = summary.get("release_notes"), summary.get("breaking")
    if (set(summary) != {"release_notes", "breaking"} or not isinstance(breaking, bool)
            or not isinstance(notes, dict) or not notes or set(notes) - set(CHANGELOG_CATEGORIES)
            or any(not isinstance(values, list) or not values
                   or any(not isinstance(value, str) or not value.strip() for value in values) for values in notes.values())
            or ("Removed" in notes and not breaking)):
        raise MDFError("ODR 发布声明需要非空分类列表、boolean breaking；Removed 要求 breaking=true",
                       code="invalid_release_summary")
    if root.parent == repo / "changes":
        from mdf_core.foundation.yamlutil import read_frontmatter
        from mdf_core.foundation.textutil import stable_semver
        from mdf_core.foundation.semver import bump_kind, required_bump
        change, _ = read_frontmatter(safe(repo, root / "CHANGE.md"))
        candidate_notes = change.get("release_notes")
        if (not isinstance(candidate_notes, dict)
                or any(not set(values) <= set(candidate_notes.get(category, [])) for category, values in notes.items())
                or (breaking and change.get("breaking") is not True)):
            raise MDFError("先将候选 Change 与 ODR 发布声明对齐，再重新验收", code="invalid_release_summary")
        previous = change.get("previous_version")
        previous = (0, 0, 0) if previous in (None, "none") else stable_semver(previous)
        candidate = stable_semver(root.name)
        if previous is None or candidate is None:
            raise MDFError("候选版本信息无效", code="invalid_release_summary")
        rank = {"patch": 1, "minor": 2, "major": 3}
        required = required_bump(previous, set(candidate_notes), change.get("breaking") is True)
        if rank[bump_kind(previous, candidate)] < rank[required]:
            raise MDFError("候选版本不满足发布声明要求", code="insufficient_bump")
    return notes, breaking


def invalidate(repo, target):
    """实际本地纳入新提交时撤销目标 ODR 的验收勾选，随 merge 提交。"""
    from mdf_core.workspace.merge_policy import git
    version = target.split("/", 1)[1]
    root = repo / "changes/unreleased" / version
    if not (root / "delivery.json").is_file():
        root = repo / "changes" / version
    path = safe(repo, root / "objectives.md")
    original = path.read_text()
    updated = set_acceptance(original, False)
    if updated != original:
        path.write_text(updated)
        git(repo, "add", "--", str(path.relative_to(repo)))
