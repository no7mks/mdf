"""外部证据必须绑定固定候选，并逐项声明覆盖、结果和可追溯来源。"""
from urllib.parse import urlparse

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.delivery_state import safe
from mdf_core.workspace.merge_policy import sha, git


def require_evidence(repo, value, head, required):
    if not isinstance(value, dict) or value.get("commit") != head or value.get("tree") != git(repo, "rev-parse", f"{head}^{{tree}}").stdout.strip():
        raise MDFError("外部 evidence 与当前候选 commit/tree 不符", code="external_evidence_required")
    checks = value.get("checks")
    if not isinstance(checks, list):
        raise MDFError("外部 evidence 缺少 checks", code="external_evidence_required")
    covered = set()
    for check in checks:
        if (not isinstance(check, dict) or check.get("passed") is not True or not isinstance(check.get("scope"), list)
                or not check["scope"] or any(not isinstance(v, str) or not v.strip() for v in check["scope"])):
            raise MDFError("外部检查须包含通过结论及非空 scope", code="external_evidence_required")
        sources = check.get("artifacts")
        if not isinstance(sources, list) or not sources:
            raise MDFError("外部检查缺少可追溯 artifact", code="external_evidence_required")
        for source in sources:
            if not isinstance(source, str) or not source.strip():
                raise MDFError("artifact 必须为链接或本地记录", code="external_evidence_required")
            parsed = urlparse(source)
            if parsed.scheme in {"https", "http"} and parsed.netloc:
                continue
            path = safe(repo, source)
            rel = path.relative_to(repo).as_posix()
            if not path.is_file() or git(repo, "cat-file", "-e", f"{head}:{rel}", check=False).returncode:
                raise MDFError("本地 evidence artifact 不存在", code="external_evidence_required")
        covered.update(check["scope"])
    if not set(required) <= covered:
        raise MDFError("外部 evidence 未覆盖所需检查", code="external_evidence_required", details={"missing": sorted(set(required) - covered)})
    return value


def require_object_outcomes(repo, meta):
    from mdf_core.lifecycle.closeout_objects import active_objects
    objects = active_objects(repo)
    expected = {"proposals": {"released"}, "fixed": {"closed"}, "closed": {"closed"}}
    if str(meta.get("release_line", "")).startswith("support/"):
        # support 继续由原 Trunk-First 契约核对 trunk Bug，不修改真源。
        expected.pop("fixed")
    for field, statuses in expected.items():
        for identifier in meta.get(field, []):
            if identifier not in objects or objects[identifier][2].get("status") not in statuses:
                raise MDFError("对象尚未满足原状态转换门槛；先完成对应验证与审查", code="object_evidence_required",
                               details={"id": identifier, "outcome": field})
