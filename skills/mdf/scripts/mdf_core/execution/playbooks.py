"""playbook：`tests/playbooks/` 下由 Agent 执行的测试手册；按 frontmatter 归属 suite。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mdf_core.foundation.errors import MDFError
from mdf_core.workspace.gitutil import ensure_clean, run

PLAYBOOK_DIR = "tests/playbooks"
PENDING_FILE = "pending.json"
PLAYBOOK_SUITES = ("release",)
STEP_RE = re.compile(r"## (S\d{2}) \S")
FENCE_RE = re.compile(r" {0,3}(`{3,}|~{3,})")


def step_ids(body: str) -> list[str]:
    """fenced code block 外的 `## Sxx` 标题；fence 以同字符且不短于开头的行关闭。"""
    steps, fence = [], None
    for line in body.splitlines():
        marker = FENCE_RE.match(line)
        if fence is None:
            if marker:
                fence = marker.group(1)
            elif step := STEP_RE.match(line):
                steps.append(step.group(1))
        elif (
            marker
            and marker.group(1)[0] == fence[0]
            and len(marker.group(1)) >= len(fence)
            and not line[marker.end():].strip()
        ):
            fence = None
    return steps


def _tracked(repo: Path) -> list[str]:
    result = run(["git", "ls-files", "-z", "--", PLAYBOOK_DIR], cwd=repo, check=False)
    if result.returncode:
        return []
    return sorted(raw for raw in result.stdout.split("\0") if raw.endswith(".md"))


def parse_playbook(repo: Path, rel: str, named: set[str]) -> dict[str, Any]:
    from mdf_core.foundation.yamlutil import read_frontmatter

    def invalid(message: str) -> MDFError:
        return MDFError(f"playbook {rel} {message}", code="invalid_playbook")

    try:
        meta, body = read_frontmatter(repo / rel)
    except MDFError as exc:
        raise invalid(f"frontmatter 无效: {exc}") from exc
    suites = meta.get("suites")
    if (
        not isinstance(suites, list)
        or not suites
        or any(not isinstance(name, str) for name in suites)
        or len(set(suites)) != len(suites)
    ):
        raise invalid("的 suites 必须为非空且不重复的名称列表")
    unknown = [name for name in suites if name not in PLAYBOOK_SUITES and name not in named]
    if unknown:
        raise invalid(f"的 suites 只能是 release 或已声明的 named suite: {', '.join(unknown)}")
    steps = step_ids(body)
    if not steps:
        raise invalid("至少需要一个 `## S<两位数> <标题>` 步骤")
    if len(set(steps)) != len(steps):
        raise invalid("的步骤 id 重复")
    return {"path": rel, "suites": suites, "steps": steps}


def load_playbooks(repo: Path) -> list[dict[str, Any]]:
    from mdf_core.execution.modules import load_modules

    named = set(load_modules(repo).named_owner())
    return [parse_playbook(repo, rel, named) for rel in _tracked(repo)]


def playbooks_for(repo: Path, suite: str) -> list[dict[str, Any]]:
    return [item for item in load_playbooks(repo) if suite in item["suites"]]


def playbook_items(repo: Path, suite: str) -> list[dict[str, Any]]:
    """plan 条目；command 为 `playbook:<path>`，供 close-out 比对序列。"""
    return [
        {"id": f"playbook:{item['path']}", "entry": suite, "command": f"playbook:{item['path']}",
         "playbook": item["path"]}
        for item in playbooks_for(repo, suite)
    ]


def _head(repo: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()


def create_pending(
    repo: Path, *, scope: str, suite: str, branch: str | None, playbooks: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    from mdf_core.execution.reports import new_report_dir

    path = new_report_dir(repo, f"{suite}-playbooks")
    rel = str(path.relative_to(repo))
    state = {
        "scope": scope, "suite": suite, "branch": branch, "head": _head(repo),
        "playbooks": [{"path": item["path"], "steps": item["steps"]} for item in playbooks],
        "results": results,
    }
    (path / PENDING_FILE).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    return {"suite": suite, "report_dir": rel, "playbooks": [item["path"] for item in playbooks]}


def _invalid_report(message: str) -> MDFError:
    return MDFError(message, code="invalid_playbook_report")


def load_pending(
    repo: Path, raw: str, *, scope: str, evidence: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    from mdf_core.execution.run_logs import REPORTS

    root = (repo / REPORTS).resolve()
    path = repo / raw
    if path.is_symlink() or not path.is_dir() or path.resolve().parent != root:
        raise _invalid_report(f"--record 须指向 {REPORTS}/ 下的 playbook 报告目录: {raw}")
    pending = path / PENDING_FILE
    if not pending.is_file():
        raise _invalid_report(f"报告目录缺少 {PENDING_FILE}: {raw}")
    state = json.loads(pending.read_text(encoding="utf-8"))
    if state.get("scope") != scope:
        raise _invalid_report(f"pending scope 为 {state.get('scope')}，与本次 {scope} 不一致")
    if state.get("head") != _head(repo):
        raise _invalid_report("HEAD 已变化；丢弃本轮 pending 并重跑验证")
    if evidence is not None:
        status = run(["git", "status", "--porcelain", "-z", "--untracked-files=all"], cwd=repo).stdout
        dirty = [entry[3:] for entry in status.split("\0") if entry]
        if any(rel != evidence for rel in dirty):
            ensure_clean(repo)
    return path, state


def record_playbooks(repo: Path, path: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    """收录 Agent 写的 JUnit；步骤须与 pending 清单一一对应。"""
    from mdf_core.execution.reports import summarize

    suite = state["suite"]
    error = None
    try:
        summarize(repo, path, suite)
    except MDFError as exc:
        if exc.code in {"invalid_test_report", "missing_test_report"}:
            raise
        error = exc.code
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    actual = [(case["name"], test["name"]) for case in summary["cases"] for test in case["tests"]]
    expected = [(item["path"], step) for item in state["playbooks"] for step in item["steps"]]
    if sorted(actual) != sorted(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise _invalid_report(
            f"JUnit 与 playbook 步骤不一致；缺少 {missing}，多出 {extra}"
            + ("" if len(set(actual)) == len(actual) else "；存在重复 testcase")
        )
    cases = {case["name"]: case for case in summary["cases"]}
    report = {"suite": suite, "path": summary["path"]}
    entries = []
    for item in state["playbooks"]:
        passed = cases[item["path"]]["result"] == "passed"
        entries.append({
            "id": f"playbook:{item['path']}", "entry": suite, "command": f"playbook:{item['path']}",
            "playbook": item["path"], "passed": passed, "report": report,
            **({} if passed else {"error": error or "test_report_failed"}),
        })
    return entries
