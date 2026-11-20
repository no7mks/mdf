"""分离 hotfix 的交付名称与一次发布固定的版本。"""
import json

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.textutil import stable_semver
from mdf_core.lifecycle.delivery_state import read_json, safe, write_json
from mdf_core.workspace.gitutil import branch_details, run, unreleased_slug


def git(repo, *args, check=True):
    return run(["git", *args], cwd=repo, check=check)


def delivery_record(repo, source, *, ref=None):
    """从工作区或固定 Git ref 读取同一 source 的开发/归档身份。"""
    slug = unreleased_slug(branch_details(source))
    paths = [f"changes/unreleased/{slug}/delivery.json"]
    if ref is None:
        changes = safe(repo, repo / "changes")
        names = [p.name for p in changes.iterdir()] if changes.is_dir() else []
    else:
        listing = git(repo, "ls-tree", "-d", "--name-only", f"{ref}:changes", check=False)
        names = listing.stdout.splitlines() if listing.returncode == 0 else []
    paths.extend(f"changes/{name}/delivery.json" for name in sorted(names) if stable_semver(name))
    records = []
    for path in paths:
        if ref is None:
            target = safe(repo, repo / path)
            if not target.is_file():
                continue
            data = read_json(target)
        else:
            shown = git(repo, "show", f"{ref}:{path}", check=False)
            if shown.returncode:
                continue
            try:
                data = json.loads(shown.stdout)
            except ValueError as exc:
                raise MDFError("发布交付身份损坏", code="invalid_delivery") from exc
        if not isinstance(data, dict) or data.get("branch") != source:
            continue
        if data.get("slug") != slug:
            raise MDFError("hotfix 交付 slug 不匹配", code="invalid_delivery")
        version = data.get("version")
        if version is not None and stable_semver(version) is None:
            raise MDFError("hotfix 版本必须为稳定 SemVer", code="invalid_delivery")
        if not path.startswith("changes/unreleased/") and version != path.split("/")[1]:
            raise MDFError("hotfix 归档版本与目录不符", code="invalid_delivery")
        records.append((path, data))
    if not records:
        return None
    selected = records[0] if records[0][0].startswith("changes/unreleased/") else max(
        records, key=lambda item: stable_semver(item[1]["version"]),
    )
    if sum(data.get("start_commit") == selected[1].get("start_commit") for _, data in records) > 1:
        raise MDFError("hotfix 交付材料存在多个目录", code="invalid_delivery")
    return selected


def _tag_base(repo, source):
    """tag 历史所在分支：gitflow 为 trunk；github-flow 的 support 线 hotfix 为其 support 分支。"""
    from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch
    if source is not None and is_github_flow(repo):
        from mdf_core.workspace.workflow_policy import target_for
        return target_for(repo, source)
    return trunk_branch(repo)


def next_patch(repo, source=None):
    """仅采用基线分支历史可达的 v<稳定 SemVer>，按数值选最大版本。"""
    base = _tag_base(repo, source)
    tags = git(repo, "tag", "--merged", f"refs/heads/{base}", "--list", "v*").stdout.splitlines()
    versions = [stable_semver(tag[1:]) for tag in tags]
    versions = [value for value in versions if value is not None]
    if not versions:
        raise MDFError(f"{base} 没有有效发布 tag，请显式指定 --version", code="missing_release_tag")
    major, minor, patch = max(versions)
    return f"{major}.{minor}.{patch + 1}"


def source_version(repo, source, *, ref=None, auto=False):
    details = branch_details(source)
    if details["version"] is not None:
        return details["version"]
    if details["kind"] != "hotfix":
        raise MDFError("需要 hotfix 分支", code="unsupported_branch")
    if ref is None:
        ref = f"refs/heads/{source}"
        if git(repo, "rev-parse", "--verify", "--quiet", ref, check=False).returncode:
            detached = not git(repo, "branch", "--show-current").stdout.strip()
            if detached:
                ref = "HEAD"
            else:
                versions = set()
                for tag in git(repo, "tag", "--list", "v*").stdout.splitlines():
                    version = tag[1:]
                    if stable_semver(version) is None:
                        continue
                    record = delivery_record(repo, source, ref=f"refs/tags/{tag}")
                    if record and record[1].get("version") == version:
                        versions.add(version)
                if len(versions) != 1:
                    raise MDFError("无法确定原 hotfix 版本，请传 --version", code="invalid_delivery",
                                   details={"versions": sorted(versions)})
                return versions.pop()
    record = delivery_record(repo, source, ref=ref)
    if record is None:
        raise MDFError("hotfix 交付身份缺失", code="invalid_delivery")
    version = record[1].get("version")
    if version is not None:
        return version
    if auto:
        return next_patch(repo, source)
    raise MDFError("hotfix 尚未固定版本，请执行 delivery resolve-version", code="missing_hotfix_version")


def freeze_version(repo, root, data, requested=None):
    details = branch_details(data["branch"])
    if details["kind"] != "hotfix":
        raise MDFError("resolve-version 仅接受 hotfix", code="unsupported_branch")
    fixed = data.get("version") or details["version"]
    if fixed is not None and stable_semver(fixed) is None:
        raise MDFError("hotfix 版本必须为稳定 SemVer", code="invalid_delivery")
    if requested is not None and stable_semver(requested) is None:
        raise MDFError("--version 必须为稳定 SemVer", code="invalid_version")
    if requested is not None and fixed is not None and requested != fixed:
        raise MDFError("hotfix 已固定版本，不得重新定版", code="hotfix_version_changed")
    version = fixed or requested or next_patch(repo, data["branch"])
    if details["version"] is None and data.get("version") is None:
        data["version"] = version
        write_json(safe(repo, root / "delivery.json"), data)
    return {"version": version, "tag": f"v{version}"}
