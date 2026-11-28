"""review-prepare：统一的审查左端点、未审净增量与体积结论。"""
import pytest

from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from support_github_flow import error_of, github_flow_repo
from test_incremental_plan import started

load_core_module()
from mdf_core.workspace import clear_commits  # noqa: E402


def prepare(python_exe, work, *extra):
    return payload(mdf(python_exe, "review-prepare", "--repo", str(work), *extra))["result"]


def test_delivery_defaults_to_start_commit_and_reports_net_increment(python_exe, tmp_path):
    _, work, _ = started(python_exe, tmp_path)
    start = json.loads(next((work / "changes/unreleased").glob("*/delivery.json")).read_text())["start_commit"]
    (work / "src/service.py").write_text("def healthy():\n    return False\n")
    commit(work, "feat: 实现")
    result = prepare(python_exe, work)
    assert result["left"] == start and result["head"] == git(work, "rev-parse", "HEAD").stdout.strip()
    assert result["net_increment"] == ["src/service.py"] == result["paths"]
    assert result["numstat"] == [{"path": "src/service.py", "added": 2, "deleted": 2}]
    assert result["size"] == {"lines": 4, "files": 1, "per_reviewer": 1000, "reviewers": 1}
    assert result["skip_review"] is False
    assert len(result["rules_sha256"]) == 64 and result["force"] is False


def test_nothing_to_review_needs_no_reviewer(python_exe, tmp_path):
    _, work, _ = started(python_exe, tmp_path)
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    result = prepare(python_exe, work, "--against", head)
    assert result["net_increment"] == [] and result["size"]["reviewers"] == 0 and result["skip_review"] is True


@pytest.mark.parametrize("tracked", [False, True])
def test_large_increment_scales_reviewers_by_numstat_lines(python_exe, tmp_path, tracked):
    _, work, _ = started(python_exe, tmp_path)
    (work / "src/big.py").write_text("".join(f"v{i} = {i}\n" for i in range(2300)))
    if tracked:
        commit(work, "feat: 大文件")
    size = prepare(python_exe, work)["size"]
    assert size["lines"] == 2300 and size["reviewers"] == 3


def record_result(python_exe, work, *, against, head, extra=()):
    return payload(mdf(python_exe, "review-record", "--repo", str(work),
                       "--against", against, "--head", head, *extra))["result"]


def record(python_exe, work, plan, *, against=None):
    return record_result(python_exe, work, against=against or plan["left"], head=plan["head"])["recorded"]


def test_release_skips_after_feature_code_is_cherry_picked(python_exe, tmp_path):
    repo, feature, _ = started(python_exe, tmp_path)
    git(repo, "tag", "v1.2.0", "master")
    (feature / "src/service.py").write_text("VALUE = 2\n")
    commit(feature, "feat: 实现")
    reviewed = prepare(python_exe, feature)
    assert record(python_exe, feature, reviewed)

    git(repo, "checkout", "develop")
    git(repo, "commit", "--allow-empty", "-m", "docs: 更新 develop 历史")
    git(repo, "cherry-pick", reviewed["head"])
    git(repo, "checkout", "master")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "release",
                       "--version", "1.3.0", "--objectives-file", str(write_release_objectives(tmp_path))))
    release = Path(data["worktree"])
    reused = prepare(python_exe, release)
    assert reused["left"] == reused["clear_commit"] == reviewed["head"]
    assert git(release, "merge-base", "HEAD", reviewed["head"]).stdout.strip() != reviewed["head"]
    assert reused["skip_review"] and reused["net_increment"] == []
    assert prepare(python_exe, release, "--force")["net_increment"] == ["src/service.py"]

    (release / "src/service.py").write_text("VALUE = 3\n")
    commit(release, "fix: release 改动")
    changed = prepare(python_exe, release)
    assert not changed["skip_review"] and changed["net_increment"] == ["src/service.py"]


