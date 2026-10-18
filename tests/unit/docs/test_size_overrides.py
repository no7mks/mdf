"""module 规模配置的默认值、校验、重叠约束与 package 完整计数。"""
from mdf_test_support import *  # noqa: F403


def module(sourceset, **extra):
    body = {"sourceset": sourceset, "lint": "true", "build": "true",
            "quick": {"command": "true", "tests": ["**"]},
            "smoke": {"command": "true", "tests": ["**"]},
            "release": {"command": "true", "tests": ["**"]}}
    return {**body, **extra}


def config(**modules):
    load_core_module()
    from mdf_core.execution.modules import parse_modules
    return parse_modules({"modules": modules})


def write(repo, name, lines=1):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("pass\n" * lines)
    return path


def test_module_size_limits_default_and_partial_override():
    defaults = config(a=module(["a/**"])).modules["a"].size_limits
    assert (defaults.max_file_lines, defaults.max_package_files, defaults.split_percent) == (1000, 50, 70)
    limits = config(a=module(["a/**"], size_limits={"max_file_lines": 1200})).modules["a"].size_limits
    assert (limits.max_file_lines, limits.max_package_files, limits.split_percent) == (1200, 50, 70)
    assert limits.target(limits.max_file_lines) == 840


@pytest.mark.parametrize("raw", [None, [], {"unknown": 1}, {"max_file_lines": True},
    {"max_file_lines": 0}, {"max_package_files": -1}, {"max_package_files": 2.5},
    {"split_percent": "70%"}, {"split_percent": False}, {"split_percent": 0},
    {"split_percent": 101}, {"max_package_files": 1, "split_percent": 70}])
def test_invalid_size_limits_are_rejected(raw):
    load_core_module()
    from mdf_core.foundation.errors import MDFError
    with pytest.raises(MDFError) as error:
        config(a=module(["a/**"], size_limits=raw))
    assert error.value.code == "modules_invalid"


def test_all_overlapping_file_policies_keep_their_own_targets(tmp_path):
    from mdf_core.inspection.code_size import code_size_findings
    settings = config(
        a=module(["shared/**"], size_limits={"max_file_lines": 10, "split_percent": 90}),
        b=module(["shared/**"], size_limits={"max_file_lines": 20, "split_percent": 40}))
    path = write(tmp_path, "shared/main.py", 15)
    findings = code_size_findings(tmp_path, [path], config=settings)
    assert len(findings) == 1 and "module a" in findings[0].message and "9 行" in findings[0].message
    path.write_text("pass\n" * 21)
    findings = code_size_findings(tmp_path, [path], config=settings)
    assert len(findings) == 2
    assert "9 行" in findings[0].message and "8 行" in findings[1].message


def test_unmatched_files_use_defaults_and_ignore_takes_priority(tmp_path):
    from mdf_core.inspection.code_size import code_size_findings
    settings = config(a=module(["lib/**"], size_limits={"max_file_lines": 2000}))
    path = write(tmp_path, "src/main.py", 1001)
    findings = code_size_findings(tmp_path, [path], config=settings)
    assert len(findings) == 1 and "1000" in findings[0].message and "700 行" in findings[0].message
    settings = config(a=module(["src/**"], ignore=[{"pattern": "src/main.py", "reason": "外部文件"}]))
    path.write_bytes(b"\xff")
    assert code_size_findings(tmp_path, [path], config=settings) == []


def test_package_counts_all_members_for_each_policy_and_separates_tests(tmp_path):
    from mdf_core.inspection.code_size import package_size_findings
    settings = config(a=module(["pkg/*.py"], size_limits={"max_package_files": 3, "split_percent": 100}),
                      b=module(["pkg/unit_*.py"], size_limits={"max_package_files": 5, "split_percent": 60}))
    paths = [write(tmp_path, f"pkg/unit_{i}.py") for i in range(4)]
    paths += [write(tmp_path, f"pkg/test_case_{i}.py") for i in range(3)]
    findings = package_size_findings(tmp_path, paths, config=settings)
    assert len(findings) == 1 and "实现" in findings[0].message and "module a" in findings[0].message
    assert "3 个" in findings[0].message
    paths += [write(tmp_path, "pkg/unit_4.py"), write(tmp_path, "pkg/unit_5.py")]
    findings = package_size_findings(tmp_path, paths, config=settings)
    assert len(findings) == 2 and "module b" in findings[1].message


def test_unmatched_package_members_keep_default_policy(tmp_path):
    from mdf_core.inspection.code_size import package_size_findings
    settings = config(a=module(["pkg/unit_*.py"], size_limits={"max_package_files": 100}))
    paths = [write(tmp_path, f"pkg/unit_{i}.py") for i in range(51)]
    assert package_size_findings(tmp_path, paths, config=settings) == []
    paths += [write(tmp_path, "pkg/helper.py")]
    findings = package_size_findings(tmp_path, paths, config=settings)
    assert len(findings) == 1 and "52" in findings[0].message and "35 个" in findings[0].message


def test_ignored_scope_path_does_not_trigger_package_policy(tmp_path):
    from mdf_core.inspection.code_size import package_size_findings
    settings = config(a=module(["pkg/**"], ignore=[{"pattern": "pkg/generated.py", "reason": "生成文件"}]))
    paths = [write(tmp_path, f"pkg/unit_{i}.py") for i in range(51)]
    ignored = write(tmp_path, "pkg/generated.py")
    paths.append(ignored)
    assert package_size_findings(tmp_path, paths, scope_paths=[ignored], config=settings) == []
    assert len(package_size_findings(tmp_path, paths, config=settings)) == 1
