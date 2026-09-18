"""只读生成 draft/ready Proposal 混态依赖视图。"""
from .errors import MDFError, emit
from .gitutil import repo_path, require_git_root
from .proposals import check_proposals, started_ids
from .validate_records import unsatisfied_depends_on


def _title(objects, key):
    return next((line[2:].strip() for line in objects[key][2].splitlines()
                 if line.startswith("# ")), key)


def _milestone(meta):
    name = meta.get("milestone")
    return name if isinstance(name, str) and name.strip() else None


def _group_sort(name):
    return (name is not None, name or "")


def _ordered_roots(shown, prp_waiting, waiting, objects, active):
    roots = [key for key in shown if not prp_waiting[key]]
    buckets = {}
    for key in roots:
        buckets.setdefault(_milestone(objects[key][1]), []).append(key)
    names = set(buckets)
    incoming = {name: set() for name in names}
    outgoing = {name: set() for name in names}
    for key in roots:
        src = _milestone(objects[key][1])
        for dep in waiting[key]:
            if dep in active or dep not in names or dep == src:
                continue
            incoming[src].add(dep)
            outgoing[dep].add(src)
    ready = sorted((name for name, preds in incoming.items() if not preds),
                   key=_group_sort)
    ordered = []
    while ready:
        name = ready.pop(0)
        ordered.append(name)
        nxts = []
        for nxt in outgoing[name]:
            incoming[nxt].discard(name)
            if not incoming[nxt] and nxt not in ordered and nxt not in ready:
                nxts.append(nxt)
        ready.extend(nxts)
        ready.sort(key=_group_sort)
    for name in sorted(names, key=_group_sort):
        if name not in ordered:
            ordered.append(name)
    return [key for name in ordered for key in sorted(buckets[name])]


def _index(objects, waiting, in_progress, active_ids):
    groups, ungrouped = {}, []
    for key in active_ids:
        meta = objects[key][1]
        item = {"id": key, "title": _title(objects, key),
                "status": meta["status"],
                "depends_on": list(meta["depends_on"]),
                "blocked_by": waiting[key],
                "in_progress": key in in_progress}
        milestone = _milestone(meta)
        if milestone is not None:
            groups.setdefault(milestone, []).append(item)
        else:
            ungrouped.append(item)
    return {"groups": [{"milestone": name, "items": groups[name]}
                       for name in sorted(groups)],
            "ungrouped": ungrouped}


def tree_view(repo, depth):
    if type(depth) is not int or depth < 1:
        raise MDFError("depth 必须为正整数", code="invalid_depth")
    objects = check_proposals(repo)
    active = {key: value for key, value in objects.items()
              if value[1]["status"] in {"draft", "ready"}}
    metas = {key: value[1] for key, value in objects.items()}
    waiting = {key: unsatisfied_depends_on(value[1]["depends_on"], metas)
               for key, value in active.items()}
    prp_waiting = {key: [dep for dep in waiting[key] if dep in active]
                   for key in active}
    in_progress = started_ids(repo)
    levels = {}

    def level(key):
        if key in levels:
            return levels[key]
        parents = [level(dep) for dep in prp_waiting[key]]
        levels[key] = None if None in parents else 1 + max(parents, default=0)
        return levels[key]

    for key in sorted(active):
        level(key)
    shown = {key for key, value in levels.items()
             if value is not None and value <= depth}
    seen = set()

    def node(key):
        meta = objects[key][1]
        result = {"id": key, "level": levels[key], "status": meta["status"],
                  "blocked_by": waiting[key],
                  "in_progress": key in in_progress,
                  "title": _title(objects, key)}
        milestone = _milestone(meta)
        if milestone is not None:
            result["milestone"] = milestone
        if key in seen:
            result["reference"] = True
            return result
        seen.add(key)
        result["children"] = [node(child) for child in sorted(shown)
                              if key in prp_waiting[child]]
        return result

    trees = [node(key) for key in _ordered_roots(
        shown, prp_waiting, waiting, objects, active)]
    return {"ok": True, "operation": "tree", "depth": depth, "trees": trees,
            "index": _index(objects, waiting, in_progress, sorted(active)),
            "hidden": sorted(key for key, value in levels.items()
                             if value is not None and value > depth),
            "empty": not active}


def command_tree(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    from .paths import load_manifest, ensure_safe_managed_paths
    ensure_safe_managed_paths(repo)
    if load_manifest(repo).get("state") != "ready":
        raise MDFError("当前操作需要 ready 仓库", code="manifest_not_ready")
    emit(tree_view(repo, args.depth))
