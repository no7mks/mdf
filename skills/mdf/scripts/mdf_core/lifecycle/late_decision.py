"""feature 延迟选择目标与 ODR 纳入 checkpoint。"""
import json

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.delivery_state import locate, safe, write_json, read_json
from mdf_core.workspace.gitutil import branch_details, current_branch, ensure_clean, unreleased_slug
from mdf_core.workspace.merge_policy import git

ODR = "on-demand-release"
CHECKPOINT = "核对发布范围纳入"


def validate_target(target, *, concrete=False):
    if target == "develop" or (target == ODR and not concrete):
        return target
    if isinstance(target, str) and target.startswith(ODR + "/"):
        branch_details(target)
        return target
    raise MDFError("目标需要 develop 或 on-demand-release/<version>", code="invalid_target")


def identity_at(repo, branch, ref=None):
    folder = unreleased_slug(branch_details(branch))
    raw = git(repo, "show", f"{ref or branch}:changes/unreleased/{folder}/delivery.json", check=False)
    if raw.returncode:
        raise MDFError("目标或来源交付记录缺失", code="invalid_delivery")
    try:
        data = json.loads(raw.stdout)
    except ValueError as exc:
        raise MDFError("交付记录无效", code="invalid_delivery") from exc
    if not isinstance(data, dict) or data.get("branch") != branch:
        raise MDFError("交付身份不符", code="invalid_delivery")
    return data


def target_for(repo, source, *, data=None):
    kind = branch_details(source)["kind"]
    from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch
    if is_github_flow(repo):
        if kind == "hotfix":
            if data is None:
                from mdf_core.lifecycle.hotfix_version import delivery_record
                record = delivery_record(repo, source, ref=f"refs/heads/{source}")
                data = record[1] if record else {}
            return data.get("base_branch") or trunk_branch(repo)
        return trunk_branch(repo)
    if kind in {"release", ODR, "hotfix"}:
        return trunk_branch(repo)
    if kind != "feature":
        return "develop"
    data = identity_at(repo, source) if data is None else data
    trunk = trunk_branch(repo)
    target = data.get("target", None if data.get("base_branch") == trunk else "develop")
    if target is None or target == ODR:
        raise MDFError("catch-up 前须确定具体交付目标", code="target_pending")
    return validate_target(target, concrete=True)


def require_independent(repo, source, *, trunk=None):
    """拒绝 source 已包含的 develop 未发布历史；不只相信启动参数。"""
    from mdf_core.workspace.workflow_policy import trunk_branch
    trunk = trunk if trunk is not None else trunk_branch(repo)
    pending = set(git(repo, "rev-list", "develop", f"^{trunk}").stdout.split())
    included = set(git(repo, "rev-list", source, f"^{trunk}").stdout.split())
    if pending & included:
        raise MDFError("已引入 develop 未发布历史，不能独立发布", code="unreleased_dependency")


def require_feature_target(repo, source, target):
    from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch
    if target == "develop" or is_github_flow(repo):
        return
    data = identity_at(repo, source)
    trunk = trunk_branch(repo)
    if data.get("base_branch") != trunk:
        raise MDFError(f"ODR 仅接受从 {trunk} 启动的 feature", code="invalid_target")
    require_independent(repo, source)
    selected = identity_at(repo, target).get("features", [])
    if source not in selected:
        raise MDFError("feature 不在目标 ODR 纳入清单", code="feature_not_selected")


def start_options(args):
    from_master = getattr(args, "from_master", False)
    target = getattr(args, "target", None)
    features = getattr(args, "feature", None)
    if from_master and args.kind != "feature":
        raise MDFError("--from-master 仅适用于 feature", code="invalid_arguments")
    if target is not None:
        if not from_master:
            raise MDFError("--target 需要 feature --from-master", code="invalid_arguments")
        validate_target(target)
    if args.kind == ODR:
        if (not features and not getattr(args, "scope_file", None)) or len(features or []) != len(set(features or [])):
            raise MDFError("ODR 需要 --feature 或 --scope-file 纳入清单", code="missing_features")
        for branch in features or []:
            if branch_details(branch)["kind"] != "feature":
                raise MDFError("ODR 清单只接受 feature/<slug>", code="invalid_arguments")
    elif features or getattr(args, "scope_file", None):
        raise MDFError("--feature 仅适用于 ODR", code="invalid_arguments")
    return from_master, target, features


