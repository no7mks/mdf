"""feature 延迟选择目标与 ODR 纳入 checkpoint。"""
import json

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.delivery_state import locate, safe, write_json, read_json
from mdf_core.workspace.gitutil import branch_details, current_branch, ensure_clean, unreleased_slug
from mdf_core.workspace.merge_policy import git

ODR = "on-demand-release"
CHECKPOINT = "等待选定 feature 合入"


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
    if kind in {"release", ODR, "hotfix"}:
        return "master"
    if kind != "feature":
        return "develop"
    data = identity_at(repo, source) if data is None else data
    target = data.get("target", None if data.get("base_branch") == "master" else "develop")
    if target is None or target == ODR:
        raise MDFError("catch-up 前须确定具体交付目标", code="target_pending")
    return validate_target(target, concrete=True)


def require_independent(repo, source):
    """拒绝 source 已包含的 develop 未发布历史；不只相信启动参数。"""
    pending = set(git(repo, "rev-list", "develop", "^master").stdout.split())
    included = set(git(repo, "rev-list", source, "^master").stdout.split())
    if pending & included:
        raise MDFError("已引入 develop 未发布历史，不能独立发布", code="unreleased_dependency")


def require_feature_target(repo, source, target):
    if target == "develop":
        return
    data = identity_at(repo, source)
    if data.get("base_branch") != "master":
        raise MDFError("ODR 仅接受从 master 启动的 feature", code="invalid_target")
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
        if not features or len(features) != len(set(features)):
            raise MDFError("ODR 需要不重复的 --feature 纳入清单", code="missing_features")
        for branch in features:
            if branch_details(branch)["kind"] != "feature":
                raise MDFError("ODR 清单只接受 feature/<slug>", code="invalid_arguments")
    elif features:
        raise MDFError("--feature 仅适用于 ODR", code="invalid_arguments")
    return from_master, target, features


def set_target(repo, target):
    ensure_clean(repo)
    root, data = locate(repo)
    source = current_branch(repo)
    if not source.startswith("feature/") or data.get("base_branch") != "master":
        raise MDFError("仅 master 起点的 feature 可选择目标", code="invalid_target")
    validate_target(target, concrete=True)
    from mdf_core.lifecycle.publish import state_path
    if state_path(repo, source).exists():
        raise MDFError("PR 已锁定目标，不允许改投", code="target_locked")
    require_feature_target(repo, source, target)
    data["target"] = target
    write_json(safe(repo, root / "delivery.json"), data)
    return {"target": target, "path": str(root / "delivery.json")}


def checkpoint(repo, *, required=False):
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
    if not isinstance(expected, list) or not expected:
        raise MDFError("ODR 缺少纳入清单", code="missing_features")
    pending = []
    parents = [row.split()[1:] for row in git(repo, "log", "--first-parent", "--format=%H %P", "HEAD").stdout.splitlines()]
    for source in expected:
        folder = unreleased_slug(branch_details(source))
        change = safe(repo, (archived if root == archived else repo / "changes/unreleased") / folder / "CHANGE.md")
        merged = False
        for pair in parents:
            if len(pair) != 2:
                continue
            try:
                child = identity_at(repo, source, pair[1])
            except MDFError:
                continue
            child_change = f"changes/unreleased/{folder}/CHANGE.md"
            included = git(repo, "cat-file", "-e", f"{pair[1]}:{child_change}", check=False)
            if child.get("target") == data["branch"] and included.returncode == 0:
                merged = True
                break
        if not change.is_file() or not merged:
            pending.append(source)
    from mdf_core.foundation.yamlutil import read_frontmatter
    container = archived if root == archived else repo / "changes/unreleased"
    actual = {read_frontmatter(path)[0].get("source_branch") for path in container.glob("*/CHANGE.md")}
    unexpected = actual - set(expected)
    if unexpected:
        raise MDFError("ODR 含未选定 Change", code="unexpected_features", details={"sources": sorted(map(str, unexpected))})
    result = {"ready": not pending, "pending": pending, "features": expected}
    if required and pending:
        raise MDFError("等待选定 feature 合入", code="features_pending", details=result)
    return result


def guard_catch_up(repo, incoming):
    source = current_branch(repo)
    if branch_details(source)["kind"] != "feature":
        return
    folder = unreleased_slug(branch_details(source))
    if not (repo / "changes/unreleased" / folder / "delivery.json").is_file():
        return
    data = identity_at(repo, source)
    if data.get("base_branch") != "master":
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
