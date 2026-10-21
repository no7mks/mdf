"""info、doctor 与 validate 报告的仓库状态。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_info_reports_protocol_versions(python_exe: str):
    result = run(
        [python_exe, str(skill_dir("mdf") / "scripts" / "mdf.py"), "info"]
    )
    data = payload(result)
    assert data["ok"] is True
    assert data["tool"] == "mdf"
    assert data["protocol_version"] == 3
    assert data["tool_version"] == 3
    assert data["schema_version"] == 3


def test_doctor_reports_only_core_and_repository_state(
    python_exe: str, tmp_path: Path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["initialized"] is False
    assert {item["code"] for item in data["findings"]} == {"layout.testing"}
    assert data["normal_workflows_allowed"] is False
    assert "entry_skills" not in data


def test_doctor_reports_retired_layout_without_manifest(python_exe: str, tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "docs/product").mkdir(parents=True)
    (repo / "docs/product/note.md").write_text("旧产品说明。\n", encoding="utf-8")

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["initialized"] is False
    codes = {item["code"] for item in data["findings"]}
    assert "layout.migrate" in codes
    assert data["is_git_root"] is False


def test_doctor_reports_ready_v2_repository(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["initialized"] is True
    assert data["state"] == "ready"
    assert data["normal_workflows_allowed"] is True
    assert data["clean"] is True
    assert "entry_skills" not in data


def test_doctor_reports_dirty_without_blocking_normal_workflows(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["clean"] is False
    assert data["normal_workflows_allowed"] is True
    assert data["findings"] == []
    assert (repo / "untracked.txt").read_text() == "dirty\n"


@pytest.mark.parametrize("change_state", ["dirty", "staged", "committed"])
def test_doctor_allows_stale_evidence_but_full_checks_reject_it(
    python_exe: str, tmp_path: Path, change_state: str,
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    service = repo / "src/service.py"
    service.write_text(service.read_text() + "\n# 新的 evidence\n")
    if change_state != "dirty":
        git(repo, "add", "src/service.py")
    if change_state == "committed":
        git(repo, "commit", "-m", "test: 更新 evidence")

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert {item["code"] for item in data["findings"]} == {"evidence.stale"}
    assert all(item["severity"] == "error" for item in data["findings"])
    assert data["normal_workflows_allowed"] is True
    assert data["clean"] is (change_state == "committed")
    for command in ("validate", "fact-audit"):
        result = mdf(python_exe, command, "--repo", str(repo), "--scope", "full")
        assert result.returncode == 2
        checked = json.loads(result.stdout)
        assert checked["ok"] is False
        assert "evidence.stale" in {item["code"] for item in checked["findings"]}


@pytest.mark.parametrize("changed_path", ["schema.yaml", "generate.py"])
@pytest.mark.parametrize("committed", [False, True])
def test_doctor_allows_stale_generated_facts_but_full_checks_reject_them(
    python_exe: str, tmp_path: Path, changed_path: str, committed: bool,
):
    repo = copy_fixture(tmp_path)
    (repo / "schema.yaml").write_text("value: initial\n")
    generator = repo / "generate.py"
    generator.write_text("#!/usr/bin/env python3\n")
    generator.chmod(0o755)
    replace(
        repo / "docs/system/interfaces/api.md",
        "evidence:\n  - path: src/service.py\n",
        "evidence:\n  - path: src/service.py\n"
        "generated:\n  source: schema.yaml\n  generator: generate.py\n",
    )
    init_git(repo)
    assert payload(mdf(python_exe, "doctor", "--repo", str(repo)))["findings"] == []
    changed = repo / changed_path
    changed.write_text(changed.read_text() + "\n# 更新 generated 输入\n")
    if committed:
        git(repo, "add", changed_path)
        git(repo, "commit", "-m", "test: 更新 generated 输入")

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert {item["code"] for item in data["findings"]} == {"generated.stale"}
    assert all(item["severity"] == "error" for item in data["findings"])
    assert data["normal_workflows_allowed"] is True
    assert data["clean"] is committed
    for command in ("validate", "fact-audit"):
        result = mdf(python_exe, command, "--repo", str(repo), "--scope", "full")
        assert result.returncode == 2
        checked = json.loads(result.stdout)
        assert checked["ok"] is False
        assert "generated.stale" in {item["code"] for item in checked["findings"]}


@pytest.mark.parametrize("other_error", [
    "evidence.missing_path", "evidence.untracked", "evidence.outside_repo",
    "manifest.schema", "layout.migrate", "manifest.initializing",
])
def test_doctor_still_blocks_other_findings_alongside_stale_evidence(
    python_exe: str, tmp_path: Path, other_error: str,
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    service = repo / "src/service.py"
    service.write_text(service.read_text() + "\n# 新的 evidence\n")
    if other_error.startswith("evidence."):
        extra = "src/extra.py"
        if other_error == "evidence.untracked":
            (repo / extra).write_text("# 未跟踪的 evidence\n")
        elif other_error == "evidence.outside_repo":
            extra = str(tmp_path / "outside.py")
            Path(extra).write_text("# 仓库外的 evidence\n")
        replace(
            repo / "docs/system/data/model.md",
            "  - path: src/service.py\n",
            f"  - path: src/service.py\n  - path: {extra}\n",
        )
    elif other_error == "manifest.schema":
        replace(repo / ".mdf/manifest.yaml", "schema_version: 3", "schema_version: 2")
    elif other_error == "manifest.initializing":
        replace(repo / ".mdf/manifest.yaml", "state: ready", "state: initializing")
    else:
        (repo / "docs/product").mkdir()
        (repo / "docs/product/note.md").write_text("# 错误布局\n")

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    codes = {item["code"] for item in data["findings"]}
    assert {"evidence.stale", other_error} <= codes
    assert data["normal_workflows_allowed"] is False


def test_doctor_allows_in_progress_unreleased_delivery_without_change(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "-m", "master")
    git(repo, "branch", "develop")
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n- needs_design: yes\n\n交付健康接口。\n")
    started = payload(
        mdf(
            python_exe,
            "start",
            "--repo",
            str(repo),
            "--kind",
            "feature",
            "--proposal",
            "prp-0001",
            "--objectives-file",
            str(obj),
        )
    )
    work = Path(started["worktree"])
    root = work / "changes/unreleased/service-health"
    assert (root / "delivery.json").is_file()
    assert (root / "objectives.md").is_file()
    assert not (root / "CHANGE.md").exists()

    data = payload(mdf(python_exe, "doctor", "--repo", str(work)))
    assert data["state"] == "ready"
    assert data["findings"] == []
    assert data["normal_workflows_allowed"] is True
    assert data["clean"] is True


def test_doctor_rejects_unreleased_dir_without_change_or_identity(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    folder = repo / "changes/unreleased/orphan-slug"
    folder.mkdir(parents=True)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["normal_workflows_allowed"] is False
    codes = {item["code"] for item in data["findings"]}
    assert "change.missing" in codes


def test_doctor_allows_semver_unreleased_review_dir(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    folder = repo / "changes/unreleased/1.2.1"
    folder.mkdir(parents=True)
    (folder / "code-review.md").write_text("# 审查\n\n通过。\n", encoding="utf-8")
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["findings"] == []
    assert data["normal_workflows_allowed"] is True


def test_doctor_allows_semver_unreleased_identity_without_review(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    folder = repo / "changes/unreleased/1.3.0"
    folder.mkdir(parents=True)
    (folder / "delivery.json").write_text("{}\n", encoding="utf-8")
    (folder / "objectives.md").write_text("# 发布目标\n\n本版收口。\n")
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["findings"] == []
    assert data["normal_workflows_allowed"] is True


def test_doctor_rejects_empty_semver_unreleased_dir(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    folder = repo / "changes/unreleased/1.3.0"
    folder.mkdir(parents=True)
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["normal_workflows_allowed"] is False
    codes = {item["code"] for item in data["findings"]}
    assert "change.missing" in codes


def test_doctor_allows_ignored_runtime_files(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    (repo / ".gitignore").write_text(".lark/\n", encoding="utf-8")
    init_git(repo)
    token_dir = repo / ".lark"
    token_dir.mkdir()
    (token_dir / "token.json").write_text("{}\n", encoding="utf-8")

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["clean"] is True


def test_validate_rejects_noncurrent_manifest_schema(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / ".mdf" / "manifest.yaml",
        "schema_version: 3",
        "schema_version: 2",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert result.returncode != 0
    assert "manifest.schema" in result.stdout
