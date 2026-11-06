"""ODR 统一验收与来源上下文：不补齐 feature 的交付进度。"""
import re

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.delivery_state import read_json, safe
from mdf_core.workspace.gitutil import ensure_clean

ACCEPTANCE = "ODR 统一验收"


def feature_records(repo, root, data):
    container = root if root.parent.name == "changes" else root.parent
    result = {}
    for source in data.get("features", []):
        folder = safe(repo, container / source.split("/", 1)[1])
        record = read_json(safe(repo, folder / "delivery.json"))
        if (record.get("branch") != source or record.get("base_branch") != "master"
                or record.get("target") != data["branch"]):
            raise MDFError("ODR 来源身份不匹配", code="invalid_delivery")
        result[source] = (folder, record)
    return result


def require_acceptance(repo, root, data, *, accepted=True):
    from mdf_core.execution.verification import recorded_suites, required_suites, suites_cover
    objectives = safe(repo, root / "objectives.md").read_text()
    checked = re.findall(r"(?m)^- \[x\] (.+)$", objectives)
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
    if accepted:
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
    from mdf_core.documents.html_documents import update_metadata
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
        if identifier not in proposals or proposals[identifier][1].get("status") not in {"ready", "implemented"}:
            raise MDFError("ODR 来源 PRP 状态不正确", code="invalid_proposal")
        selected.add(identifier)
    projected = {identifier: {**meta, **({"status": "implemented"} if identifier in selected else {})}
                 for identifier, (_path, meta, _body) in proposals.items()}
    for identifier in selected:
        if unsatisfied_depends_on(projected[identifier].get("depends_on", []), projected):
            raise MDFError("ODR 来源存在未满足的 PRP 依赖", code="unreleased_dependency")
    path = safe(repo, root / "objectives.md")
    text = path.read_text()
    if not re.search(rf"(?m)^- \[[ x]\] {ACCEPTANCE}$", text):
        raise MDFError("ODR 缺少统一验收步骤", code="invalid_delivery")
    # 全部检查通过后才写入，保留 feature 的 objectives 与报告原样。
    for identifier in selected:
        proposal_path, meta, _ = proposals[identifier]
        proposal_path.write_text(update_metadata(proposal_path.read_text(), {**meta, "status": "implemented"}))
    path.write_text(text.replace(f"- [ ] {ACCEPTANCE}", f"- [x] {ACCEPTANCE}"))
    return {"accepted": True, "proposals": sorted(selected)}


def source_contexts(repo, version):
    root = safe(repo, repo / "changes/unreleased" / version)
    data = read_json(root / "delivery.json")
    return feature_records(repo, root, data)
