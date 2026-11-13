"""verify 内容指纹凭证：命中不启动子进程，显式输入优先，环境/失败/产物破损一律 miss。"""
import json

from mdf_test_support import *  # noqa: F403

REPORT = "echo '<testsuite><testcase/></testsuite>' > $MDF_REPORT_DIR/r.xml"


def prepare(tmp_path, *, quick_extra="", build="true", module_extra=""):
    repo = copy_fixture(tmp_path)
    counter, flag = tmp_path / "quick.count", tmp_path / "fail.flag"
    quick = f'echo x >> {counter}; test ! -f {flag} && {REPORT}'
    manifest = repo / ".mdf/modules.yaml"
    text = manifest.read_text()
    text = text.replace('build: "true"', f'build: "{build}"\n{module_extra}', 1)
    text = text.replace(f'command: "{REPORT}"', f'command: "{quick}"{quick_extra}', 1)
    manifest.write_text(text)
    init_git(repo)
    return repo, counter, flag


def verify(python_exe, repo, *extra):
    return payload(mdf(python_exe, "verify", "smart", "--repo", str(repo), "--module", "default", *extra))["result"]


def runs(counter):
    return len(counter.read_text().split()) if counter.exists() else 0


def commit_all(repo, message="test: 调整输入"):
    git(repo, "add", "--all")
    git(repo, "commit", "-m", message)


def quick_item(result):
    return next(item for item in result["results"] if item["id"] == "quick:default")


def test_second_run_reuses_without_starting_process(python_exe, tmp_path):
    repo, counter, _ = prepare(tmp_path)
    first = verify(python_exe, repo)
    assert runs(counter) == 1 and "reused_from" not in quick_item(first)
    second = verify(python_exe, repo)
    item = quick_item(second)
    assert runs(counter) == 1 and item["passed"] and item["report"]["tests"] == 1
    assert item["reused"] is True and item["reused_from"]["key"] and item["check_duration_s"] < 5
    assert item["original_duration_s"] == quick_item(first)["original_duration_s"]
    assert Path(item["reused_from"]["evidence"]).is_dir()


def test_implementation_change_misses_but_docs_and_generated_hit(python_exe, tmp_path):
    repo, counter, _ = prepare(tmp_path)
    verify(python_exe, repo)
    (repo / "README.md").write_text("只改说明\n")
    (repo / "CHANGELOG.md").write_text("# 生成物\n")
    assert "reused_from" in quick_item(verify(python_exe, repo)) and runs(counter) == 1
    (repo / "src/service.py").write_text("changed = True\n")
    assert "reused_from" not in quick_item(verify(python_exe, repo)) and runs(counter) == 2


def test_explicit_inputs_override_generated_exclusion(python_exe, tmp_path):
    repo, counter, _ = prepare(tmp_path, quick_extra='\n      extra_inputs:\n        - "CHANGELOG.md"')
    verify(python_exe, repo)
    (repo / "CHANGELOG.md").write_text("# 被显式声明为输入\n")
    assert "reused_from" not in quick_item(verify(python_exe, repo)) and runs(counter) == 2


def test_force_reruns_and_failure_revokes_old_success(python_exe, tmp_path):
    repo, counter, flag = prepare(tmp_path)
    verify(python_exe, repo)
    assert "reused_from" in quick_item(verify(python_exe, repo))
    flag.write_text("fail\n")
    failed = mdf(python_exe, "verify", "smart", "--repo", str(repo), "--module", "default", "--force")
    assert failed.returncode != 0 and runs(counter) == 2
    flag.unlink()
    again = verify(python_exe, repo)
    assert "reused_from" not in quick_item(again) and runs(counter) == 3
    assert "reused_from" in quick_item(verify(python_exe, repo)) and runs(counter) == 3


def test_environment_mismatch_is_a_miss(python_exe, tmp_path):
    repo, counter, _ = prepare(tmp_path)
    verify(python_exe, repo)
    common = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    for path in (common / "mdf/attestations/verify").glob("*.json"):
        record = json.loads(path.read_text())
        record["env"]["python"] = "0.0.0"
        path.write_text(json.dumps(record))
    assert "reused_from" not in quick_item(verify(python_exe, repo)) and runs(counter) == 2


def test_external_state_is_never_reused(python_exe, tmp_path):
    repo, counter, _ = prepare(tmp_path, quick_extra="\n      external_state: true")
    verify(python_exe, repo)
    verify(python_exe, repo)
    assert runs(counter) == 2


def test_build_needs_intact_artifacts_or_all_downstream_hits(python_exe, tmp_path):
    build = f"echo b >> {tmp_path / 'build.count'}; mkdir -p dist; echo a > dist/out.txt"
    repo, counter, _ = prepare(tmp_path, build=build, module_extra='    build_artifacts:\n      - "dist/**"\n')
    builds = lambda: len((tmp_path / "build.count").read_text().split())
    verify(python_exe, repo)
    verify(python_exe, repo)
    assert builds() == 1 and runs(counter) == 1
    (repo / "dist/out.txt").write_text("tampered\n")
    verify(python_exe, repo)
    assert builds() == 2 and runs(counter) == 1


def test_build_without_artifacts_is_skipped_only_when_downstream_all_hit(python_exe, tmp_path):
    build = f"echo b >> {tmp_path / 'build.count'}"
    repo, counter, _ = prepare(tmp_path, build=build)
    builds = lambda: len((tmp_path / "build.count").read_text().split())
    verify(python_exe, repo)
    verify(python_exe, repo)
    assert builds() == 1 and runs(counter) == 1
    (repo / "src/service.py").write_text("changed = True\n")
    verify(python_exe, repo)
    assert builds() == 2 and runs(counter) == 2