def set_target(repo, target):
    ensure_clean(repo)
    root, data = locate(repo)
    source = current_branch(repo)
    from mdf_core.workspace.workflow_policy import trunk_branch
    trunk = trunk_branch(repo)
    if not source.startswith("feature/") or data.get("base_branch") != trunk:
        raise MDFError(f"仅 {trunk} 起点的 feature 可选择目标", code="invalid_target")
    validate_target(target, concrete=True)
    from mdf_core.lifecycle.publish import state_path
    if state_path(repo, source).exists():
        raise MDFError("PR 已锁定目标，不允许改投", code="target_locked")
    require_feature_target(repo, source, target)
    data["target"] = target
    write_json(safe(repo, root / "delivery.json"), data)
    return {"target": target, "path": str(root / "delivery.json")}


def checkpoint(repo, *, required=False, release=False):
    source = current_branch(repo)
    if branch_details(source)["kind"] != ODR:
        raise MDFError("checkpoint 仅适用于 ODR", code="invalid_arguments")
    version = branch_details(source)["version"]
    archived = safe(repo, repo / "changes" / version)
    if (archived / "delivery.json").is_file():
        root, data = archived, read_json(archived / "delivery.json")
    else:
        root, data = locate(repo)
    if data.get("branch") != source:
        raise MDFError("ODR 身份不符", code="invalid_delivery")
    expected = data.get("features")
    if not isinstance(expected, list) or (not expected and not data.get("scope")):
        raise MDFError("ODR 缺少纳入清单", code="missing_features")
    require_independent(repo, "HEAD")
    covered = set()
    pending = []
    parents = [row.split()[1:] for row in git(repo, "log", "--first-parent", "--format=%H %P", "HEAD").stdout.splitlines()]
    for source in expected:
        folder = unreleased_slug(branch_details(source))
        merged = False
        for pair in parents:
            if len(pair) != 2:
                continue
            try:
                child = identity_at(repo, source, pair[1])
            except MDFError:
                continue
            from mdf_core.workspace.workflow_policy import trunk_branch
            if child.get("target") == data["branch"] and child.get("base_branch") == trunk_branch(repo):
                merged = True
                from mdf_core.lifecycle.odr_scope import ancestors
                covered.update(ancestors(repo, pair[1], data["start_commit"])
                               - ancestors(repo, pair[0], data["start_commit"]))
                # 后续 feature 会继承本 feature 的材料；继续累计较早的实际合入。
        if not merged:
            pending.append(source)
    from mdf_core.foundation.yamlutil import read_frontmatter
    container = archived if root == archived else repo / "changes/unreleased"
    actual = {read_frontmatter(path)[0].get("source_branch") for path in container.glob("*/CHANGE.md")}
    unexpected = actual - set(expected)
    if unexpected:
        raise MDFError("ODR 含未选定 Change", code="unexpected_features", details={"sources": sorted(map(str, unexpected))})
    from mdf_core.lifecycle.odr_scope import check_scope
    pending.extend(check_scope(repo, data, covered))
    result = {"ready": not pending, "pending": pending, "features": expected}
    if required and pending:
        raise MDFError("等待发布范围纳入与验收", code="features_pending", details=result)
    if release:
        from mdf_core.lifecycle.odr_acceptance import require_acceptance
        require_acceptance(repo, root, data, included=covered)
    return result


def guard_catch_up(repo, incoming):
    source = current_branch(repo)
    if branch_details(source)["kind"] == "release":
        folder = unreleased_slug(branch_details(source))
        if (repo / "changes/unreleased" / folder / "delivery.json").is_file():
            from mdf_core.lifecycle.cutpoint import require_not_frozen_catch_up
            require_not_frozen_catch_up(identity_at(repo, source), repo, incoming)
        return
    if branch_details(source)["kind"] != "feature":
        return
    folder = unreleased_slug(branch_details(source))
    if not (repo / "changes/unreleased" / folder / "delivery.json").is_file():
        return
    data = identity_at(repo, source)
    from mdf_core.workspace.workflow_policy import trunk_branch
    if data.get("base_branch") != trunk_branch(repo):
        return
    refs = git(repo, "for-each-ref", "--format=%(refname)", f"--points-at={incoming}",
               "refs/heads/develop", "refs/remotes/origin/develop",
               "refs/heads/on-demand-release/", "refs/remotes/origin/on-demand-release/").stdout.split()
    if refs:
        target = target_for(repo, source, data=data)
        selected_refs = {f"refs/heads/{target}", f"refs/remotes/origin/{target}"}
        if not selected_refs.intersection(refs):
            raise MDFError("catch-up 必须使用已确定的交付目标", code="invalid_target")
        require_feature_target(repo, source, target)
    if str(data.get("target", "")).startswith(ODR):
        require_independent(repo, incoming)
