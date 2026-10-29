"""Validate evidence for quick/smoke suites fully deselected by known Bugs."""
import json
import re
from pathlib import Path

from mdf_core.foundation.constants import OBJECT_FILE_RE
from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.yamlutil import read_frontmatter


def _fail(message):
    raise MDFError(message, code="invalid_empty_suite_exemption")


def _identity(item):
    if not isinstance(item, dict):
        _fail("test 身份必须是对象")
    fields = ("module", "file", "test_id")
    if any(not isinstance(item.get(key), str) or not item[key].strip() for key in fields):
        _fail("test 身份缺少 module/file/test_id")
    path = Path(item["file"])
    if path.is_absolute() or ".." in path.parts:
        _fail("test file 必须是仓库相对路径")
    return tuple(item[key] for key in fields)


def _local_file(repo, relative):
    if not isinstance(relative, str):
        _fail("证据路径必须是字符串")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        _fail("证据必须是仓库相对路径")
    candidate = repo / path
    if not candidate.is_file() or not candidate.resolve().is_relative_to(repo.resolve()):
        _fail("证据文件缺失或位于仓库外")
    relative_parts = candidate.relative_to(repo).parts
    if any(repo.joinpath(*relative_parts[:index]).is_symlink() for index in range(1, len(relative_parts) + 1)):
        _fail("证据路径不得包含 symlink")
    return candidate


def validate_empty_suite(repo, report_dir, suite):
    """Return explicit exemptions, or None when no exemption evidence exists."""
    evidence = Path(report_dir) / "empty-suite.json"
    if not evidence.exists():
        return None
    if evidence.is_symlink() or suite not in {"quick", "smoke"}:
        _fail("仅 quick/smoke 可使用本轮普通文件 empty-suite.json")
    try:
        data = json.loads(evidence.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _fail(f"无法读取空 suite 证据: {exc}")
    if not isinstance(data, dict) or data.get("suite") != suite:
        _fail("空 suite 证据的 suite 不匹配")
    collected, excluded = data.get("collected"), data.get("excluded")
    if not isinstance(collected, list) or not collected or not isinstance(excluded, list):
        _fail("必须记录非空 collected 与 excluded 清单")
    identities = [_identity(item) for item in collected]
    removed = [_identity(item) for item in excluded]
    if len(set(identities)) != len(identities) or len(set(removed)) != len(removed):
        _fail("空 suite 证据含重复 test")
    if set(identities) != set(removed):
        _fail("并非全部收集到的 test 都已豁免")
    repo = Path(repo)
    for item in excluded:
        _local_file(repo, item["file"])
        bug = _local_file(repo, item.get("bug"))
        if bug.parent != repo / "docs" / "bugs":
            _fail("豁免须引用 active Bug 文件")
        meta, body = read_frontmatter(bug)
        filename = OBJECT_FILE_RE.fullmatch(bug.name)
        if not filename or not filename.group(1).startswith("bug-") or meta.get("id") != filename.group(1):
            _fail("关联文件缺少匹配的 Bug ID")
        if meta.get("type") != "bug" or meta.get("status") != "open":
            _fail("关联 Bug 不再是 open")
        blocks = re.findall(r"^```mdf-test-links\s*\n(.*?)^```\s*$", body, re.M | re.S)
        if len(blocks) != 1:
            _fail("Bug 必须含唯一 mdf-test-links 关联清单")
        try:
            links = json.loads(blocks[0])
        except ValueError:
            _fail("Bug test 关联不是有效 JSON")
        if not isinstance(links, list):
            _fail("Bug test 关联必须是列表")
        matches = [link for link in links if _identity(link) == _identity(item)]
        if len(matches) != 1:
            _fail("未精确命中唯一 Bug test 关联")
        link = matches[0]
        suites = link.get("suites")
        if not isinstance(suites, list) or any(not isinstance(name, str) for name in suites):
            _fail("关联 suites 必须是字符串列表")
        if link.get("state") != "removed" or suite not in suites:
            _fail("关联 test 未在当前 suite 中标记 removed")
    return {"fully_exempted": True, "exemptions": excluded,
            "selection_evidence": str(evidence.relative_to(repo))}
