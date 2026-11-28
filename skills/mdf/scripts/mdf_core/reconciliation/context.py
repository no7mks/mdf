"""只读探测发布现场；本地操作记录不替代交付账本或验收证据。"""
from pathlib import Path
import re

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.textutil import stable_semver
from mdf_core.foundation.yamlutil import frontmatter_span, parse_yaml, read_frontmatter
from mdf_core.inspection.validate_reconcile import historical_head, line_ref
from mdf_core.lifecycle.delivery_state import read_json
from mdf_core.workspace.gitutil import branch_details, current_branch
from mdf_core.workspace.merge_policy import ancestor, configured, git, sha
from mdf_core.workspace.squash import common_dir
from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch


def metadata(text):
    if hasattr(text, "content"):
        text = text.content.decode("utf-8")
    start, end, body = frontmatter_span(text)
    return parse_yaml(text[start:end]), text[body:]


def state_path(repo, source=None):
    return common_dir(repo) / "mdf/reconcile" / ((source or current_branch(repo)) + ".json")


def external_record(repo, source, ref=None):
    ref = ref or "HEAD"
    if git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False).returncode:
        return None
    files = git(repo, "ls-tree", "-r", "--name-only", ref, "--", "changes").stdout.splitlines()
    found = []
    for path in files:
        parts = Path(path).parts
        if len(parts) != 3 or parts[-1] != "CHANGE.md" or stable_semver(parts[1]) is None:
            continue
        data, _ = metadata(git(repo, "show", f"{ref}:{path}").stdout)
        if data.get("source_branch") == source and data.get("record_mode") == "ledgerless":
            found.append(data)
    if len(found) > 1:
        raise MDFError("同名分支有多个 ledgerless 版本，须显式指定版本", code="ambiguous_release")
    return found[0] if found else None


def require_no_ledger(repo, source, version=None):
    details = branch_details(source)
    suffix = details.get("slug") or source.split("/", 1)[-1]
    folders = [repo / "changes/unreleased" / suffix]
    if version:
        folders += [repo / "changes/unreleased" / version, repo / "changes" / version]
    for root in dict.fromkeys(folders):
        delivery, objectives = root / "delivery.json", root / "objectives.md"
        if delivery.exists() or objectives.exists() or delivery.is_symlink() or objectives.is_symlink():
            if not delivery.is_file() or not objectives.is_file() or delivery.is_symlink() or objectives.is_symlink():
                raise MDFError("交付账本残缺；不得降级到 reconcile", code="invalid_delivery")
            from mdf_core.lifecycle.delivery_state import locate
            locate(repo)
            raise MDFError("已有 MDF 账本，使用 next / deliver / consolidate", code="standard_delivery",
                           details={"next_intent": "next"})


def stable_tags(repo, ref, line):
    result = []
    for tag in git(repo, "tag", "--merged", ref).stdout.splitlines():
        version = tag.removeprefix("v")
        parsed = stable_semver(version)
        if not tag.startswith("v") or parsed is None:
            continue
        if line.startswith("support/") and line != f"support/{parsed[0]}.{parsed[1]}":
            continue
        result.append((version, tag, sha(repo, f"refs/tags/{tag}")))
    return sorted(result, key=lambda row: stable_semver(row[0]))


def previous_release(repo, head, version, line):
    older = [row for row in stable_tags(repo, head, line) if stable_semver(row[0]) < stable_semver(version) and row[2] != head]
    if older:
        return older[-1]
    return None, None, None