def test_dirty_loads_clear_and_includes_index_worktree_and_untracked(python_exe, tmp_path):
    _, work, _ = started(python_exe, tmp_path)
    first = prepare(python_exe, work)
    assert record(python_exe, work, first)
    path = work / "src/service.py"
    original = path.read_text()
    path.write_text("STAGED = 1\n")
    git(work, "add", "src/service.py")
    path.write_text(original)
    (work / "src/new.py").write_text("NEW = 1\n")
    dirty = prepare(python_exe, work)
    assert dirty["dirty"] and not dirty["skip_review"]
    assert dirty["left"] == dirty["clear_commit"] == first["head"]
    assert dirty["paths"] == ["src/new.py", "src/service.py"]
    assert not record(python_exe, work, dirty)
    assert clear_commits.load(work, "code_review") == first["head"]


def test_narrow_review_cannot_clear_head_and_changed_rules_cannot_skip(python_exe, tmp_path):
    _, work, _ = started(python_exe, tmp_path)
    first = prepare(python_exe, work)
    assert record(python_exe, work, first)
    (work / "src/service.py").write_text("VALUE = 3\n")
    commit(work, "feat: 实现")
    changed = prepare(python_exe, work)
    assert not record(python_exe, work, changed, against=changed["head"])
    assert record(python_exe, work, changed)
    (work / "AGENTS.md").write_text((work / "AGENTS.md").read_text() + "\nUse the new rules.\n")
    commit(work, "docs: 调整规则")
    assert not prepare(python_exe, work)["skip_review"]


def test_blocking_review_discards_matching_clear(python_exe, tmp_path):
    _, work, _ = started(python_exe, tmp_path)
    (work / "src/service.py").write_text("VALUE = 2\n")
    commit(work, "feat: 实现")
    reviewed = prepare(python_exe, work)
    assert record(python_exe, work, reviewed)
    payload(mdf(python_exe, "review-record", "--repo", str(work), "--against", reviewed["left"],
                "--head", reviewed["head"], "--failed"))
    assert clear_commits.load(work, "code_review") is None
    assert not prepare(python_exe, work)["skip_review"]


def test_requires_explicit_left_outside_delivery(python_exe, tmp_path):
    repo, _, _ = started(python_exe, tmp_path)
    git(repo, "checkout", "-q", "develop")
    assert error_of(mdf(python_exe, "review-prepare", "--repo", str(repo)))["error"] == "missing_review_base"


def test_schema_version_change_counts_as_rules_changed(python_exe, tmp_path):
    _, work, _ = started(python_exe, tmp_path)
    plan = prepare(python_exe, work)
    assert record(python_exe, work, plan)
    clear = plan["head"]
    manifest = work / ".mdf" / "manifest.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        "schema_version: 3", "schema_version: 2", 1,
    ), encoding="utf-8")
    commit(work, "chore: 降低契约声明")
    result = prepare(python_exe, work)
    assert result["rules_changed"] is True
    assert result["clear_commit"] == clear
    assert result["left"] != clear


