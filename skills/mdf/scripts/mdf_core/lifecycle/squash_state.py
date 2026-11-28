"""squash 核验后的流程端点映射；不重新执行或伪造验收。"""
from mdf_core.lifecycle.delivery_state import read_json, write_json
from mdf_core.workspace.merge_policy import ancestor, git


def paths(repo, branch):
    from mdf_core.lifecycle.catchup import state_path as catchup_path
    from mdf_core.lifecycle.consolidation import record_path
    from mdf_core.lifecycle.target_integration import state_path as integration_path
    return catchup_path(repo, branch), integration_path(repo, branch), record_path(repo, branch)


def covered_by_consolidation(repo, base, consolidated):
    """仅跨越无需增量验收的材料提交，最后一笔可复用 consolidate 的精确提交证据。"""
    from mdf_core.lifecycle.incremental_plan import CONTRACTS, classify, commit_paths, config_paths, rule_paths
    head = consolidated.get("head")
    start = consolidated.get("start_head", head)
    if not head or not start or not ancestor(repo, base, start) or not ancestor(repo, start, head):
        return False
    rules = rule_paths(repo) if (repo / ".mdf/manifest.yaml").is_file() else CONTRACTS
    from mdf_core.execution.verification_inputs import input_patterns, is_input
    declared = input_patterns(repo) if (repo / ".mdf/modules.yaml").is_file() else set()
    rows = git(repo, "rev-list", "--parents", f"{base}..{start}").stdout.splitlines()
    for row in rows:
        commit, *parents = row.split()
        changed = commit_paths(repo, commit)
        if (len(parents) != 1 or config_paths(changed)
                or any(classify(p) != "material" or p in rules or is_input(p, declared) for p in changed)):
            return False
    return True



def protected_commits(repo, branch, head):
    """无法由当前已收敛 tip 承接的端点，保留在 squash floor 之前。"""
    catchup, integration, consolidation = paths(repo, branch)
    consolidated = read_json(consolidation) if consolidation.is_file() else {}
    covered = consolidated.get("head") == head and not consolidated.get("pending")
    protected = set()
    for path, keys in ((catchup, ("base", "completed_head")), (integration, ("base", "accepted_head"))):
        state = read_json(path) if path.is_file() else {}
        # 完成记录取代上一轮的 base；旧 base 仅保留为历史证据。
        if path == catchup and state.get("completed_head"):
            keys = ("completed_head",)
        for key in keys:
            value = state.get(key)
            if value and value != head and not (path == catchup and covered and covered_by_consolidation(repo, value, consolidated)):
                protected.add(value)
    from mdf_core.reconciliation.context import state_path
    record = state_path(repo, branch)
    state = read_json(record) if record.is_file() else {}
    if state.get("record_mode") == "ledgerless" and not state.get("completed") and state.get("record_head"):
        protected.add(state["record_head"])
    return protected


def remap(repo, branch, old_tip, heads, old_tips):
    """heads 是已核对段界 tree 与线性父链的新 commits，最后一个等价于 old_tip。"""
    if not heads:
        return
    catchup, integration, consolidation = paths(repo, branch)
    consolidated = read_json(consolidation) if consolidation.is_file() else {}
    consolidated_head = consolidated.get("head")

    mapping = dict(zip(old_tips, heads))

    def equivalent(value):
        head = mapping.get(value)
        if not head or not ancestor(repo, value, old_tip):
            return None
        if git(repo, "rev-parse", f"{value}^{{tree}}").stdout == git(repo, "rev-parse", f"{head}^{{tree}}").stdout:
            return head
        return None

    catchup_state = read_json(catchup) if catchup.is_file() else {}
    receipt = catchup_state.get("squash_mapping", {})
    restored = (receipt.get("restored_completion") is True and receipt.get("old_tip") == old_tip
                and receipt.get("head") == heads[-1] and catchup_state.get("completed_head") == heads[-1])
    for path, keys in ((catchup, ("base", "completed_head")), (integration, ("base", "accepted_head")),
                       (consolidation, ("head",))):
        if not path.is_file():
            continue
        state = read_json(path)
        updates = {}
        for key in keys:
            value = state.get(key)
            if not value or ancestor(repo, value, heads[-1]):
                continue
            mapped = equivalent(value)
            if (not mapped and path == catchup and consolidated_head
                    and covered_by_consolidation(repo, value, consolidated)):
                mapped = equivalent(consolidated_head)
            if mapped:
                updates[key] = {"before": value, "after": mapped}
                state[key] = mapped
        if path == catchup and updates and not state.get("completed_head") and state.get("summary"):
            from mdf_core.lifecycle.delivery_state import locate
            from mdf_core.lifecycle.stage_route import parse_items
            root, _ = locate(repo)
            checked = {item["name"] for item in parse_items((root / "objectives.md").read_text()) if item["checked"]}
            if (consolidated.get("pending") and equivalent(consolidated_head) == heads[-1]
                    and state["base"] == heads[-1] and {"catch-up", "consolidate"} <= checked):
                state["completed_head"] = heads[-1]
                restored = True
        if path == consolidation and restored:
            state.pop("pending", None)
            write_json(path, state)
        if updates:
            state["squash_mapping"] = {"old_tip": old_tip, "head": heads[-1], "fields": updates}
            if path == catchup and restored:
                state["squash_mapping"]["restored_completion"] = True
            write_json(path, state)
