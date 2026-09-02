"""Mars Development Flow 的确定性协议与事务测试。"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from _support import run
from conftest import skill_dir

FIXTURE = Path(__file__).parent / "fixtures" / "mdf" / "valid_repo"
PRP_NAME = "prp-AB23-service-health.md"
BUG_NAME = "bug-CD34-unreleased-timeout.md"
BUG_ID = "bug-CD34"
PRP_ID_RE = re.compile(r"^prp-[A-HJ-NP-Z2-9]{4}$")
BUG_ID_RE = re.compile(r"^bug-[A-HJ-NP-Z2-9]{4}$")
JOT_ID_RE = re.compile(r"^jot-[A-HJ-NP-Z2-9]{4}$")


def mdf(python_exe: str, *args: str, cwd: Path | None = None):
    cli = skill_dir("mdf") / "scripts" / "mdf.py"
    return run([python_exe, str(cli), *args], cwd=cwd)


def assert_ok(result) -> None:
    assert result.returncode == 0, (
        f"命令失败\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def payload(result):
    assert_ok(result)
    return json.loads(result.stdout)


def copy_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    return repo


def git(repo: Path, *args: str):
    result = run(["git", *args], cwd=repo)
    assert_ok(result)
    return result


def init_git(repo: Path) -> None:
    git(repo, "init")
    git(repo, "branch", "-M", "main")
    git(repo, "config", "user.name", "MDF Test")
    git(repo, "config", "user.email", "mdf@example.invalid")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 初始化 MDF fixture")


def load_core_module():
    scripts = skill_dir("mdf") / "scripts"
    scripts_str = str(scripts.resolve())
    if scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)
    # mdf_core 是正常 package；白盒 monkeypatch 必须打到符号的
    # 定义模块（如 "mdf_core.doctor.collect_findings"），因为消费模块
    # 对可 patch 的函数一律使用 `模块.函数()` 限定访问。
    from mdf_core import (
        commands_misc,
        doctor,
        errors,
        gitutil,
        init_repo,
        moves,
    )
    from mdf_core import closeout_objects, closeout_shape, closeout_stage

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


def all_not_applicable_baselines() -> list[str]:
    names = (
        "glossary",
        "product_reference",
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
        "product_reference": "docs/product/reference/capabilities.md",
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
    change = repo / "changes" / "unreleased" / slug / "CHANGE.md"
    change.parent.mkdir(parents=True)
    change.write_text(
        (
            "---\n"
            "change_kind: feature\n"
            f"source_branch: feature/{slug}\n"
            f"proposals: [prp-AB23]\n"
            "fixed: [bug-CD34]\n"
            "closed: []\n"
            "deferred: []\n"
            "closed_resolutions: {}\n"
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
            "## Result\n\n"
            "服务健康能力已经交付。\n\n"
            "## Current Docs Updated\n\n"
            "- docs/product/reference/capabilities.md\n\n"
            "## Known Deviations\n\n"
            "None.\n"
        ),
        encoding="utf-8",
    )


def write_closeout_spec(path: Path, *, version: str, slug: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "mode": "release",
                "expected_branch": f"release/{version}",
                "version": version,
                "previous_version": "1.2.0",
                "release_date": "2026-07-29",
                "closures": [
                    {
                        "id": "prp-AB23",
                        "resolution": "fulfilled",
                        "fulfilled_in": version,
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


def prepare_release_closeout_repo(
    tmp_path: Path, slug: str = "service-health"
) -> Path:
    repo = copy_fixture(tmp_path)
    init_git(repo)
    write_unreleased_change(repo, slug)
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "feat: 准备服务健康变更")
    git(repo, "checkout", "-b", "release/1.3.0")
    return repo


def closeout_context_for(core, repo: Path, tmp_path: Path, slug: str):
    spec_path = tmp_path / "closeout.json"
    write_closeout_spec(spec_path, version="1.3.0", slug=slug)
    context = core.validate_closeout_shape(
        repo.resolve(),
        json.loads(spec_path.read_text(encoding="utf-8")),
    )
    return context
