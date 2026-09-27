"""确定性交付 gate；语义结论由调用 intent 审查并记录。"""
from pathlib import Path

from .delivery_state import (
    STAGES, fingerprints, gate, git, locate, read_json, require_design,
    require_finish, require_green, safe, write_json,
)
from .errors import MDFError, emit
from .gitutil import current_branch, repo_path, require_git_root
from .paths import load_manifest
from .roster import (
    apply_roster_patch,
    models_from_args,
    owner_branch,
    parse_role_branch,
    read_roster_config,
    role_branch,
    write_roster_config,
)
from .verification import (
    SUITES, manifest_verification, parse_suite_names, required_suite, required_suites,
)
from .verify_run import run_verify_command
from .validate_links import require_existing_local_links


def policy_input(raw):
    policy = read_json(Path(raw)) if raw else None
    if not policy or set(policy) != {"protected_paths", "suites"}:
        raise MDFError(
            "design 需要 protected_paths 与本交付 named suite 列表 suites",
            code="invalid_policy",
        )
    paths = policy["protected_paths"]
    if (not isinstance(paths, list) or not paths
            or any(not isinstance(p, str) or not p.strip() or p.startswith("/")
                   or ".." in p.split("/") for p in paths)):
        raise MDFError("protected_paths 必须列出测试、fixture 和验证配置路径", code="invalid_policy")
    policy["suites"] = parse_suite_names(policy["suites"])
    return policy


def require_stage_branch(repo, stage, data):
    branch = current_branch(repo)
    owner = data["branch"]
    roster = data["roster"]
    parsed = parse_role_branch(branch)
    if stage == "write-tests":
        if roster["qa"] == 0:
            allowed = branch == owner
        else:
            allowed = parsed is not None and parsed[1] == "qa"
    elif stage == "implement":
        if roster["dev"] == 0:
            allowed = branch == owner
        else:
            allowed = parsed is not None and parsed[1] == "dev"
    else:
        allowed = branch == owner
    if not allowed:
        raise MDFError("该阶段不允许在当前角色分支执行", code="stage_branch")


def record_stage(repo, root, data, args):
    stage = args.stage
    if stage not in STAGES:
        raise MDFError("record 需要有效阶段", code="invalid_stage")
    require_stage_branch(repo, stage, data)
    if not args.summary or not args.summary.strip():
        raise MDFError("gate 需要非空语义审查摘要", code="missing_review")
    if stage == "design":
        policy = policy_input(args.policy_file)
        require_existing_local_links(
            repo, [root / "objectives.md", root / "design.md"]
        )
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
    elif stage == "code-review":
        previous = gate(repo, root, "converge")
        if previous.get("fingerprints", {}).get("design") != current["design"]:
            raise MDFError("缺少同设计的收敛证据", code="stale_gate")
        current = require_green(repo, root, data)
    elif stage == "fact-update":
        previous = gate(repo, root, "code-review")
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


def verify(repo, root, data):
    before = require_design(repo, root, data)
    verification = manifest_verification(load_manifest(repo))
    planned = verification.plan(required_suite("feature"))
    results = []
    failed = False
    total = len(planned)
    for index, item in enumerate(planned, 1):
        try:
            result = run_verify_command(
                repo,
                item["command"],
                label=item["id"],
                index=index,
                total=total,
                timeout=item["budget"],
                entry=item["id"],
                junit=item["id"] in SUITES,
            )
            result["passed"] = True
        except MDFError as exc:
            failed = True
            result = {"command": item["command"], "passed": False,
                      "error": exc.code, "details": exc.details}
        results.append({"id": item["id"], "budget": item["budget"], **result})
    after = fingerprints(repo, root, data)
    if before["code"] != after["code"] or before["design"] != after["design"]:
        failed = True
    record = {"fingerprints": before, "results": results,
              "suites": required_suites("feature"), "all_passed": not failed}
    write_json(safe(repo, root / "gates/verification.json"), record)
    if failed:
        raise MDFError("项目验证失败或验证期间输入发生变化", code="verify_command_failed", details=record)
    return record


