"""安装根发现：MDF_HOME 优先，无效时不回退。"""
from __future__ import annotations

import sys
from pathlib import Path

from launcher_support import REV_A, REV_B, error, invoke, link_bin, plant, plant_host, root_of


def entries(home: Path, binary_root: Path):
    launcher = binary_root / "current" / "scripts" / "mdf_launcher.py"
    host = home / ".agents" / "skills" / "mdf" / "scripts" / "mdf_launcher.py"
    return (
        (["mdf", "root"], True),
        ([sys.executable, "-B", str(launcher), "root"], False),
        (["sh", "-c", "mdf root"], True),
        ([sys.executable, "-B", str(host), "root"], False),
        (["sh", "-c", 'python3 -B "$0" root', str(host)], False),
    )


def test_explicit_home_wins_over_default(tmp_path: Path) -> None:
    home = tmp_path / "home"
    default = home / ".local" / "share" / "mdf"
    chosen = tmp_path / "opt" / "mdf"
    plant(default, REV_A)
    plant_host(home, plant(chosen, REV_B))
    link_bin(home, default)
    for args, use_path in entries(home, chosen):
        found = root_of(invoke(home, args, mdf_home=str(chosen), path_first=use_path))
        assert found.name == REV_B
        assert found.parent.parent == chosen.resolve()


def test_unset_home_uses_default(tmp_path: Path) -> None:
    home = tmp_path / "home"
    default = home / ".local" / "share" / "mdf"
    version = plant(default, REV_A)
    plant_host(home, version)
    link_bin(home, default)
    for args, use_path in entries(home, default):
        found = root_of(invoke(home, args, path_first=use_path))
        assert found.name == REV_A
        assert found.parent.parent == default.resolve()


def test_host_script_resolves_without_path_mdf(tmp_path: Path) -> None:
    home = tmp_path / "home"
    default = home / ".local" / "share" / "mdf"
    host = plant_host(home, plant(default, REV_A))
    found = root_of(invoke(home, [sys.executable, "-B", str(host), "root"]))
    assert found.name == REV_A
    assert found.parent.parent == default.resolve()
    assert not (home / ".local" / "bin" / "mdf").exists()


def test_invalid_home_does_not_fall_back(tmp_path: Path) -> None:
    home = tmp_path / "home"
    default = home / ".local" / "share" / "mdf"
    plant_host(home, plant(default, REV_A))
    link_bin(home, default)
    dangling = tmp_path / "dangling"
    plant(dangling, REV_B)
    (dangling / "current").unlink()
    (dangling / "current").symlink_to(Path("versions") / REV_B)
    (dangling / "versions" / REV_B).rename(dangling / "versions" / "moved")
    cases = ("", str(tmp_path / "missing"), str(dangling))
    for value in cases:
        for args, use_path in entries(home, default):
            body = error(invoke(home, args, mdf_home=value, path_first=use_path))
            assert body["error"] == "mdf_home_invalid"
            assert "MDF_HOME" in body["message"]
            assert REV_A not in body["message"]
