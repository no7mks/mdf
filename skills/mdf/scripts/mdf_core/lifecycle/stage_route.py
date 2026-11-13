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


def _verify_evidence(repo, root, data):
    path = safe(repo, root / "verification-report.json")
    if not path.is_file():
        return None, "缺少 verification-report.json"
    report = read_json(path)
    if report.get("all_passed") is not True or report.get("branch") not in {None, data["branch"]}:
        return None, "verification-report.json 未声称本分支全部通过"
    return {"report": path.relative_to(repo).as_posix()}, None


def evidence(repo, root, data, stage):
    """返回 (证据, 缺失原因)；证据为空表示该阶段不可自动完成。"""
    if stage == "verify":
        return _verify_evidence(repo, root, data)
    plan = build_plan(repo, root, data)
    pending = {k: plan[k]["action"] for k in ("review", "verify", "fact") if plan[k]["action"] != "skip"}
    if pending:
        return None, f"catch-up 仍有待补检动作: {pending}"
    return {"baseline": plan["head"]}, None


def route(repo, root, data, yolo=False):
    _, text = _objectives(repo, root)
    items = parse_items(text)
    pending = [i for i in items if not i["checked"]]
    result = {"pending": [i["name"] for i in pending], "yolo": yolo, "next": None, "auto_completable": False}
    if not pending:
        return {**result, "state": "complete"}
    head = pending[0]
    result["next"] = head["name"]
    if head["name"] == "design":
        return {**result, "state": "awaiting_design_approval"}
    if head["name"] == "人工工作":
        return {**result, "state": "awaiting_manual_work"}
    if head["name"] in {"pr", "close-out"} and not yolo:
        return {**result, "state": "awaiting_decision_confirmation"}
    stage = next((s for s in AUTO if _is(head, s)), None)
    if stage:
        found, _ = evidence(repo, root, data, stage)
        result["auto_completable"] = found is not None
    return {**result, "state": "ready"}


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
    if stage == "verify":
        return True
    baseline = BASELINE.findall(text)
    if not baseline or git(repo, "merge-base", "--is-ancestor", baseline[-1], "HEAD", check=False).returncode:
        return False
    # 基线落后于“勾选提交”一个提交；其间只有 objectives 自身变化才算同一次完成。
    changed = set(git(repo, "diff", "--name-only", "-z", baseline[-1], "HEAD").stdout.split("\0")) - {""}
    return changed <= {rel}


def complete_stage(repo, root, data, stage):
    if stage not in AUTO:
        raise MDFError(f"{stage} 不是纯证据可判定的阶段，仅支持 {', '.join(AUTO)}", code="invalid_stage")
    path, text = _objectives(repo, root)
    rel = path.relative_to(repo).as_posix()
    item = next((i for i in parse_items(text) if _is(i, stage)), None)
    if item is None:
        raise MDFError(f"objectives 中没有 {stage} 步骤", code="invalid_stage")
    found, reason = evidence(repo, root, data, stage)
    if found is None:
        raise MDFError(reason, code="stage_evidence_missing")
    if _already_done(repo, rel, text, item, stage):
        return {"stage": stage, "completed": True, "already_completed": True, "commit": sha(repo, "HEAD")}
    earlier = [i["name"] for i in parse_items(text) if not i["checked"]][:1]
    if stage == "catch-up" and not item["checked"] and earlier and earlier[0] != item["name"]:
        raise MDFError(f"catch-up 前置未完成: {earlier[0]}", code="stage_prerequisite")
    owned = {rel, *([found["report"]] if "report" in found else [])}
    unrelated = sorted(_staged(repo) - owned)
    if unrelated:
        raise MDFError("index 存在本阶段之外的已暂存改动，已保留现场未做任何修改",
                       code="unrelated_staged_changes", details={"paths": unrelated})
    if git(repo, "status", "--porcelain", "--", rel).stdout.strip():
        raise MDFError("objectives.md 存在未提交改动，不代为提交", code="dirty_stage_files")
    path.write_text(_tick(text, item, stage, found), encoding="utf-8")
    changed = [p for p in sorted(owned) if git(repo, "status", "--porcelain", "--", p).stdout.strip()]
    git(repo, "add", "--", *changed)
    extra = sorted(_staged(repo) - owned)
    if extra:
        git(repo, "reset", "-q", "--", *changed)
        raise MDFError("暂存集超出本阶段白名单", code="unrelated_staged_changes", details={"paths": extra})
    git(repo, "commit", "-q", "-m", f"docs(delivery): 完成 {stage} 阶段", "--", *changed)
    return {"stage": stage, "completed": True, "already_completed": False, "commit": sha(repo, "HEAD"),
            "paths": changed, "evidence": found}
