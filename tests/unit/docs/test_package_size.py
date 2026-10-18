"""package 文件数按直属目录、实现与测试分类分别计数。"""
from mdf_test_support import *  # noqa: F403


def files(repo, names):
    result = []
    for name in names:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("pass\n")
        result.append(path)
    return result


def test_package_source_and_tests_are_not_added_together(tmp_path):
    load_core_module()
    from mdf_core.inspection.code_size import package_size_findings
    paths = files(tmp_path, [f"mixed/code_{i}.py" for i in range(50)]
                  + [f"mixed/test_case_{i}.py" for i in range(50)])
    assert package_size_findings(tmp_path, paths) == []
    paths += files(tmp_path, ["mixed/code_50.py"])
    findings = package_size_findings(tmp_path, paths)
    assert [(item.code, item.path) for item in findings] == [("package.size", "mixed")]
    assert "实现" in findings[0].message and "35" in findings[0].message
    paths += files(tmp_path, ["mixed/test_case_50.py"])
    assert len(package_size_findings(tmp_path, paths)) == 2


def test_child_packages_are_independent_and_non_source_files_do_not_count(tmp_path):
    load_core_module()
    from mdf_core.inspection.code_size import package_size_findings
    paths = files(tmp_path, [f"src/code_{i}.py" for i in range(35)]
                  + [f"src/child/code_{i}.py" for i in range(35)]
                  + [f"src/data_{i}.json" for i in range(60)])
    assert package_size_findings(tmp_path, paths) == []


def test_package_scope_counts_all_members_and_includes_deleted_source_paths(tmp_path):
    load_core_module()
    from mdf_core.inspection.code_size import package_size_findings
    paths = files(tmp_path, [f"large/code_{i}.py" for i in range(51)]
                  + [f"unrelated/code_{i}.py" for i in range(51)])
    findings = package_size_findings(tmp_path, paths, scope_paths=[tmp_path / "large/deleted.py"])
    assert [item.path for item in findings] == ["large"]


@pytest.mark.parametrize("name", ["tests/pkg/helper.py", "test/pkg/helper.ts", "src/__tests__/helper.js",
    "src/widget.test.ts", "src/widget.spec.ts", "src/widget_test.go", "src/test_widget.py", "src/WidgetTest.java"])
def test_package_test_file_conventions(tmp_path, name):
    load_core_module()
    from mdf_core.inspection.code_size import is_test_source
    assert is_test_source(Path(name))


def test_repository_ancestor_names_do_not_change_source_classification(tmp_path):
    load_core_module()
    from mdf_core.inspection.code_size import package_size_findings
    repo = tmp_path / "tests/repo"
    paths = files(repo, [f"src/code_{i}.py" for i in range(51)])
    findings = package_size_findings(repo, paths)
    assert len(findings) == 1 and "实现" in findings[0].message
