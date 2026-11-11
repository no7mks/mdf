"""Mars Development Flow 的确定性协议与事务测试。"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from _support import run
from conftest import skill_dir

FIXTURE = Path(__file__).parent / "fixtures" / "mdf" / "valid_repo"
PRP_NAME = "prp-0001-service-health.html"
BUG_NAME = "bug-CD34-unreleased-timeout.md"
BUG_ID = "bug-CD34"
PRP_ID = "prp-0001"
PRP_ID_RE = re.compile(r"^prp-[0-9]{2}(?:[0-9][A-HJ-NP-Z0-9]|[A-HJ-NP-Z][0-9])$")
BUG_ID_RE = re.compile(r"^bug-[A-HJ-NP-Z0-9]{4}$")
JOT_ID_RE = re.compile(r"^jot-[A-HJ-NP-Z0-9]{4}$")


def write_release_objectives(
    tmp_path: Path, name: str = "release-objectives.md",
) -> Path:
    path = tmp_path / name
    path.write_text(
        "# 发布目标\n\n"
        "- needs_design: no\n"
        "- has_dev: no\n\n"
        "## 步骤\n\n"
        "- [x] 确认工作线与范围（start）\n"
        "- [x] integrate（无联调工作线：start 写入时已勾）\n"
        "- [x] 完成预发布工作\n"
        "- [x] owner 开发（has_dev: no）\n"
        "- [x] converge（has_dev: no）\n"
        "- [ ] lint\n"
        "- [ ] code-review\n"
        "- [ ] verify branch\n"
        "- [ ] fact audit\n"
        "- [ ] catch-up\n"
        "- [ ] close-out\n\n"
        "## 工作线\n\n不联调\n\n"
        "本版收口与预发布验收。\n",
        encoding="utf-8",
    )
    return path


def write_work_objectives(
    tmp_path: Path, name: str = "work-objectives.md",
) -> Path:
    path = tmp_path / name
    path.write_text(
        "# 目标\n\n- needs_design: no\n\n"
        "- [ ] 修复\n- [ ] converge\n- [ ] verify branch\n- [ ] fact audit\n- [ ] catch-up\n",
        encoding="utf-8",
    )
    return path


def mdf(python_exe: str, *args: str, cwd: Path | None = None):
    """调用同一进程内的 CLI，避免每个命令再起一个 Python 解释器。"""
    scripts = str((skill_dir("mdf") / "scripts").resolve())
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from mdf_core.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    previous = os.getcwd()
    try:
        if cwd is not None:
            os.chdir(cwd)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
            stderr
        ):
            try:
                code = main(list(args))
            except SystemExit as exc:
                raw = exc.code
                if raw is None:
                    code = 0
                elif isinstance(raw, int):
                    code = raw
                else:
                    code = 1
    finally:
        if cwd is not None:
            os.chdir(previous)
    cli = skill_dir("mdf") / "scripts" / "mdf.py"
    return subprocess.CompletedProcess(
        args=[python_exe, str(cli), *args],
        returncode=code,
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
    )


def assert_ok(result) -> None:
    assert result.returncode == 0, (
        f"命令失败\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def payload(result):
    assert_ok(result)
    return json.loads(result.stdout)


def fact_audit_view(data: dict) -> dict:
    """统一 full/paths 机械 payload 与 against/branch→against 的 result.audit 视图。"""
    result = data.get("result")
    if isinstance(result, dict) and "audit" in result:
        audit = dict(result["audit"])
        audit["implementation_paths"] = result.get(
            "implementation_paths", audit.get("implementation_paths", [])
        )
        audit["document_paths"] = result.get(
            "document_paths", audit.get("document_paths", [])
        )
        audit["ignored"] = result.get("ignored", audit.get("ignored", []))
        audit["base"] = result.get("against", audit.get("base"))
        audit["mode"] = data.get("mode", result.get("mode"))
        audit["semantic_review"] = data.get("semantic_review")
        audit["against"] = result.get("against")
        return audit
    return data


def copy_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo, ignore=shutil.ignore_patterns("__pycache__"))
    return repo


def proposal_markdown(path: Path) -> str:
    from mdf_core.foundation.yamlutil import read_frontmatter, frontmatter_span
    _, body = read_frontmatter(path)
    text = path.read_text()
    start, end, _ = frontmatter_span(text)
    return "---\n" + text[start:end] + "\n---\n\n" + body


def proposal_html(text: str) -> str:
    from mdf_core.documents.html_documents import render_html
    from mdf_core.foundation.yamlutil import frontmatter_span, parse_yaml
    start, end, body_start = frontmatter_span(text)
    rendered = render_html(parse_yaml(text[start:end]), text[body_start:])
    a, b, _ = frontmatter_span(rendered)
    return rendered[:a] + text[start:end] + rendered[b:]


def git(repo: Path, *args: str):
    result = run(["git", *args], cwd=repo)
    assert_ok(result)
    return result


def init_git(repo: Path) -> None:
    # 提交身份由 conftest 通过环境变量提供，省去逐仓库 config 调用。
    # 一次 shell 完成 init/add/commit，少两次 git 进程启动。
    result = run(
        [
            "sh",
            "-c",
            "git init --initial-branch=main --template= && "
            "git add --all && "
            'git commit --quiet -m "test: 初始化 MDF fixture"',
        ],
        cwd=repo,
    )
    assert_ok(result)


def checkout_develop(repo: Path) -> None:
    git(repo, "checkout", "-b", "develop")


def planning_worktree(python_exe: str, repo: Path) -> Path:
    data = payload(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))
    return Path(data["worktree"])


def load_core_module():
    scripts = skill_dir("mdf") / "scripts"
    scripts_str = str(scripts.resolve())
    if scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)
    # mdf_core 是正常 package；白盒 monkeypatch 必须打到符号的
    # 定义模块（如 "mdf_core.inspection.doctor.collect_findings"），因为消费模块
    # 对可 patch 的函数一律使用 `模块.函数()` 限定访问。
    from mdf_core import commands_misc
    from mdf_core.inspection import doctor
    from mdf_core.foundation import errors
    from mdf_core.workspace import gitutil, init_repo
    from mdf_core.documents import moves
    from mdf_core.lifecycle import closeout_objects, closeout_shape, closeout_stage

    return SimpleNamespace(
        os=os,
        shutil=shutil,
        MDFError=errors.MDFError,
        Finding=errors.Finding,
        apply_closeout=closeout_stage.apply_closeout,
        close_object_text=closeout_objects.close_object_text,
        summarize_closeout=closeout_stage.summarize_closeout,
        validate_closeout_shape=closeout_shape.validate_closeout_shape,
        collect_findings=doctor.collect_findings,
        command_archive=commands_misc.command_archive,
        git_directory=gitutil.git_directory,
        replacement_plan=moves.replacement_plan,
        apply_moves_and_rewrites=moves.apply_moves_and_rewrites,
        write_files=init_repo.write_files,
    )


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} 不在 {path} 中"
    path.write_text(text.replace(old, new), encoding="utf-8")


SUITE_OK = "echo '<testsuite><testcase/></testsuite>' > $MDF_REPORT_DIR/r.xml"


def modules_yaml(repo: Path) -> Path:
    return repo / ".mdf" / "modules.yaml"


def patch_module_command(repo: Path, entry: str, transform) -> None:
    """改写 default module 的 lint/build 命令，或 suite 的 command 字符串。"""
    path = modules_yaml(repo)
    text = path.read_text(encoding="utf-8")
    if entry in ("lint", "build"):
        old = f'    {entry}: "'
        start = text.index(old) + len(old)
        end = text.index('"', start)
        path.write_text(text[:start] + transform(text[start:end]) + text[end:])
        return
    marker = f"    {entry}:\n      command: \""
    start = text.index(marker) + len(marker)
    end = text.index('"', start)
    path.write_text(text[:start] + transform(text[start:end]) + text[end:])


def set_modules_budget(repo: Path, suite: str, seconds: int) -> None:
    path = modules_yaml(repo)
    text = path.read_text(encoding="utf-8")
    if text.rstrip().endswith("named: []") or "\nnamed: []\n" in text:
        pass
    if "\nbudgets:\n" in text:
        import re

        text = re.sub(
            rf"(budgets:\n(?:  .*\n)*?)(  {suite}: )\d+",
            rf"\g<1>\g<2>{seconds}",
            text,
            count=1,
        )
        if f"  {suite}:" not in text.split("budgets:\n", 1)[-1]:
            text = text.replace("budgets:\n", f"budgets:\n  {suite}: {seconds}\n", 1)
    else:
        text = text.rstrip() + f"\nbudgets:\n  {suite}: {seconds}\n"
    path.write_text(text, encoding="utf-8")


def verification_args(command: str = "true") -> list[str]:
    result: list[str] = []
    for name in ("lint", "build", "quick", "smoke", "release"):
        result.extend([f"--{name}", command])
    return result


def all_not_applicable_baselines() -> list[str]:
    names = (
        "glossary",
        "user_guide",
        "system_boundary",
        "architecture",
        "interfaces",
        "data",
        "operations",
        "deviations",
    )
    result: list[str] = []
    for name in names:
        result.extend(
            ["--baseline", f"{name}=not_applicable:test fixture has no {name}"]
        )
    return result


def fixture_documented_baselines() -> list[str]:
    values = {
        "glossary": "GLOSSARY.md",
        "user_guide": "docs/user-guide/README.md",
        "system_boundary": "docs/system/overview.md",
        "architecture": "docs/system/architecture/current.md",
        "interfaces": "docs/system/interfaces/api.md",
        "data": "docs/system/data/model.md",
        "operations": "docs/system/operations/runbook.md",
        "deviations": "docs/system/deviations.md",
    }
    result: list[str] = []
    for name, path in values.items():
        result.extend(["--baseline", f"{name}=documented:{path}"])
    return result


def closeout_cli_args(*extra: str) -> list[str]:
    return list(extra)


def write_unreleased_change(repo: Path, slug: str) -> None:
    proposal = repo / "docs/proposals" / PRP_NAME
    text = proposal.read_text()
    proposal.write_text(text.replace("status: ready", "status: implemented"))
    change = repo / "changes" / "unreleased" / slug / "CHANGE.md"
    change.parent.mkdir(parents=True)
    change.write_text(
        (
            "---\n"
            "change_kind: feature\n"
            f"source_branch: feature/{slug}\n"
            f"proposals: [prp-0001]\n"
            "fixed: [bug-CD34]\n"
            "closed: []\n"
            "deferred: []\n"
            "adrs: []\n"
            "release_notes:\n"
            "  Added:\n"
            '    - "交付可验证的服务健康能力"\n'
            "breaking: false\n"
            "evidence:\n"
            "  tests: [tests/test_service.py]\n"
            '  commands: ["python -m pytest"]\n'
            "  artifacts: []\n"
            "---\n\n"
            "# Change\n\n"
            "## 结果\n\n"
            "服务健康能力已经交付。\n\n"
            "## 已更新的当前文档\n\n"
            "- docs/user-guide/README.md\n\n"
            "## 已知偏差\n\n"
            "无。\n"
        ),
        encoding="utf-8",
    )


def write_closeout_spec(path: Path, *, version: str, slug: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "mode": "release",
                "expected_branch": f"release/{version}",
                "version": version,
                "previous_version": "1.2.0",
                "release_date": "2026-07-29",
                "closures": [
                    {
                        "id": "prp-0001",
                        "resolution": "released",
                        "released_in": version,
                    },
                    {
                        "id": "bug-CD34",
                        "resolution": "fixed",
                        "fixed_in": version,
                    },
                ],
                "validation_commands": ["true"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def seed_verify_branch(python_exe: str, repo: Path) -> None:
    """写入可复用的 verification-report.json；release-closeout 只复用、不重跑验证。"""
    branch = git(repo, "branch", "--show-current").stdout.strip()
    folder = branch.split("/", 1)[1]
    root = repo / "changes" / "unreleased" / folder
    root.mkdir(parents=True, exist_ok=True)
    review = root / "code-review.md"
    if not review.is_file():
        review.write_text("# 审查记录\n\n无未解决问题。\n", encoding="utf-8")
        git(repo, "add", "--", str(review.relative_to(repo)))
        git(repo, "commit", "-m", "test: 审查记录")
    payload(mdf(python_exe, "verify", "--scope", "branch", "--repo", str(repo)))
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 提交 verify.branch")


def prepare_release_closeout_repo(
    tmp_path: Path, slug: str = "service-health",
    *, python_exe: str | None = None,
) -> Path:
    repo = copy_fixture(tmp_path)
    replace(
        repo / "docs/bugs" / BUG_NAME,
        "status: open",
        "status: closed\nfixed_in: 1.3.0",
    )
    init_git(repo)
    replace(repo / "docs/proposals" / PRP_NAME, "status: ready", "status: implemented")
    write_unreleased_change(repo, slug)
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "feat: 准备服务健康变更")
    git(repo, "checkout", "-b", "release/1.3.0")
    if python_exe is not None:
        seed_verify_branch(python_exe, repo)
    return repo


def closeout_context_for(core, repo: Path, tmp_path: Path, slug: str):
    spec_path = tmp_path / "closeout.json"
    write_closeout_spec(spec_path, version="1.3.0", slug=slug)
    context = core.validate_closeout_shape(
        repo.resolve(),
        json.loads(spec_path.read_text(encoding="utf-8")),
    )
    return context
