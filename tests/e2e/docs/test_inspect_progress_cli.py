"""检查命令实时输出进度，stdout 与错误仍可按 JSON 解析。"""
import select
import time

from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize("command", ["doctor", "validate", "fact-audit"])
def test_inspect_progress_keeps_json_and_is_logged(command, python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = mdf(python_exe, command, "--repo", str(repo))
    data = payload(result)
    assert len(result.stdout.splitlines()) == 1
    assert "开始" in result.stderr and "检查结束，用时" in result.stderr
    assert "检查 5/5：事实文档与 evidence" in result.stderr
    assert "[事实文档] 已检查 0/" in result.stderr
    assert "[evidence：docs/system/interfaces/api.md] 已检查 1/1" in result.stderr
    log = next((repo / ".mdf/logs").glob(f"*-{command}"))
    assert (log / "stderr.log").read_text() == result.stderr
    assert json.loads((log / "stdout.log").read_text()) == data
    if command == "fact-audit":
        assert (
            f"scope=full，实现 {len(data['implementation_paths'])} 份，"
            f"文档 {len(data['document_paths'])} 份"
        ) in result.stderr


def test_uninitialized_doctor_reports_layout_progress(python_exe, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    result = mdf(python_exe, "doctor", "--repo", str(repo))
    assert payload(result)["initialized"] is False
    assert "检查 1/1：未初始化布局" in result.stderr
    assert "检查 5/5" not in result.stderr
    assert "doctor 3/3" in result.stderr


@pytest.mark.parametrize("command", ["validate", "fact-audit"])
def test_findings_still_fail_after_progress(command, python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    (repo / "src/service.py").write_text("# 已变更\n")
    result = mdf(python_exe, command, "--repo", str(repo), "--scope", "full")
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert "evidence.stale" in {item["code"] for item in data["findings"]}
    assert "检查结束" in result.stderr


def test_doctor_failure_keeps_error_json_last(python_exe, tmp_path, monkeypatch):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    load_core_module()
    from mdf_core.inspection import doctor
    from mdf_core.foundation.errors import MDFError

    def fail(*args, **kwargs):
        raise MDFError("检查无法继续", code="inspection_failed")

    monkeypatch.setattr(doctor, "validate_evidence", fail)
    result = mdf(python_exe, "doctor", "--repo", str(repo))
    assert result.returncode != 0
    assert not result.stdout
    assert "中断，用时" in result.stderr
    assert json.loads(result.stderr.splitlines()[-1])["error"] == "inspection_failed"


def test_doctor_progress_arrives_before_check_finishes(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    (repo / "src/blocked.py").write_text("# evidence\n")
    doc = repo / "docs/system/interfaces/api.md"
    doc.write_text(doc.read_text().replace(
        "  - path: src/service.py", "  - path: src/service.py\n  - path: src/blocked.py",
    ))
    init_git(repo)
    scripts = str(skill_dir("mdf") / "scripts")
    probe = f"""
import sys
sys.path.insert(0, {scripts!r})
from mdf_core.workspace.gitutil import GitPathIndex
from mdf_core.cli import main
original = GitPathIndex.last_commit
def wait_for_input(self, path):
    if path.name == "blocked.py":
        sys.stdin.readline()
    return original(self, path)
GitPathIndex.last_commit = wait_for_input
sys.exit(main(["doctor", "--repo", sys.argv[1]]))
"""
    proc = subprocess.Popen(
        [python_exe, "-c", probe, str(repo)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    received = b""
    marker = (
        "[evidence：docs/system/interfaces/api.md] 已检查 1/2，当前 src/blocked.py"
    ).encode()
    try:
        deadline = time.monotonic() + 10
        while marker not in received:
            remaining = deadline - time.monotonic()
            assert remaining > 0, received.decode()
            ready, _, _ = select.select([proc.stderr], [], [], remaining)
            assert ready, received.decode()
            chunk = os.read(proc.stderr.fileno(), 65536)
            assert chunk, received.decode()
            received += chunk
        assert proc.poll() is None
        assert not select.select([proc.stdout], [], [], 0)[0]
        stdout, stderr = proc.communicate(input=b"\n", timeout=10)
        assert proc.returncode == 0, (received + stderr).decode()
        assert json.loads(stdout)["operation"] == "doctor"
        assert "[evidence：docs/system/interfaces/api.md] 已检查 2/2" in stderr.decode()
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()
