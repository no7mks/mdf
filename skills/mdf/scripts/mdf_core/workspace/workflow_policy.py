"""manifest `workflow` 配置：分支模型与 trunk 名称的唯一解释入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.paths import load_manifest, manifest_path
from mdf_core.foundation.yamlutil import parse_yaml
from mdf_core.workspace.gitutil import run, valid_branch_name

GITFLOW = "gitflow"
GITHUB_FLOW = "github-flow"
MODELS = (GITFLOW, GITHUB_FLOW)
DEFAULT_TRUNK = "master"
DEFAULT_WORKFLOW = {"model": GITFLOW, "trunk": DEFAULT_TRUNK}
# MDF 保留的分支名与前缀；trunk 不得与之冲突。
RESERVED_NAMES = frozenset({"develop", "planning"})
RESERVED_PREFIXES = (
    "feature/", "bugfix/", "release/", "on-demand-release/", "hotfix/",
    "support/", "adhoc/", "qa/", "dev/", "codex/",
)
GITHUB_FLOW_UNSUPPORTED = "github_flow_unsupported"


def _check_trunk(trunk: Any, repo: Path | None) -> str:
    if not isinstance(trunk, str) or not trunk.strip() or trunk != trunk.strip():
        raise MDFError("workflow.trunk 必须为非空分支名", code="invalid_workflow")
    if trunk == "HEAD" or not valid_branch_name(trunk):
        raise MDFError(f"workflow.trunk 不是合法分支名：{trunk}", code="invalid_workflow")
    if repo is not None and run(
        ["git", "check-ref-format", "--branch", trunk], cwd=repo, check=False,
    ).returncode:
        raise MDFError(f"workflow.trunk 不是合法分支名：{trunk}", code="invalid_workflow")
    if trunk in RESERVED_NAMES or trunk.startswith(RESERVED_PREFIXES):
        raise MDFError(f"workflow.trunk 与 MDF 保留分支冲突：{trunk}", code="invalid_workflow")
    return trunk


def parse_workflow(manifest: dict[str, Any], repo: Path | None = None) -> dict[str, str]:
    """校验并补全 `workflow`；缺省为 gitflow + master。"""
    raw = manifest.get("workflow")
    if raw is None:
        if "workflow" in manifest:
            raise MDFError("workflow 不能为 null", code="invalid_workflow")
        return dict(DEFAULT_WORKFLOW)
    if not isinstance(raw, dict) or set(raw) - {"model", "trunk"}:
        raise MDFError("workflow 只允许 model 与 trunk", code="invalid_workflow")
    model = raw.get("model", GITFLOW)
    if model not in MODELS:
        raise MDFError("workflow.model 必须为 gitflow 或 github-flow", code="invalid_workflow")
    return {"model": model, "trunk": _check_trunk(raw.get("trunk", DEFAULT_TRUNK), repo)}


def manifest_at(repo: Path, ref: str) -> dict[str, Any]:
    shown = run(["git", "show", f"{ref}:.mdf/manifest.yaml"], cwd=repo, check=False)
    if shown.returncode:
        raise MDFError(f"{ref} 缺少 .mdf/manifest.yaml", code="not_initialized")
    return parse_yaml(shown.stdout)


def workflow_config(repo: Path, ref: str | None = None) -> dict[str, str]:
    """读取工作区（或指定 ref）manifest 的 workflow；无 manifest 时取缺省。"""
    if ref is not None:
        return parse_workflow(manifest_at(repo, ref), repo)
    if not manifest_path(repo).is_file():
        return dict(DEFAULT_WORKFLOW)
    return parse_workflow(load_manifest(repo), repo)


def is_github_flow(repo: Path, ref: str | None = None) -> bool:
    return workflow_config(repo, ref)["model"] == GITHUB_FLOW


def trunk_branch(repo: Path, ref: str | None = None) -> str:
    return workflow_config(repo, ref)["trunk"]


def integration_branch(repo: Path, ref: str | None = None) -> str:
    """交付分支默认合入的分支：gitflow 为 develop，github-flow 为 trunk。"""
    config = workflow_config(repo, ref)
    return config["trunk"] if config["model"] == GITHUB_FLOW else "develop"


def permanent_trunks(repo: Path, ref: str | None = None) -> tuple[str, ...]:
    """常驻分支：gitflow 为 trunk/develop/planning；github-flow 仅 trunk，PR mode 另有短命 planning。"""
    config = workflow_config(repo, ref)
    if config["model"] == GITFLOW:
        return (config["trunk"], "develop", "planning")
    from mdf_core.workspace.merge_policy import configured
    pr = configured(repo, ref)["mode"] == "pr"
    return (config["trunk"], "planning") if pr else (config["trunk"],)


def sync_trunks(repo: Path) -> tuple[str, ...]:
    """sync 对齐的常驻分支；github-flow 的 planning 短命，不参与。"""
    config = workflow_config(repo)
    return permanent_trunks(repo) if config["model"] == GITFLOW else (config["trunk"],)


def require_gitflow(repo: Path, entry: str, ref: str | None = None) -> None:
    """github-flow 下 gitflow 专属入口一律明确报错。"""
    config = workflow_config(repo, ref)
    if config["model"] == GITHUB_FLOW:
        raise MDFError(
            f"github-flow 不支持 {entry}；主干转移入口为 trunk-pr",
            code=GITHUB_FLOW_UNSUPPORTED,
            details={"entry": entry, "trunk": config["trunk"]},
        )


def render_workflow_lines(config: dict[str, str]) -> list[str]:
    return ["workflow:", f"  model: {config['model']}", f"  trunk: {config['trunk']}"]


def render_closeout_lines(entry: dict[str, Any]) -> list[str]:
    import json
    lines = ["closeout:", f"  mode: {entry['mode']}"]
    if "provider" in entry:
        lines.append(f"  provider: {entry['provider']}")
    if "trivial_paths" in entry:
        lines.append("  trivial_paths: " + json.dumps(entry["trivial_paths"], ensure_ascii=False))
    return lines


def set_manifest_block(text: str, key: str, block: list[str], *, before: str = "implementation_roots:") -> str:
    """替换（或在 `before` 之前插入）manifest 顶层 `key:` 块，其他内容原样保留。"""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(f"{key}:")), None)
    if start is None:
        anchor = next((i for i, line in enumerate(lines) if line.startswith(before)), len(lines))
        lines[anchor:anchor] = block
    else:
        end = start + 1
        while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
            end += 1
        lines[start:end] = block
    return "\n".join(lines) + "\n"


def support_branch(major_minor: str) -> str:
    return f"support/{major_minor}"


def ci_branches(repo: Path) -> list[str]:
    """CI push 触发分支：gitflow 含 develop，github-flow 含 support/**。"""
    config = workflow_config(repo)
    if config["model"] == GITFLOW:
        return ["develop", config["trunk"]]
    return [config["trunk"], "support/**"]
