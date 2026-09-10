"""Proposal 身份、依赖图和未开工判定。"""
import json

from .errors import MDFError, serialize_findings
from .gitutil import run
from .validate_objects import iter_object_files, validate_object
from .validate_records import validate_record_references
from .yamlutil import read_frontmatter

SATISFIED = {"implemented", "released"}


def records(repo):
    result = {}
    for path in iter_object_files(repo, "proposal"):
        meta, body = read_frontmatter(path)
        if meta.get("id") in result:
            raise MDFError("Proposal ID 重复", code="invalid_proposals")
        result[meta.get("id")] = (path, meta, body)
    return result


def check_proposals(repo):
    findings = []
    for path in iter_object_files(repo, "proposal"):
        validate_object(repo, path, "proposal", findings)
    validate_record_references(repo, findings)
    if findings:
        raise MDFError("Proposal 契约或依赖图无效", code="invalid_proposals",
                       details={"findings": serialize_findings(findings)})
    return records(repo)


def started(repo, identifier):
    for root in (repo / "docs/specs", repo / "docs/changes"):
        if not root.exists():
            continue
        for path in root.rglob("delivery.json"):
            if path.is_symlink():
                raise MDFError("工作记录不能为符号链接", code="unsafe_path")
            try:
                data = json.loads(path.read_text())
            except (ValueError, OSError) as exc:
                raise MDFError("工作记录损坏", code="invalid_delivery") from exc
            if not isinstance(data, dict):
                raise MDFError("工作记录必须是 JSON 对象", code="invalid_delivery")
            if data.get("proposal") == identifier:
                return True
    refs = run(["git", "for-each-ref", "--format=%(refname)",
                "refs/heads/feature/", "refs/remotes/origin/feature/"], cwd=repo).stdout.splitlines()
    for ref in refs:
        paths = run(["git", "ls-tree", "-r", "--name-only", ref, "--", "docs/specs", "docs/changes"],
                    cwd=repo).stdout.splitlines()
        for path in paths:
            if not path.endswith("/delivery.json"):
                continue
            raw = run(["git", "show", f"{ref}:{path}"], cwd=repo).stdout
            try:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise MDFError("分支工作记录必须是 JSON 对象", code="invalid_delivery")
                if data.get("proposal") == identifier:
                    return True
            except ValueError as exc:
                raise MDFError("关联分支的工作记录损坏", code="invalid_delivery") from exc
    return False


def require_startable(repo, identifier):
    from .paths import load_manifest
    if load_manifest(repo).get("state") != "ready":
        raise MDFError("start 需要 ready 仓库", code="manifest_not_ready")
    objects = check_proposals(repo)
    if identifier not in objects:
        raise MDFError("缺少指定 PRP", code="missing_proposal")
    path, meta, _ = objects[identifier]
    if meta["status"] != "ready" or len(path.relative_to(repo / "docs").parts) != 2:
        raise MDFError("feature 需要 active ready PRP", code="proposal_not_ready")
    blocked = [dep for dep in meta["depends_on"] if objects[dep][1]["status"] not in SATISFIED]
    if blocked:
        raise MDFError("PRP 依赖尚未满足", code="proposal_blocked", details={"blocked_by": blocked})
    if started(repo, identifier):
        raise MDFError("PRP 已开工", code="proposal_started")
    return path
