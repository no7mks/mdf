"""真实 Git 快照测量、当前策略与只读执行边界。"""
import hashlib
import shutil

from mdf_test_support import *  # noqa: F403


MEASURE = skill_dir("mdf") / "scripts/measure_code.py"


def measure(python_exe, repo, *args, script=MEASURE):
    return subprocess.run([python_exe, str(script), "--repo", str(repo), *args],
                          cwd=repo, text=True, capture_output=True)


def test_historical_and_current_measurements_use_current_policy(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    path = repo / "src/large.py"
    path.write_text("pass\n" * 1001)
    init_git(repo)
    ref = git(repo, "rev-parse", "HEAD").stdout.strip()
    path.write_text("pass\n" * 700)
    current = payload(measure(python_exe, repo, "--path", "src/large.py"))["result"]
    assert current["files"][0]["value"] == 700
    assert current["files"][0]["within_split_target"] is True
    git(repo, "add", "src/large.py")
    git(repo, "commit", "-m", "test: 保存修复终点")
    repaired = git(repo, "rev-parse", "HEAD").stdout.strip()
    repaired_data = payload(measure(python_exe, repo, "--ref", repaired, "--path", "src/large.py"))["result"]
    assert repaired_data["files"][0]["within_split_target"] is True
    old = payload(measure(python_exe, repo, "--ref", ref, "--path", "src/large.py"))["result"]
    assert old["files"][0]["value"] == 1001 and old["files"][0]["within_limit"] is False
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace("    ignore: []\n",
        "    ignore: []\n    size_limits:\n      max_file_lines: 1200\n"))
    updated = payload(measure(python_exe, repo, "--ref", ref, "--path", "src/large.py"))["result"]
    assert updated["files"][0]["limit"] == 1200
    assert updated["files"][0]["within_limit"] is True
    assert updated["files"][0]["within_split_target"] is False
    original_policy = payload(measure(python_exe, repo, "--ref", ref, "--policy-ref", ref,
                                      "--path", "src/large.py"))["result"]
    assert original_policy["files"][0]["limit"] == 1000
    assert original_policy["files"][0]["split_target"] == 700
    assert original_policy["files"][0]["within_limit"] is False


def test_package_measurement_has_complete_members_and_separate_test_count(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    folder = repo / "src/package"
    folder.mkdir()
    for index in range(40):
        (folder / f"unit_{index}.py").write_text("pass\n")
    (folder / "test_case.py").write_text("pass\n")
    init_git(repo)
    data = payload(measure(python_exe, repo, "--path", "src/package/unit_0.py"))["result"]
    implementation = next(item for item in data["packages"] if not item["tests"])
    assert implementation["value"] == 40 and implementation["split_target"] == 35
    assert implementation["within_limit"] is True and implementation["within_split_target"] is False
    assert next(item for item in data["packages"] if item["tests"])["value"] == 1


def test_moving_to_wider_module_does_not_satisfy_original_split_targets(python_exe, tmp_path):
    from mdf_core.execution.modules_check import render_modules_yaml

    repo = copy_fixture(tmp_path)
    moved = repo / "moved"
    moved.mkdir()
    (moved / "large.py").write_text("pass\n" * 900)
    for index in range(39):
        (moved / f"unit_{index}.py").write_text("pass\n")
    wide = render_modules_yaml(module_name="wide", sourceset=["moved/**"],
                              lint="true", build="true", quick=SUITE_OK, smoke=SUITE_OK, release=SUITE_OK)
    wide = wide.split("modules:\n", 1)[1].replace("    ignore: []\n",
        "    ignore: []\n    size_limits:\n      max_file_lines: 2000\n      max_package_files: 100\n")
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(modules.read_text().replace("modules:\n", "modules:\n" + wide, 1))
    init_git(repo)
    data = payload(measure(python_exe, repo, "--path", "moved/large.py",
                           "--file-target", "700", "--package-target", "35"))["result"]
    assert data["files"][0]["within_split_target"] is True
    assert data["files"][0]["within_required_split_targets"] is False
    assert data["packages"][0]["within_split_target"] is True
    assert data["packages"][0]["within_required_split_targets"] is False


def test_installed_measurement_creates_no_worktree_files_or_bytecode(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    installed = repo / ".local-skill/scripts"
    shutil.copytree(MEASURE.parent, installed, ignore=shutil.ignore_patterns("__pycache__"))
    init_git(repo)

    def snapshot():
        return {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in repo.rglob("*") if path.is_file()}

    before = snapshot()
    assert_ok(measure(python_exe, repo, "--path", "src", script=installed / "measure_code.py"))
    assert snapshot() == before
    assert not list(installed.rglob("__pycache__"))
    result = measure(python_exe, repo, "--path", "../outside")
    assert result.returncode != 0 and "仓库相对" in result.stderr
