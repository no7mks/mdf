"""hook 配置限制与非阻塞错误。"""
from pathlib import Path

import pytest

from mdf_core.errors import MDFError
from mdf_core.hooks import post_gitflow_start, validate_hooks
from mdf_core.init_repo import render_manifest
from mdf_core.yamlutil import parse_yaml


@pytest.mark.parametrize("hooks", [
    [], {"unknown": {"type": "command", "path": "hook.sh"}},
    {"post-gitflow-start": "hook.sh"},
    {"post-gitflow-start": {"type": "other", "path": "hook.sh"}},
    {"post-gitflow-start": {"type": "command", "path": "/hook.sh"}},
    {"post-gitflow-start": {"type": "rule", "path": "../rule.md"}},
    {"post-gitflow-start": {"type": "rule", "path": ""}},
])
def test_invalid_hooks(hooks):
    with pytest.raises(MDFError, match="hook"):
        validate_hooks({"hooks": hooks})


@pytest.mark.parametrize("hook_type", ["command", "rule"])
def test_missing_hook_file_is_reported_without_raising(tmp_path, capsys, hook_type):
    (tmp_path / ".mdf").mkdir()
    (tmp_path / ".mdf/manifest.yaml").write_text(
        f"hooks:\n  post-gitflow-start:\n    type: {hook_type}\n    path: missing.sh\n"
    )
    result = post_gitflow_start(tmp_path, tmp_path)
    assert result["status"] == "failed"
    output = capsys.readouterr().err
    assert "不影响 start" in output
    assert output.index("开始执行 hook") < output.index("执行结束")
    assert "missing.sh" in output
    assert f"cwd={tmp_path}" in output


def test_manifest_render_preserves_hooks():
    from mdf_core.constants import BASELINES
    hooks = {"post-gitflow-start": {"type": "rule", "path": "rules/start.md"}}
    baselines = {name: {"status": "not_applicable", "reason": "测试"} for name in BASELINES}
    manifest = parse_yaml(render_manifest(baselines, None, ["src"], hooks=hooks))
    assert manifest["hooks"] == hooks
