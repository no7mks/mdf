"""只读生成 ready Proposal 依赖视图。"""
from .errors import MDFError, emit
from .gitutil import repo_path, require_git_root
from .proposals import check_proposals, started
from .validate_records import unsatisfied_depends_on


def next_view(repo, depth):
    if type(depth) is not int or depth < 1:
        raise MDFError("depth 必须为正整数", code="invalid_depth")
    objects = check_proposals(repo)
    active = {key: value for key, value in objects.items() if value[1]["status"] in {"draft", "ready"}}
    ready = {key for key, value in active.items() if value[1]["status"] == "ready"}
    metas = {key: value[1] for key, value in objects.items()}
    waiting = {key: unsatisfied_depends_on(value[1]["depends_on"], metas)
               for key, value in active.items()}
    levels = {}

    def level(key):
        if key in levels:
            return levels[key]
        deps = waiting[key]
        if any(dep not in ready for dep in deps):
            levels[key] = None
        else:
            parents = [level(dep) for dep in deps]
            levels[key] = None if None in parents else 1 + max(parents, default=0)
        return levels[key]

    for key in sorted(ready):
        level(key)
    shown = {key for key, value in levels.items() if value is not None and value <= depth}
    seen = set()

    def node(key):
        result = {"id": key, "level": levels[key], "blocked_by": waiting[key],
                  "in_progress": started(repo, key)}
        title = next((line[2:].strip() for line in objects[key][2].splitlines() if line.startswith("# ")), key)
        result["title"] = title
        if key in seen:
            result["reference"] = True
            return result
        seen.add(key)
        result["children"] = [node(child) for child in sorted(shown) if key in waiting[child]]
        return result

    trees = [node(key) for key in sorted(shown) if not waiting[key]]
    blocked = [{"id": key, "blocked_by": waiting[key]} for key in sorted(ready) if levels[key] is None]
    return {"ok": True, "operation": "next", "depth": depth, "trees": trees,
            "blocked": blocked, "needs_review": sorted(set(active) - ready),
            "hidden": sorted(key for key, value in levels.items() if value is not None and value > depth),
            "empty": not ready}


def command_next(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    from .paths import load_manifest, ensure_safe_managed_paths
    ensure_safe_managed_paths(repo)
    if load_manifest(repo).get("state") != "ready":
        raise MDFError("当前操作需要 ready 仓库", code="manifest_not_ready")
    emit(next_view(repo, args.depth))
