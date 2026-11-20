"""incremental-integration-plan：按 base..HEAD 的拓扑图（0/1/多次 merge）独立判定 review/verify/fact 动作；只读。"""
import re

from mdf_core.execution.verification import FIXED_INPUTS, LOCKFILES
from mdf_core.execution.modules import load_modules, match
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.lifecycle.delivery_state import locate, safe, split_objectives_steps
from mdf_core.workspace.gitutil import repo_path, require_git_root
from mdf_core.workspace.merge_policy import ancestor, git, sha
from mdf_core.workspace.workflow_policy import integration_branch, trunk_branch, target_for

MATERIAL_NAMES = {"objectives.md", "code-review.md", "fact-audit.md", "CHANGE.md", "incremental-integration-verification-report.json"}
CONTRACTS = {".mdf/manifest.yaml", ".mdf/modules.yaml", "AGENTS.md"}
BASELINE = re.compile(r"(?m)^[ \t]*(?:- )?incremental-integration 基线：([0-9a-f]{40})")
REWORK = re.compile(r"(?m)^[ \t]*(?:- )?PR 返工：([0-9a-f]{40})\.\.[0-9a-f]{40}")


def classify(path):
    """fact：事实页；material：账本/文档；code：其余（是否被 module 拥有另判）。"""
    if path == "GLOSSARY.md" or (path.endswith(".md") and path.startswith(("docs/user-guide/", "docs/system/"))):
        return "fact"
    name = path.rsplit("/", 1)[-1]
    if (name in MATERIAL_NAMES or path.startswith(("changes/", "docs/")) or ("/" not in path and name.endswith(".md"))):
        return "material"
    return "code"


def _lines(repo, *args):
    return [x for x in git(repo, *args).stdout.split("\0") if x]


def commit_paths(repo, commit):
    return set(_lines(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "--no-renames", "-z", commit))


def resolve_base(repo, root, explicit):
    if explicit:
        return sha(repo, explicit)
    objectives = safe(repo, root / "objectives.md").read_text(encoding="utf-8")
    for pattern in (BASELINE, REWORK):
        found = pattern.findall(objectives)
        if found:
            return found[-1]
    relative = (root / "objectives.md").relative_to(repo).as_posix()
    commits = git(repo, "log", "--reverse", "--format=%H", "-G^- \\[[xX]\\] fact", "--", relative).stdout.split()
    for commit in commits:
        version = git(repo, "show", f"{commit}:{relative}", check=False)
        _, steps, _ = split_objectives_steps(version.stdout)
        if not version.returncode and re.search(r"(?m)^- \[[xX]\] fact", steps):
            return commit
    raise MDFError("无法确定 incremental-integration 基线，请用 --base 指定", code="missing_integration_base")


def target_refs(repo, target):
    names = {target, integration_branch(repo), trunk_branch(repo)} - {None}
    refs = [f"refs/{kind}/{name}" for name in sorted(names) for kind in ("remotes/origin", "heads")]
    return [r for r in refs if git(repo, "rev-parse", "--verify", "-q", r, check=False).returncode == 0]


def upstream_merge(repo, parents, refs):
    return len(parents) > 1 and all(any(ancestor(repo, p, ref) for ref in refs) for p in parents[1:])


def graph(repo, left, refs, head):
    """left..HEAD 的 merge 与普通提交划分：上游并入集、本分支自身提交、各 merge 冲突解决净改动。"""
    merges, incoming = [], set()
    for line in git(repo, "rev-list", "--merges", "--reverse", "--parents", f"{left}..{head}").stdout.splitlines():
        commit, *parents = line.split()
        kind = "upstream" if upstream_merge(repo, parents, refs) else "internal"
        if kind == "upstream":
            incoming |= set(git(repo, "rev-list", "--no-merges", commit, f"^{parents[0]}").stdout.split())
        merged = git(repo, "show", "--remerge-diff", "--format=", "--name-only", "--no-renames", "-z", commit, check=False)
        known = not merged.returncode and len(parents) == 2
        resolution = _lines(repo, "diff", "--name-only", "--no-renames", "-z", f"{commit}^1", commit) \
            if not known else [x for x in merged.stdout.split("\0") if x]
        merges.append({"commit": commit, "kind": kind, "parents": len(parents),
                       "resolution_known": known, "resolution_paths": sorted(resolution)})
    own = [c for c in git(repo, "rev-list", "--no-merges", "--reverse", f"{left}..{head}").stdout.split()
           if c not in incoming]
    return merges, own, incoming


def surface(repo, commits):
    found = set()
    for commit in commits:
        found |= commit_paths(repo, commit)
    return found


def rule_paths(repo):
    from mdf_core.foundation.paths import load_manifest
    rules = load_manifest(repo).get("rules") or {}
    return CONTRACTS | {v for v in rules.values() if isinstance(v, str)}


def config_paths(paths):
    """影响验证环境的配置：固定输入、lockfile、requirements*.txt。"""
    return sorted(p for p in paths if any(match(p, f) for f in FIXED_INPUTS) or p.rsplit("/", 1)[-1] in LOCKFILES
                  or (p.rsplit("/", 1)[-1].startswith("requirements") and p.endswith(".txt")))


