"""托管路径检查跳过本地产物，保留配置与文档的 symlink 检查。"""
import os
from pathlib import Path

import pytest

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.paths import ensure_safe_managed_paths, managed_symlinks


@pytest.mark.parametrize("name", ["logs", "reports", "tmp", "cache"])
def test_managed_paths_do_not_descend_into_local_artifacts(tmp_path, monkeypatch, name):
    root = tmp_path / ".mdf" / name
    root.mkdir(parents=True)
    (root / "nested").mkdir()
    (root / "nested" / "escape").symlink_to(tmp_path / "outside")
    scandir = os.scandir

    def guarded_scandir(path):
        assert not Path(path).is_relative_to(root), "不应扫描本地产物目录"
        return scandir(path)

    monkeypatch.setattr(os, "scandir", guarded_scandir)
    ensure_safe_managed_paths(tmp_path)
    assert managed_symlinks(tmp_path) == []


@pytest.mark.parametrize("name", [
    ".mdf", ".mdf/manifest.yaml",
    ".mdf/config/escape", "docs/system/escape", "docs/logs/escape", "AGENTS.md",
])
def test_managed_paths_still_reject_symlinks(tmp_path, name):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(tmp_path / "outside")

    with pytest.raises(MDFError) as error:
        ensure_safe_managed_paths(tmp_path)

    assert error.value.code == "managed_symlink"
    assert error.value.details["paths"] == [name]


@pytest.mark.parametrize("name", ["logs", "reports", "tmp", "cache"])
def test_local_artifact_symlink_does_not_block_managed_paths(tmp_path, name):
    path = tmp_path / ".mdf" / name
    path.parent.mkdir()
    path.symlink_to(tmp_path / "outside")

    assert managed_symlinks(tmp_path) == [path]
    ensure_safe_managed_paths(tmp_path)
