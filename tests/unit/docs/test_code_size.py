"""代码行数检查只覆盖源代码与测试源代码。"""
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize("name", ["src/main.py", "tests/main.test.ts", "src/View.vue"])
def test_code_size_boundary(tmp_path, name):
    load_core_module()
    from mdf_core.code_size import code_size_findings
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    path.write_text("pass\n" * 1000, encoding="utf-8")
    assert code_size_findings(tmp_path, [path]) == []
    path.write_text("pass\n" * 1001, encoding="utf-8")
    findings = code_size_findings(tmp_path, [path])
    assert [(item.code, item.path) for item in findings] == [("code.size", name)]
    assert "700 行" in findings[0].message


@pytest.mark.parametrize("name", ["config.yaml", "data.json", "README.md", "page.html", "uv.lock"])
def test_non_code_is_not_limited(tmp_path, name):
    load_core_module()
    from mdf_core.code_size import code_size_findings
    path = tmp_path / name
    path.write_text("data\n" * 1001, encoding="utf-8")
    assert code_size_findings(tmp_path, [path]) == []