def test_another_tool_revision_reuses_the_clear_commit(python_exe, tmp_path):
    import shutil
    import subprocess
    from conftest import skill_dir

    _, work, _ = started(python_exe, tmp_path)
    plan = prepare(python_exe, work)
    assert record(python_exe, work, plan)
    copy = tmp_path / "tool-b"
    shutil.copytree(skill_dir("mdf"), copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (copy / "references" / ".version").write_text("b" * 40 + "\n", encoding="utf-8")
    info = subprocess.run(
        [python_exe, "-B", str(copy / "scripts" / "mdf.py"), "info"],
        capture_output=True, text=True, check=False,
    )
    assert info.returncode == 0, info.stderr
    assert json.loads(info.stdout)["revision"] == "b" * 40
    reviewed = subprocess.run(
        [python_exe, "-B", str(copy / "scripts" / "mdf.py"), "review-prepare", "--repo", str(work)],
        capture_output=True, text=True, check=False,
    )
    assert reviewed.returncode == 0, reviewed.stderr
    result = json.loads(reviewed.stdout)["result"]
    assert result["rules_changed"] is False
    assert result["clear_commit"] == plan["head"]
    assert result["left"] == plan["head"]


def test_release_full_review_records_despite_overlapping_prior_clear_and_continues_incrementally(python_exe, tmp_path):
    repo, feature, _ = started(python_exe, tmp_path)
    git(repo, "tag", "v1.2.0", "master")
    base_a = git(repo, "rev-parse", "v1.2.0").stdout.strip()
    (feature / "src/service.py").write_text("VALUE = 2\n")
    commit(feature, "feat: 实现 B")
    clear_b = git(feature, "rev-parse", "HEAD").stdout.strip()
    assert record(python_exe, feature, prepare(python_exe, feature))
    assert clear_commits.load(repo, "code_review") == clear_b

    git(repo, "checkout", "develop")
    git(repo, "cherry-pick", clear_b)
    git(repo, "checkout", "master")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "release",
                       "--version", "1.3.0", "--objectives-file", str(write_release_objectives(tmp_path))))
    release = Path(data["worktree"])
    (release / "src/service.py").write_text("VALUE = 3\n")
    commit(release, "fix: release 改动 C")
    head_c = git(release, "rev-parse", "HEAD").stdout.strip()

    full_res = record_result(python_exe, release, against=base_a, head=head_c)
    assert full_res == {"recorded": True}
    assert clear_commits.load(release, "code_review") == head_c

    (release / "src/service.py").write_text("VALUE = 4\n")
    commit(release, "fix: release 增量 D")
    head_d = git(release, "rev-parse", "HEAD").stdout.strip()
    incr_plan = prepare(python_exe, release)
    assert incr_plan["left"] == head_c and incr_plan["head"] == head_d
    incr_res = record_result(python_exe, release, against=head_c, head=head_d)
    assert incr_res == {"recorded": True}
    assert clear_commits.load(release, "code_review") == head_d


def test_github_flow_main_release_full_review_records_and_continues_incrementally(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path, trunk="main", previous_release=True)
    base_a = git(repo, "rev-parse", "v1.2.0^{commit}").stdout.strip()
    feature = Path(payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                               "--proposal", PRP_ID, "--roster", "solo",
                               "--objectives-file", str(write_work_objectives(tmp_path))))["worktree"])
    (feature / "src/service.py").write_text("VALUE = 2\n")
    commit(feature, "feat: 实现 B")
    clear_b = git(feature, "rev-parse", "HEAD").stdout.strip()
    assert record(python_exe, feature, prepare(python_exe, feature))
    assert clear_commits.load(repo, "code_review") == clear_b

    git(repo, "checkout", "main")
    git(repo, "cherry-pick", clear_b)
    release = Path(payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "release",
                               "--version", "1.3.0",
                               "--objectives-file", str(write_release_objectives(tmp_path))))["worktree"])
    (release / "src/service.py").write_text("VALUE = 3\n")
    commit(release, "fix: release 改动 C")
    head_c = git(release, "rev-parse", "HEAD").stdout.strip()
    assert prepare(python_exe, release, "--force")["left"] == base_a

    full_res = record_result(python_exe, release, against=base_a, head=head_c)
    assert full_res == {"recorded": True}
    assert clear_commits.load(release, "code_review") == head_c

    (release / "src/service.py").write_text("VALUE = 4\n")
    commit(release, "fix: release 增量 D")
    head_d = git(release, "rev-parse", "HEAD").stdout.strip()
    incr_plan = prepare(python_exe, release)
    assert incr_plan["left"] == head_c and incr_plan["head"] == head_d
    incr_res = record_result(python_exe, release, against=head_c, head=head_d)
    assert incr_res == {"recorded": True}
    assert clear_commits.load(release, "code_review") == head_d


