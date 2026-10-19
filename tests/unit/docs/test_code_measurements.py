"""硬限制与拆分目标分别提供工具证据，完整 package 不混合实现和测试。"""
from mdf_core.execution.modules import parse_modules
from mdf_core.inspection.code_size import code_size_measurements


def config():
    module = {"sourceset": ["src/**"], "lint": "true", "build": "true",
              "ignore": [{"pattern": "src/ignored.py", "reason": "生成文件"}],
              "size_limits": {"max_package_files": 5},
              **{name: {"command": "test", "tests": ["tests/**"]}
                 for name in ("quick", "smoke", "release")}}
    return parse_modules({"modules": {"app": module}})


def test_below_hard_limit_is_not_proof_of_split_target():
    paths = ["src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/test_case.py", "src/ignored.py"]
    result = code_size_measurements({"src/a.py": 900}, paths, config())
    file = result["files"][0]
    assert file["value"] == 900 and file["limit"] == 1000
    assert file["split_target"] == 700
    assert file["within_limit"] is True and file["within_split_target"] is False
    implementation = next(item for item in result["packages"] if not item["tests"])
    assert implementation["value"] == 4
    assert implementation["limit"] == 5 and implementation["split_target"] == 3
    assert implementation["within_limit"] is True and implementation["within_split_target"] is False
    tests = next(item for item in result["packages"] if item["tests"])
    assert tests["value"] == 1


def test_ignored_selection_does_not_measure_the_surrounding_package():
    result = code_size_measurements({"src/ignored.py": 10000}, ["src/a.py", "src/ignored.py"], config())
    assert result == {"files": [], "packages": []}
