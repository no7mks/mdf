"""init 写入的冲突拒绝与失败现场。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_init_refuses_to_overwrite_unexpected_files(tmp_path: Path):
    core = load_core_module()
    existing = tmp_path / "docs" / "README.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("keep me\n", encoding="utf-8")

    with pytest.raises(core.MDFError) as caught:
        core.write_files({existing: "overwritten\n"})
    assert caught.value.code == "init_collision"
    assert existing.read_text(encoding="utf-8") == "keep me\n"


def test_init_write_failure_leaves_partial_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    core = load_core_module()
    replaced_existing = tmp_path / "CHANGELOG.md"
    replaced_existing.write_text("original changelog\n", encoding="utf-8")
    created = tmp_path / "docs" / "README.md"
    blocked = tmp_path / "AGENTS.md"
    files = {
        replaced_existing: "updated changelog\n",
        created: "# Docs\n",
        blocked: "# Agents\n",
    }
    original_write = Path.write_text

    def fail_on_blocked(path, *args, **kwargs):
        if path == blocked:
            raise OSError("injected write failure")
        return original_write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_on_blocked)
    with pytest.raises(OSError, match="injected write failure"):
        core.write_files(files, replace_allowed={replaced_existing})

    assert (
        replaced_existing.read_text(encoding="utf-8") == "updated changelog\n"
    )
    assert created.read_text(encoding="utf-8") == "# Docs\n"
    assert not blocked.exists()
