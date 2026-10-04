"""阶段 Gate 可选；交接与合流依据设计和已提交产出。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def without_gates(python_exe, tmp_path):
    owner, root, _ = setup_delivery(python_exe, tmp_path)
    shutil.rmtree(root / "gates")
    path = root / "objectives.md"
    path.write_text(path.read_text() + (
        "\n- [x] design\n\n设计已确认。\n\n"
        "- [ ] write-tests\n\n测试负责验收。\n\n"
        "- [ ] implement\n\n实现负责交付。\n"
    ))
    commit(owner)
    design = git(owner, "rev-parse", "HEAD").stdout.strip()
    qa, dev = sync_roles(python_exe, owner)
    return owner, root, qa, dev, design


def test_handoff_and_join_accept_checked_objectives_without_stage_gates(python_exe, tmp_path):
    owner, root, qa, dev, design = without_gates(python_exe, tmp_path)
    for role, path, stage in (("qa", qa, "write-tests"), ("dev", dev, "implement")):
        obj = path / "changes/unreleased/service-health/objectives.md"
        obj.write_text(obj.read_text().replace(f"[ ] {stage}", f"[x] {stage}"))
        if role == "qa":
            (path / "tests/test_added.py").write_text("def test_added():\n    assert True\n")
        else:
            (path / "src/service.py").write_text("value = 1\n")
        commit(path)
        result = payload(mdf(python_exe, "worktree-check", "--repo", str(path),
                             "--owner", str(owner), "--role", role,
                             "--design-commit", design, "--handoff"))
        assert result["result"]["head"] == git(path, "rev-parse", "HEAD").stdout.strip()
    payload(mdf(python_exe, "delivery", "roster-join", "--repo", str(owner)))
    assert not qa.exists() and not dev.exists()
    assert (owner / "src/service.py").read_text() == "value = 1\n"
    assert (owner / "tests/test_added.py").is_file()
    assert "[x] write-tests" in (root / "objectives.md").read_text()
    assert "[x] implement" in (root / "objectives.md").read_text()
    assert not (root / "gates/design.json").exists()
    assert not (root / "gates/write-tests.json").exists()
    assert not (root / "gates/implement.json").exists()


def test_changed_design_without_snapshot_is_rejected(python_exe, tmp_path):
    owner, root, qa, dev, design = without_gates(python_exe, tmp_path)
    path = qa / "changes/unreleased/service-health/design.md"
    path.write_text(path.read_text() + "\n未确认的新接口。\n")
    commit(qa)
    failed = mdf(python_exe, "worktree-check", "--repo", str(qa), "--owner", str(owner),
                 "--role", "qa", "--design-commit", design, "--handoff")
    assert failed.returncode != 0 and "stale_gate" in failed.stderr
    assert qa.exists() and dev.exists()


def test_invalid_policy_without_snapshot_is_rejected(python_exe, tmp_path):
    owner, root, qa, dev, design = without_gates(python_exe, tmp_path)
    path = qa / "changes/unreleased/service-health/design-policy.json"
    path.write_text('{"protected_paths": ["tests/"]}\n')
    commit(qa)
    failed = mdf(python_exe, "worktree-check", "--repo", str(qa), "--owner", str(owner),
                 "--role", "qa", "--design-commit", design, "--handoff")
    assert failed.returncode != 0 and "invalid_policy" in failed.stderr


def test_shared_design_changes_still_require_new_fixed_baseline(python_exe, tmp_path):
    owner, root, qa, _, design = without_gates(python_exe, tmp_path)
    path = root / "design.md"
    path.write_text(path.read_text() + "\n共同修改的新接口。\n")
    commit(owner)
    git(qa, "merge", "--no-ff", "--no-edit", "-m", "test: 合入设计修订",
        "feature/service-health")
    failed = mdf(python_exe, "worktree-check", "--repo", str(qa), "--owner", str(owner),
                 "--role", "qa", "--design-commit", design, "--handoff")
    assert failed.returncode != 0 and "stale_gate" in failed.stderr
    revised = git(owner, "rev-parse", "HEAD").stdout.strip()
    payload(mdf(python_exe, "worktree-check", "--repo", str(qa), "--owner", str(owner),
                "--role", "qa", "--design-commit", revised, "--handoff"))


def test_invalid_optional_snapshot_does_not_block_handoff_or_join(python_exe, tmp_path):
    owner, root, qa, dev, design = without_gates(python_exe, tmp_path)
    (root / "gates").mkdir()
    (root / "gates/design.json").write_text("损坏的辅助快照\n")
    commit(owner)
    for role, path in (("qa", qa), ("dev", dev)):
        payload(mdf(python_exe, "worktree-check", "--repo", str(path),
                    "--owner", str(owner), "--role", role,
                    "--design-commit", design, "--handoff"))
    payload(mdf(python_exe, "delivery", "roster-join", "--repo", str(owner)))
    assert not qa.exists() and not dev.exists()
