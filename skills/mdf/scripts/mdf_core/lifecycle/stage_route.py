"""delivery route / complete-stage：按 objectives 清单路由，并只自动完成纯证据可判定的阶段。"""
import re

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.catchup_plan import BASELINE, build_plan
from mdf_core.lifecycle.delivery_state import git, read_json, safe
from mdf_core.workspace.merge_policy import sha

ITEM = re.compile(r"(?m)^- \[([ xX])\] (.+?)[ \t]*$")
AUTO = ("catch-up", "verify")


def parse_items(text):
    return [{"checked": mark != " ", "label": label, "name": label.split("（", 1)[0].strip()}
            for mark, label in ITEM.findall(text)]


def _is(item, stage):
    return item["name"] == stage or item["name"].startswith(stage + " ")


def _objectives(repo, root):
    path = safe(repo, root / "objectives.md")
    return path, path.read_text(encoding="utf-8")


def _verify_evidence(repo, root, data, item):
    path = safe(repo, root / "verification-report.json")
    if not path.is_file():
        return None, ("缺少 verification-report.json", {"missing": "verification-report.json"})
    report = read_json(path)
    expected = {"stage": "verify", "expected_scope": "smart" if item["name"] == "verify smart" else "branch",
                "expected_branch": data["branch"], "actual_scope": report.get("scope"),
                "actual_branch": report.get("branch")}
    if (report.get("all_passed") is not True or report.get("scope") != expected["expected_scope"]
            or report.get("branch") != data["branch"]):
        return None, ("verification-report.json 未声称本分支本 scope 全部通过", expected)
    if report["scope"] == "branch":
        from mdf_core.execution.verification import recorded_suites, required_suites, suites_cover
        from mdf_core.workspace.gitutil import branch_details
        kind = branch_details(data["branch"])["kind"]
        if not suites_cover(recorded_suites(report), required_suites(kind)):
            return None, ("branch 报告未覆盖必选 suite", {**expected, "suites": report.get("suites")})
    else:
        results = report.get("results")
        if (not isinstance(results, list) or not results
                or any(not isinstance(item, dict) or item.get("passed") is False
                       or item.get("exit_code") != 0 for item in results)):
            return None, ("smart 报告需要非空且逐项通过的 results", expected)
    found = {"report": path.relative_to(repo).as_posix()}
    if report["scope"] == "branch":
        summary = safe(repo, root / "verification-report.md")
        if summary.is_file():
            found["summary"] = summary.relative_to(repo).as_posix()
    return found, None


def evidence(repo, root, data, item, stage):
    """返回 (证据, (原因, details))；证据为空表示该阶段不可自动完成。"""
    if stage == "verify":
        return _verify_evidence(repo, root, data, item)
    plan = build_plan(repo, root, data)
    pending = {k: plan[k]["action"] for k in ("review", "verify", "fact") if plan[k]["action"] != "skip"}
    if pending:
        return None, (f"catch-up 仍有待补检动作: {pending}", {"stage": stage, "pending": pending})
    return {"baseline": plan["head"]}, None


def route(repo, root, data, yolo=False):
    _, text = _objectives(repo, root)
    items = parse_items(text)
    pending = [i for i in items if not i["checked"]]
    result = {"pending": [i["name"] for i in pending], "yolo": yolo, "next": None, "auto_completable": False}
    if not pending:
        return _after_checklist(repo, data, result, yolo)
    head = pending[0]
    result["next"] = head["name"]
    if head["name"] == "design" and not yolo:
        return {**result, "state": "awaiting_design_approval"}
    if head["name"] == "人工工作":
        return {**result, "state": "awaiting_manual_work"}
    if head["name"] in {"pr", "close-out"} and not yolo:
        return {**result, "state": "awaiting_decision_confirmation"}
    stage = next((s for s in AUTO if _is(head, s)), None)
    if stage:
        found, _ = evidence(repo, root, data, head, stage)
        result["auto_completable"] = found is not None
    return {**result, "state": "ready"}


def _after_checklist(repo, root_data, result, yolo):
    """清单勾完后：PR mode 走 pr → close-out → complete；local 还要核收口记录或已合入。"""
    data = root_data
    from mdf_core.lifecycle.publish import state_path
    from mdf_core.workspace.merge_policy import ancestor, configured
    path = state_path(repo, data["branch"])
    state = read_json(path) if path.is_file() else None
    mode = configured(repo)["mode"]

    def gated(nxt):
        return {**result, "next": nxt, "state": "ready" if yolo else "awaiting_decision_confirmation"}

    if mode == "pr":
        if not state or not state.get("merge_commit"):
            return gated("pr")
        if not state.get("completed"):
            return gated("close-out")
        return {**result, "state": "complete", "next": None}
    target = data.get("target") or "develop"
    merged = ancestor(repo, "HEAD", f"refs/heads/{target}")
    if (state and state.get("completed")) or merged:
        return {**result, "state": "complete", "next": None}
    return gated("close-out")