def check(repo, root, data, stage):
    if stage not in (*STAGES, "finish"):
        raise MDFError("check 需要有效阶段", code="invalid_stage")
    if stage == "finish":
        return require_finish(repo, root, data)
    current = require_design(repo, root, data)
    if stage in {"write-tests", "implement"}:
        require_stage_branch(repo, stage, data)
        return current
    if stage == "converge":
        for prerequisite in ("write-tests", "implement"):
            record = gate(repo, root, prerequisite)
            if record.get("fingerprints", {}).get("design") != current["design"]:
                raise MDFError("并行阶段设计不一致", code="stale_gate")
        return current
    if stage == "code-review":
        gate(repo, root, "converge")
        return require_green(repo, root, data)
    if stage == "fact-update":
        record = gate(repo, root, "code-review")
        if any(record.get("fingerprints", {}).get(key) != current[key] for key in ("code", "design")):
            raise MDFError("实现审查已过期", code="stale_gate")
        return current
    return current


def roster_patch(args):
    patch = {}
    for key in ("qa_strategy", "dev_strategy", "review_strategy"):
        value = getattr(args, key, None)
        if value is not None:
            patch[key] = value
    models = models_from_args(args)
    if models is not None:
        patch["models"] = models
    return patch


def update_roster(repo, args):
    branch = current_branch(repo)
    owner = owner_branch(branch)
    if owner != branch:
        raise MDFError("仅 owner 可更新 roster", code="stage_branch")
    try:
        root, data = locate(repo)
    except MDFError as exc:
        if exc.code != "invalid_delivery":
            raise
        updated = apply_roster_patch(
            read_roster_config(repo, owner), roster_patch(args),
            locked_qa_dev=False,
        )
        write_roster_config(repo, owner, updated)
        return updated
    locked = (root / "gates" / "design.json").exists()
    updated = apply_roster_patch(
        data["roster"], roster_patch(args), locked_qa_dev=locked,
    )
    data["roster"] = updated
    write_json(safe(repo, root / "delivery.json"), data)
    write_roster_config(repo, owner, updated)
    return updated


def command_delivery(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    from .paths import load_manifest, ensure_safe_managed_paths
    ensure_safe_managed_paths(repo)
    if load_manifest(repo).get("state") != "ready":
        raise MDFError("当前操作需要 ready 仓库", code="manifest_not_ready")
    if args.action == "roster":
        result = update_roster(repo, args)
        emit({"ok": True, "operation": "delivery-roster", "result": result})
        return
    root, data = locate(repo)
    if args.action == "record":
        result = record_stage(repo, root, data, args)
    elif args.action == "verify":
        result = verify(repo, root, data)
    elif args.action == "check":
        result = check(repo, root, data, args.stage)
    elif args.action == "integrate":
        from .delivery_git import integrate
        result = integrate(
            repo, root, data, args.test_approval,
            getattr(args, "qa_branch", None), getattr(args, "dev_branch", None),
        )
    else:
        from .gitutil import worktree_map
        trees = worktree_map(repo)
        owner = data["branch"]
        roster = data["roster"]

        def slot(name):
            return {
                "branch": name,
                "path": str(trees[name]) if name in trees else None,
            }

        result = {
            "delivery": data,
            "path": str(root.relative_to(repo)),
            "gates": [stage for stage in STAGES
                      if (root / "gates" / f"{stage}.json").exists()],
            "roster": roster,
            "worktrees": {
                "owner": slot(owner),
                "qa": [
                    {"index": index, **slot(role_branch("qa", owner, index))}
                    for index in range(1, roster["qa"] + 1)
                ],
                "dev": [
                    {"index": index, **slot(role_branch("dev", owner, index))}
                    for index in range(1, roster["dev"] + 1)
                ],
            },
        }
    emit({"ok": True, "operation": f"delivery-{args.action}", "result": result})
