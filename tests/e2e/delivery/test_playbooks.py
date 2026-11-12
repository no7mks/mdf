"""playbook：Agent 执行的测试手册；pending、--record 收录与校验。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def _register_named(repo: Path, name: str, frontmatter: str = "") -> None:
    modules = repo / ".mdf/modules.yaml"
    modules.write_text(
        modules.read_text(encoding="utf-8").replace("named: []", f"named:\n      - {name}"),
        encoding="utf-8",
    )
    doc = repo / f"docs/system/testing/{name}.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        f"---\ntitle: {name}\n{frontmatter}---\n\n# {name}\n\n目的：手册回归。\n\ntestcase 构成：playbook。\n",
        encoding="utf-8",
    )


def _write_playbook(repo: Path, rel: str, suites: str, steps=("S01", "S02")) -> None:
    path = repo / "tests/playbooks" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"## {step} 步骤\n\n- 操作：执行。\n- 判定：通过。\n\n" for step in steps)
    path.write_text(f"---\nsuites: {suites}\n---\n\n# {rel}\n\n{body}", encoding="utf-8")


def _write_junit(repo: Path, report_dir: str, suite: str, cases, name: str = "agent.xml") -> None:
    rows = []
    for classname, step, failed in cases:
        inner = '<failure message="判定未通过"/>' if failed else ""
        rows.append(f'<testcase classname="{classname}" name="{step}" time="1">{inner}</testcase>')
    (repo / report_dir / name).write_text(
        f'<testsuite name="{suite}">{"".join(rows)}</testsuite>', encoding="utf-8"
    )


def _named_pending(python_exe, tmp_path, frontmatter: str = ""):
    repo = copy_fixture(tmp_path)
    _register_named(repo, "smoke-env", frontmatter)
    _write_playbook(repo, "env/deploy.md", "[smoke-env]")
    init_git(repo)
    result = payload(mdf(python_exe, "verify", "smoke-env", "--repo", str(repo)))
    return repo, result


PLAYBOOK = "tests/playbooks/env/deploy.md"


def _record_named(python_exe, repo, report_dir):
    return mdf(
        python_exe, "verify", "--scope", "named", "--suites", "smoke-env",
        "--record", report_dir, "--repo", str(repo),
    )


def test_named_playbook_only_suite_pending_then_record(python_exe, tmp_path):
    repo, result = _named_pending(python_exe, tmp_path)
    assert result["operation"] == "verify-pending"
    assert result["result"]["all_passed"] is False
    pending = result["result"]["pending"][0]
    assert pending["playbooks"] == [PLAYBOOK]
    assert pending["report_dir"].startswith(".mdf/reports/")
    _write_junit(repo, pending["report_dir"], "smoke-env", [(PLAYBOOK, "S01", False), (PLAYBOOK, "S02", False)])
    recorded = payload(_record_named(python_exe, repo, pending["report_dir"]))
    assert recorded["operation"] == "verify-named-run"
    item = recorded["result"]["results"][0]
    assert item["id"] == f"playbook:{PLAYBOOK}" and item["passed"] is True
    assert (repo / pending["report_dir"] / "summary.json").is_file()


def test_named_commands_and_playbooks_keep_command_results(python_exe, tmp_path):
    repo, result = _named_pending(python_exe, tmp_path, f'command: "{SUITE_OK}"\n')
    assert [item["id"] for item in result["result"]["results"]] == ["smoke-env"]
    pending = result["result"]["pending"][0]
    _write_junit(repo, pending["report_dir"], "smoke-env", [(PLAYBOOK, "S01", False), (PLAYBOOK, "S02", True)])
    failed = _record_named(python_exe, repo, pending["report_dir"])
    assert "verify_command_failed" in failed.stderr
    details = json.loads(failed.stderr)["details"]
    assert [item["id"] for item in details["results"]] == ["smoke-env", f"playbook:{PLAYBOOK}"]
    assert details["results"][1]["error"] == "test_report_failed"


@pytest.mark.parametrize(
    "cases, code",
    [
        ([(PLAYBOOK, "S01", False)], "invalid_playbook_report"),
        ([(PLAYBOOK, "S01", False), (PLAYBOOK, "S02", False), (PLAYBOOK, "S03", False)], "invalid_playbook_report"),
        (None, "missing_test_report"),
    ],
)
def test_named_record_requires_exact_steps(python_exe, tmp_path, cases, code):
    repo, result = _named_pending(python_exe, tmp_path)
    report_dir = result["result"]["pending"][0]["report_dir"]
    if cases is not None:
        _write_junit(repo, report_dir, "smoke-env", cases)
    assert code in _record_named(python_exe, repo, report_dir).stderr


@pytest.mark.parametrize("staged", [False, True])
def test_named_record_rejects_tracked_changes(python_exe, tmp_path, staged):
    repo, result = _named_pending(python_exe, tmp_path)
    report_dir = result["result"]["pending"][0]["report_dir"]
    _write_junit(repo, report_dir, "smoke-env", [(PLAYBOOK, "S01", False), (PLAYBOOK, "S02", False)])
    (repo / PLAYBOOK).write_text((repo / PLAYBOOK).read_text() + "\nChanged assertion\n")
    if staged:
        git(repo, "add", PLAYBOOK)
    assert "tracked 文件已变化" in _record_named(python_exe, repo, report_dir).stderr


def test_named_pending_can_preserve_initial_dirty_state(python_exe, tmp_path):
    repo, _ = _named_pending(python_exe, tmp_path)
    (repo / PLAYBOOK).write_text((repo / PLAYBOOK).read_text() + "\nInitial edit\n")
    result = payload(mdf(python_exe, "verify", "smoke-env", "--repo", str(repo)))
    report_dir = result["result"]["pending"][0]["report_dir"]
    _write_junit(repo, report_dir, "smoke-env", [(PLAYBOOK, "S01", False), (PLAYBOOK, "S02", False)])
    assert payload(_record_named(python_exe, repo, report_dir))["result"]["all_passed"] is True


def test_record_rejects_foreign_dir_head_change_and_smart(python_exe, tmp_path):
    repo, result = _named_pending(python_exe, tmp_path)
    report_dir = result["result"]["pending"][0]["report_dir"]
    assert "invalid_playbook_report" in _record_named(python_exe, repo, "docs").stderr
    smart = mdf(python_exe, "verify", "smart", "--module", "default", "--record", report_dir, "--repo", str(repo))
    assert "invalid_verify_scope" in smart.stderr
    (repo / "src/extra.py").write_text("changed = True\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 改动后 HEAD 变化")
    _write_junit(repo, report_dir, "smoke-env", [(PLAYBOOK, "S01", False), (PLAYBOOK, "S02", False)])
    assert "HEAD 已变化" in _record_named(python_exe, repo, report_dir).stderr


@pytest.mark.parametrize(
    "suites, steps",
    [("[smoke]", ("S01",)), ("[unknown]", ("S01",)), ("[]", ("S01",)), ("[release]", ()), ("[release]", ("S01", "S01"))],
)
def test_validate_reports_invalid_playbook(python_exe, tmp_path, suites, steps):
    repo = copy_fixture(tmp_path)
    _write_playbook(repo, "bad.md", suites, steps)
    init_git(repo)
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "playbooks.invalid" in result.stdout


def test_validate_requires_command_or_playbook_for_named(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    _register_named(repo, "empty-suite")
    init_git(repo)
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "modules.named_doc_command" in result.stdout


def test_release_branch_pending_then_record_writes_evidence(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    _write_playbook(repo, "release/smoke-live.md", "[release]", ("S01",))
    rel = "tests/playbooks/release/smoke-live.md"
    replace(repo / "docs/bugs" / BUG_NAME, "status: open", "status: closed\nfixed_in: 1.3.0")
    init_git(repo)
    write_unreleased_change(repo, "service-health")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 准备发布变更")
    git(repo, "checkout", "-b", "release/1.3.0")
    evidence = repo / "changes/unreleased/1.3.0/verification-report.json"
    result = payload(mdf(python_exe, "verify", "branch", "--repo", str(repo)))
    assert result["operation"] == "verify-pending"
    pending = result["result"]["pending"]
    assert json.loads(evidence.read_text())["all_passed"] is False
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 提交 pending 证据")
    _write_junit(repo, pending["report_dir"], "release", [(rel, "S01", False)])
    assert "HEAD 已变化" in mdf(python_exe, "verify", "branch", "--record", pending["report_dir"], "--repo", str(repo)).stderr
    result = payload(mdf(python_exe, "verify", "branch", "--repo", str(repo)))
    pending = json.loads(evidence.read_text())["pending"]
    state = json.loads((repo / pending["report_dir"] / "pending.json").read_text())
    assert state["playbooks"] == [{"path": rel, "steps": ["S01"]}]
    _write_junit(repo, pending["report_dir"], "release", [(rel, "S01", False)])
    recorded = payload(mdf(python_exe, "verify", "branch", "--record", pending["report_dir"], "--repo", str(repo)))
    assert recorded["operation"] == "verify-branch-run"
    saved = json.loads(evidence.read_text())
    assert saved["all_passed"] is True and "pending" not in saved
    assert saved["results"][-1]["command"] == f"playbook:{rel}"
