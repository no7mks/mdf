"""CodeWiki 运行环境检查不做安装。"""
from types import SimpleNamespace
from mdf_test_support import *  # noqa: F403


def test_codewiki_runtime_checks_existing_environment_without_installing(tmp_path, monkeypatch):
    load_core_module()
    from mdf_core.integrations import codewiki_runtime
    root = tmp_path / "codewiki"
    (root / "codewiki").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    python = root / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("stub")
    commands = []

    def fake_run(args, cwd):
        commands.append(args)
        return str(root) if "--show-toplevel" in args else ""

    monkeypatch.setattr(codewiki_runtime, "run", fake_run)
    result = codewiki_runtime.prepare(root)
    assert result["python"] == str(python)
    assert commands[-1] == [str(python), "-c", "from codewiki.mcp.server import server"]
    assert not any("install" in args or "clone" in args for args in commands)