def dependents(config, touched):
    """沿 depends_on 反向传递；未声明任何依赖图时只返回 touched。"""
    result, changed = set(touched), True
    while changed:
        changed = False
        for module in config.modules.values():
            if module.name not in result and result & set(module.depends_on):
                result.add(module.name)
                changed = True
    return sorted(result)


def build_plan(repo, root, data, explicit_base=None, *, explicit_head=None):
    config = load_modules(repo)
    base, head = resolve_base(repo, root, explicit_base), sha(repo, explicit_head or "HEAD")
    if not ancestor(repo, base, head):
        raise MDFError("incremental-integration 基线不是 HEAD 的祖先", code="invalid_integration_base")
    refs = target_refs(repo, target_for(repo, data["branch"], data=data))
    merges, own, incoming = graph(repo, base, refs, head)
    start = data.get("start_commit") or base
    _, branch_own, _ = graph(repo, start, refs, head) if start != base else (None, own, None)

    def counted_code(paths):
        """无 module 的根脚本、CI 与 lockfile 同样计入 review、verify 与 fact。"""
        return sorted(p for p in paths if classify(p) == "code")

    own_paths, up_paths = surface(repo, own), surface(repo, incoming)
    resolution = sorted({p for m in merges for p in m["resolution_paths"] if classify(p) != "material"})
    unknown = [m["commit"] for m in merges if not m["resolution_known"]]
    branch_paths = surface(repo, branch_own)
    own_code, res_code, up_code = counted_code(own_paths), counted_code(resolution), counted_code(up_paths)
    branch_code = counted_code(branch_paths)
    shared = sorted(set(branch_code) & set(up_code))
    interaction_modules = config.interacting(config.modules_for_paths(repo, branch_code),
                                             config.modules_for_paths(repo, up_code))
    module_files = sorted(p for p in up_code if set(config.modules_for_paths(repo, [p])) & set(interaction_modules))
    contract = sorted((own_paths | up_paths | set(resolution)) & rule_paths(repo))
    reasons = [name for name, hit in (("conflict_resolution", resolution or unknown), ("post_base_code", own_code), ("upstream_code", up_code),
                                      ("interaction", shared), ("module_interaction", interaction_modules),
                                      ("rules_or_contract_changed", contract)) if hit]
    review = {"action": "skip" if not reasons else "focused", "reasons": reasons, "diff_range": f"{base}..{head}",
              "paths": sorted(set(own_code) | set(up_code) | set(res_code) | set(shared) | set(module_files)),
              "interaction": {"files": shared, "modules": interaction_modules,
                              "branch_paths": sorted(p for p in branch_code if set(config.modules_for_paths(repo, [p]))
                                                     & set(interaction_modules))},
              "unknown_merges": unknown}
    own_config, up_config = config_paths(own_paths | set(resolution)), config_paths(up_paths)
    upstream_and_branch = bool(up_code or up_config) and bool(branch_code or config_paths(branch_paths))
    config_hit = bool(own_config or up_config)
    touched_paths = sorted(set(own_code) | set(res_code) | set(up_code) | set(own_config)
                           | (set(up_config) if config_hit else set()))
    smart = bool(own_code or up_code or res_code or upstream_and_branch or config_hit or contract
                 or ".mdf/modules.yaml" in up_paths)
    declared = any(m.depends_on for m in config.modules.values())
    touched_modules = set(config.modules_for_paths(repo, touched_paths))
    if upstream_and_branch and not declared:
        touched_modules |= set(config.modules_for_paths(repo, branch_code))
    verify = {"action": "smart" if smart else "skip",
              "modules": sorted(config.modules) if config_hit or ".mdf/modules.yaml" in up_paths
              else dependents(config, touched_modules),
              "paths": touched_paths if smart else [], "depends_on_declared": declared}
    facts = sorted(p for p in own_paths | up_paths | set(resolution) if classify(p) == "fact")
    implementation = sorted(set(own_code) | set(res_code) | set(up_code))
    conflicting_facts = sorted(set(facts) & ({p for p in resolution if classify(p) == "fact"}
                                              | (set(p for p in branch_paths if classify(p) == "fact") & up_paths)))
    action = ("skip" if not facts and not implementation and not contract
              else "update_required" if conflicting_facts else "audit")
    fact = {"action": action, "implementation": implementation, "facts": facts,
            "conflicting_facts": conflicting_facts, "rules_changed": contract}
    return {"base": base, "head": head, "target_refs": refs, "merges": merges, "own_commits": own,
            "incoming_commits": sorted(incoming), "review": review, "verify": verify, "fact": fact}


def command_incremental_plan(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    root, data = locate(repo)
    base = args.base
    if base is None:
        from mdf_core.lifecycle.target_integration import state_path
        from mdf_core.lifecycle.delivery_state import read_json
        path = state_path(repo, data["branch"])
        if path.is_file():
            base = read_json(path)["base"]
    emit({"ok": True, "operation": "incremental-integration-plan", "result": build_plan(repo, root, data, base)})