def inspect(repo, args):
    source = current_branch(repo)
    if git(repo, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        raise MDFError("发布历史不完整；先获取完整历史再对账", code="incomplete_release_history")
    if not source:
        raise MDFError("reconcile 需要已检出的工作分支", code="unsupported_branch")
    saved_path = state_path(repo, source)
    saved = read_json(saved_path) if saved_path.is_file() else None
    if saved and not saved.get("completed"):
        versions = {saved["version"]} if saved["record_mode"] == "ledgerless" else {r["version"] for r in saved["releases"]}
        if (saved.get("source") != source or (args.version and args.version not in versions)
                or (args.support and saved["release_line"] != f"support/{args.support}")):
            raise MDFError("参数与在途 reconcile 身份冲突，先续办原操作", code="reconcile_state_changed")
        if saved["record_mode"] == "ledgerless":
            require_no_ledger(repo, source, saved["version"])
        current = sha(repo, "HEAD")
        heads = {current, saved.get("release_head")} if saved["record_mode"] == "ledgerless" else {
            r["release_commit"] for r in saved["releases"]}
        tags = {f"v{v}" for v in versions} | {r.get("release_tag") for r in saved.get("releases", [])}
        if ((args.commit and sha(repo, args.commit) not in heads)
                or (args.tag and (args.tag not in tags or sha(repo, f"refs/tags/{args.tag}") not in heads))):
            raise MDFError("tag/commit 与在途 reconcile 身份冲突", code="reconcile_state_changed")
        return {**saved, "resume": True, "current_head": current,
                **({"head": current} if saved["record_mode"] == "ledgerless" else {})}
    version, tag, commit = args.version, args.tag, args.commit
    support = args.support
    if support and not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", support):
        raise MDFError("support 需要 major.minor", code="invalid_support")
    line = f"support/{support}" if support else (source if source.startswith("support/") else trunk_branch(repo))
    details = branch_details(source)
    publishing = details["kind"] in {"release", "hotfix"}
    version = version or details.get("version") or (tag.removeprefix("v") if tag else None)
    if publishing and details.get("version") and version != details["version"]:
        raise MDFError("version 与真实发布分支不符", code="invalid_version")
    if publishing:
        require_no_ledger(repo, source, version)
        if is_github_flow(repo) and details["kind"] == "hotfix" and not commit and not tag:
            from mdf_core.lifecycle.support_line import hotfix_base
            line, _ = hotfix_base(repo, args)
    elif source not in {line, trunk_branch(repo), "planning"} and not source.startswith("pm/reconcile-"):
        raise MDFError("reconcile 不接管 feature/bugfix 或普通工作分支", code="unsupported_branch")
    if version is not None and stable_semver(version) is None:
        raise MDFError("version 必须为稳定 SemVer", code="invalid_version")
    if tag:
        tagged = sha(repo, f"refs/tags/{tag}")
        if commit and sha(repo, commit) != tagged:
            raise MDFError("tag 与 commit 不一致", code="tag_conflict")
        commit = tagged
    elif version and not git(repo, "rev-parse", "--verify", f"refs/tags/v{version}", check=False).returncode:
        tagged = sha(repo, f"refs/tags/v{version}")
        if commit and sha(repo, commit) != tagged:
            raise MDFError("version 的 tag 与显式 commit 不一致", code="tag_conflict")
        tag, commit = f"v{version}", tagged
    if publishing and not commit and ancestor(repo, "HEAD", line_ref(repo, line)):
        from mdf_core.lifecycle.publish import find_merge
        commit = find_merge(repo, line_ref(repo, line), sha(repo, "HEAD")) or sha(repo, "HEAD")
    if publishing and not commit and support and (not is_github_flow(repo) or details["kind"] != "hotfix"):
        raise MDFError("新发布只有 github-flow hotfix 可指定 support；其他发布目标固定为 trunk", code="invalid_support")
    if publishing and not commit and not ancestor(repo, "HEAD", line_ref(repo, line)):
        if not version:
            raise MDFError("slug hotfix 需要 --version", code="invalid_version")
        if is_github_flow(repo) and details["kind"] == "hotfix":
            from mdf_core.lifecycle.support_line import hotfix_base
            line, _ = hotfix_base(repo, args)
            base = git(repo, "merge-base", "HEAD", line_ref(repo, line)).stdout.strip()
            trunk_base = git(repo, "merge-base", "HEAD", line_ref(repo, trunk_branch(repo))).stdout.strip()
            if not ancestor(repo, trunk_base, base):
                raise MDFError("hotfix 不属于声明的 support 历史", code="invalid_release_line")
        head = sha(repo, "HEAD")
        previous, previous_tag, base = previous_release(repo, head, version, line)
        if is_github_flow(repo) and details["kind"] == "hotfix" and not previous:
            raise MDFError("support hotfix 缺少已发布基线", code="missing_release_tag")
        return {"record_mode": "ledgerless", "source": source, "version": version, "kind": details["kind"],
                "release_line": line, "head": head, "base": base, "previous_version": previous or "none",
                "previous_tag": previous_tag, "settings": configured(repo), "workflow": "github-flow" if is_github_flow(repo) else "gitflow"}
    if commit and not version:
        raise MDFError("指定 commit 时需要 --version", code="invalid_version")
    if commit:
        queue = [(version, tag, sha(repo, commit))]
    elif version:
        raise MDFError("目标历史版本没有 tag；显式传入 --commit", code="missing_release_tag")
    else:
        queue = stable_tags(repo, line_ref(repo, line), line)
    releases = []
    for value, release_tag, head in queue:
        previous, previous_tag, base = previous_release(repo, head, value, line)
        data = {"record_mode": "post_hoc", "version": value, "release_commit": head, "release_line": line,
                "previous_version": previous or "none", "previous_tag": previous_tag, "base": base,
                "source": source if publishing else line,
                "kind": details["kind"] if publishing else "hotfix" if line.startswith("support/") else "release"}
        if release_tag:
            data["release_tag"] = release_tag
            data["release_tag_oid"] = git(repo, "rev-parse", f"refs/tags/{release_tag}").stdout.strip()
        if previous_tag:
            data["previous_tag_oid"] = git(repo, "rev-parse", f"refs/tags/{previous_tag}").stdout.strip()
        historical_head(repo, data)
        existing = repo / "changes" / value / "CHANGE.md"
        if existing.is_file():
            from mdf_core.inspection.validate_change_schema import validate_version_change_file
            from mdf_core.lifecycle.closeout_render import changelog_excerpt
            findings = []
            validate_version_change_file(repo, existing, findings, value)
            if findings:
                raise MDFError("已有版本记录损坏，不能跳过补账核对", code="invalid_release_record",
                               details={"findings": [f.as_dict() for f in findings]})
            recorded, _ = read_frontmatter(existing)
            if recorded.get("record_mode") == "post_hoc" and recorded.get("release_commit") != head:
                raise MDFError("已有版本绑定另一个发布 commit", code="collision")
            changelog_excerpt((repo / "CHANGELOG.md").read_text(), value)
            continue
        releases.append(data)
    for left, right in zip(releases, releases[1:]):
        if not ancestor(repo, left["release_commit"], right["release_commit"]):
            raise MDFError("版本顺序与发布拓扑不一致，保留现场核对", code="ambiguous_release")
    return {"record_mode": "post_hoc", "source": source, "release_line": line, "releases": releases,
            "settings": configured(repo), "workflow": "github-flow" if is_github_flow(repo) else "gitflow"}