def _staged(repo):
    return {p for p in git(repo, "diff", "--cached", "--name-only", "-z").stdout.split("\0") if p}


def _tick(text, item, stage, found):
    updated = text.replace(f"- [ ] {item['label']}", f"- [x] {item['label']}", 1)
    if stage == "catch-up":
        line = f"catch-up 基线：{found['baseline']}"
        if BASELINE.search(updated):
            updated = BASELINE.sub(line, updated)
        else:
            updated = updated.replace(f"- [x] {item['label']}", f"- [x] {item['label']}\n  - {line}", 1)
    return updated


def _already_done(repo, rel, text, item, stage):
    if not item["checked"]:
        return False
    if git(repo, "status", "--porcelain", "--", rel).stdout.strip():
        return False
    if stage == "verify":
        return True
    baseline = BASELINE.findall(text)
    if not baseline or git(repo, "merge-base", "--is-ancestor", baseline[-1], "HEAD", check=False).returncode:
        return False
    # 基线落后于“勾选提交”一个提交；其间只有 objectives 自身变化才算同一次完成。
    changed = set(git(repo, "diff", "--name-only", "-z", baseline[-1], "HEAD").stdout.split("\0")) - {""}
    return changed <= {rel}


def _dirty_names(repo):
    raw = git(repo, "status", "--porcelain", "-z").stdout.split("\0")
    names = []
    index = 0
    while index < len(raw):
        entry = raw[index]
        index += 1
        if len(entry) < 4:
            continue
        names.append(entry[3:])
        if "R" in entry[:2]:
            index += 1
    return names


def complete_stage(repo, root, data, stage):
    from mdf_core.workspace.gitutil import current_branch, git_in_progress_head
    if git_in_progress_head(repo):
        raise MDFError("存在未完成的 merge、cherry-pick 或 revert", code="unfinished_merge")
    if current_branch(repo) != data["branch"]:
        raise MDFError("complete-stage 须在 owner worktree 执行", code="not_owner")
    if stage not in AUTO:
        raise MDFError(f"{stage} 不是纯证据可判定的阶段，仅支持 {', '.join(AUTO)}", code="invalid_stage")
    path, text = _objectives(repo, root)
    rel = path.relative_to(repo).as_posix()
    items = parse_items(text)
    item = next((i for i in items if _is(i, stage)), None)
    if item is None:
        raise MDFError(f"objectives 中没有 {stage} 步骤", code="invalid_stage")
    found, reason = evidence(repo, root, data, item, stage)
    if found is None:
        raise MDFError(reason[0], code="stage_evidence_missing", details=reason[1])
    if _already_done(repo, rel, text, item, stage):
        return {"stage": stage, "completed": True, "already_completed": True, "commit": sha(repo, "HEAD")}
    earlier = [i["name"] for i in items[:items.index(item)] if not i["checked"]]
    if earlier:
        raise MDFError(f"{stage} 前置未完成: {', '.join(earlier)}", code="stage_prerequisite",
                       details={"stage": stage, "pending": earlier})
    owned = {rel, *(found[k] for k in ("report", "summary") if k in found)}
    unrelated = sorted(_staged(repo) - owned)
    if unrelated:
        raise MDFError("index 存在本阶段之外的已暂存改动，已保留现场未做任何修改",
                       code="unrelated_staged_changes", details={"paths": unrelated})
    if stage == "catch-up":
        from mdf_core.lifecycle.catchup_plan import classify
        foreign = sorted(p for p in _dirty_names(repo) if p != rel and classify(p) != "material")
        if foreign:
            raise MDFError("catch-up 不接受非材料的未提交改动", code="dirty_worktree", details={"paths": foreign})
    desired = _tick(text, item, stage, found)
    if git(repo, "status", "--porcelain", "--", rel).stdout.strip():
        if path.read_text(encoding="utf-8") != desired:
            raise MDFError("objectives.md 存在未提交改动，不代为提交", code="dirty_stage_files")
    else:
        path.write_text(desired, encoding="utf-8")
    changed = [p for p in sorted(owned) if git(repo, "status", "--porcelain", "--", p).stdout.strip()]
    git(repo, "add", "--", *changed)
    extra = sorted(_staged(repo) - owned)
    if extra:
        git(repo, "reset", "-q", "--", *changed)
        raise MDFError("暂存集超出本阶段白名单", code="unrelated_staged_changes", details={"paths": extra})
    git(repo, "commit", "-q", "-m", f"docs(delivery): 完成 {stage} 阶段", "--", *changed)
    return {"stage": stage, "completed": True, "already_completed": False, "commit": sha(repo, "HEAD"),
            "paths": changed, "evidence": found}