def test_review_record_rejects_invalid_against_and_rules_changed_with_reasons(python_exe, tmp_path):
    _, work, _ = started(python_exe, tmp_path)
    normal = json.loads(next((work / "changes/unreleased").glob("*/delivery.json")).read_text())["start_commit"]
    (work / "src/service.py").write_text("VALUE = 2\n")
    commit(work, "feat: 实现 B")
    clear_b = git(work, "rev-parse", "HEAD").stdout.strip()
    assert record(python_exe, work, prepare(python_exe, work))

    (work / "src/service.py").write_text("VALUE = 3\n")
    commit(work, "feat: 实现 C")
    commit_c = git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "src/service.py").write_text("VALUE = 4\n")
    commit(work, "feat: 实现 D")
    head_d = git(work, "rev-parse", "HEAD").stdout.strip()

    bad = record_result(python_exe, work, against=commit_c, head=head_d)
    assert bad == {"recorded": False, "reason": "invalid_against"}
    assert clear_commits.load(work, "code_review") == clear_b

    (work / "AGENTS.md").write_text((work / "AGENTS.md").read_text() + "\nNew review rule.\n")
    commit(work, "docs: 调整规则")
    head_e = git(work, "rev-parse", "HEAD").stdout.strip()
    stale_rules = record_result(python_exe, work, against=clear_b, head=head_e)
    assert stale_rules == {"recorded": False, "reason": "rules_changed"}
    assert clear_commits.load(work, "code_review") == clear_b

    full_after_rules = record_result(python_exe, work, against=normal, head=head_e)
    assert full_after_rules == {"recorded": True}
    assert clear_commits.load(work, "code_review") == head_e


def test_review_record_protects_dirty_head_mismatch_and_non_delivery_with_reasons(python_exe, tmp_path):
    repo, work, _ = started(python_exe, tmp_path)
    first = prepare(python_exe, work)
    assert record(python_exe, work, first)
    (work / "src/service.py").write_text("VALUE = 2\n")
    commit(work, "feat: 实现")
    head = git(work, "rev-parse", "HEAD").stdout.strip()

    mismatch = record_result(python_exe, work, against=first["head"], head=first["head"])
    assert mismatch == {"recorded": False, "reason": "head_mismatch"}

    (work / "src/service.py").write_text("DIRTY = 1\n")
    dirty = record_result(python_exe, work, against=first["head"], head=head)
    assert dirty == {"recorded": False, "reason": "dirty_worktree"}

    git(repo, "checkout", "-q", "develop")
    dev_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    non_delivery = record_result(python_exe, repo, against=dev_head, head=dev_head)
    assert non_delivery == {"recorded": False, "reason": "not_delivery"}


def test_review_record_reports_clear_changed_on_concurrent_update(python_exe, tmp_path, monkeypatch, capsys):
    import argparse
    from mdf_core.reviewing import prepare as review_prepare

    _, work, _ = started(python_exe, tmp_path)
    first = prepare(python_exe, work)
    assert record(python_exe, work, first)
    (work / "src/service.py").write_text("VALUE = 2\n")
    commit(work, "feat: 并发目标")
    other = git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "src/service.py").write_text("VALUE = 3\n")
    commit(work, "feat: 当前 HEAD")
    head = git(work, "rev-parse", "HEAD").stdout.strip()

    original_record = clear_commits.record

    def racing_record(repo, key, target_head, *, expected):
        state = clear_commits.state_file(repo)
        state.write_text(json.dumps({key: other}, indent=2) + "\n", encoding="utf-8")
        return original_record(repo, key, target_head, expected=expected)

    monkeypatch.setattr(clear_commits, "record", racing_record)
    review_prepare.command_review_record(argparse.Namespace(
        repo=str(work), against=first["head"], head=head, initial_base=None, failed=False,
    ))
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["result"] == {"recorded": False, "reason": "clear_changed"}
    assert clear_commits.load(work, "code_review") == other
