"""确定性交付 gate；语义结论由调用 intent 审查并记录。"""
from pathlib import Path

from .delivery_state import (
    STAGES, fingerprints, gate, git, locate, read_json, require_design,
    require_finish, require_green, safe, write_json,
)
from .errors import MDFError, emit
from .gitutil import current_branch, repo_path, require_git_root
from .paths import load_manifest
from .verification import manifest_items
from .closeout_validate import run_verify_commands


def policy_input(raw):
    policy = read_json(Path(raw)) if raw else None
    if not policy or set(policy) != {"protected_paths"}:
        raise MDFError("design 需要包含 protected_paths 的 policy JSON", code="invalid_policy")
    paths = policy["protected_paths"]
    if (not isinstance(paths, list) or not paths
            or any(not isinstance(p, str) or not p.strip() or p.startswith("/")
                   or ".." in p.split("/") for p in paths)):
        raise MDFError("protected_paths 必须列出测试、fixture 和验证配置路径", code="invalid_policy")
    return policy


def require_stage_branch(repo, stage):
    branch = current_branch(repo)
    allowed = {"write-tests": ("feature/", "qa/"), "implement": ("feature/", "dev/")}
    if not branch.startswith(allowed.get(stage, ("feature/",))):
        raise MDFError("该阶段不允许在当前角色分支执行", code="stage_branch")


def record_stage(repo, root, data, args):
    stage = args.stage
    if stage not in STAGES:
        raise MDFError("record 需要有效阶段", code="invalid_stage")
    require_stage_branch(repo, stage)
    if not args.summary or not args.summary.strip():
        raise MDFError("gate 需要非空语义审查摘要", code="missing_review")
    if stage == "design":
        policy = policy_input(args.policy_file)
        current = fingerprints(repo, root, data, policy)
    else:
        current = require_design(repo, root, data)
        policy = gate(repo, root, "design")["policy"]
    if stage == "implement":
        baseline = gate(repo, root, "design")
        if (root / "gates/write-tests.json").exists():
            baseline = gate(repo, root, "write-tests")
        if baseline["fingerprints"]["tests"] != current["tests"]:
            raise MDFError("implement 不得修改测试或验证规则", code="test_approval_required")
    if stage == "converge":
        for prerequisite in ("write-tests", "implement"):
            record = gate(repo, root, prerequisite)
            if record.get("fingerprints", {}).get("design") != current["design"]:
                raise MDFError("两路产出必须来自同一设计", code="stale_gate")
        original = gate(repo, root, "write-tests")["fingerprints"]["tests"]
        if original != current["tests"] and not args.test_approval:
            raise MDFError("测试或验证规则变化，需要用户批准记录", code="test_approval_required")
        current = require_green(repo, root, data)
    elif stage == "review":
        previous = gate(repo, root, "converge")
        if previous.get("fingerprints", {}).get("design") != current["design"]:
            raise MDFError("缺少同设计的收敛证据", code="stale_gate")
        current = require_green(repo, root, data)
    elif stage == "fact-update":
        previous = gate(repo, root, "review")
        if previous.get("fingerprints", {}).get("code") != current["code"]:
            raise MDFError("实现审查已过期", code="stale_gate")
        # Facts-only edits need not invalidate business verification.
        require_green(repo, root, data)
    record = {"stage": stage, "summary": args.summary, "fingerprints": current,
              "head": git(repo, "rev-parse", "HEAD").stdout.strip()}
    if stage == "design":
        record["policy"] = policy
    if args.test_approval:
        record["test_approval"] = args.test_approval
    write_json(safe(repo, root / "gates" / f"{stage}.json"), record)
    return record


def verify(repo, root, data, selected):
    before = require_design(repo, root, data)
    items = manifest_items(load_manifest(repo))
    ids = {item["id"] for item in items}
    if set(selected) - ids:
        raise MDFError("未知验证项 ID", code="invalid_verification")
    results = []
    failed = False
    for item in items:
        if selected and item["id"] not in selected:
            continue
        try:
            result = run_verify_commands(repo, [item["command"]])[0]
            result["passed"] = True
        except MDFError as exc:
            failed = True
            result = {"command": item["command"], "passed": False,
                      "error": exc.code, "details": exc.details}
        results.append({"id": item["id"], "kind": item["kind"], **result})
    after = fingerprints(repo, root, data)
    if before["code"] != after["code"] or before["design"] != after["design"]:
        failed = True
    record = {"fingerprints": before, "results": results,
              "all_passed": not failed and {r["id"] for r in results} == ids}
    target = "verification" if not selected else "verification-partial"
    write_json(safe(repo, root / "gates" / f"{target}.json"), record)
    if failed:
        if selected:
            write_json(safe(repo, root / "gates/verification.json"), record)
        raise MDFError("项目验证失败或验证期间输入发生变化", code="verify_command_failed", details=record)
    return record


def check(repo, root, data, stage):
    if stage not in (*STAGES, "finish"):
        raise MDFError("check 需要有效阶段", code="invalid_stage")
    if stage == "finish":
        return require_finish(repo, root, data)
    current = require_design(repo, root, data)
    if stage in {"write-tests", "implement"}:
        return current
    if stage == "converge":
        for prerequisite in ("write-tests", "implement"):
            record = gate(repo, root, prerequisite)
            if record.get("fingerprints", {}).get("design") != current["design"]:
                raise MDFError("并行阶段设计不一致", code="stale_gate")
        return current
    if stage == "review":
        gate(repo, root, "converge")
        return require_green(repo, root, data)
    if stage == "fact-update":
        record = gate(repo, root, "review")
        if any(record.get("fingerprints", {}).get(key) != current[key] for key in ("code", "design")):
            raise MDFError("实现审查已过期", code="stale_gate")
        return current
    return current


def command_delivery(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    from .paths import load_manifest, ensure_safe_managed_paths
    ensure_safe_managed_paths(repo)
    if load_manifest(repo).get("state") != "ready":
        raise MDFError("当前操作需要 ready 仓库", code="manifest_not_ready")
    root, data = locate(repo)
    if args.action == "record":
        result = record_stage(repo, root, data, args)
    elif args.action == "verify":
        result = verify(repo, root, data, args.item)
    elif args.action == "check":
        result = check(repo, root, data, args.stage)
    elif args.action == "parallel":
        from .delivery_git import parallel
        result = parallel(repo, root, data)
    elif args.action == "integrate":
        from .delivery_git import integrate
        result = integrate(repo, root, data, args.test_approval)
    else:
        result = {"delivery": data, "path": str(root.relative_to(repo)),
                  "gates": [stage for stage in STAGES if (root / "gates" / f"{stage}.json").exists()]}
    emit({"ok": True, "operation": f"delivery-{args.action}", "result": result})
