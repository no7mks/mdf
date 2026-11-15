"""review-prepare：统一的审查左端点、未审净增量与体积结论。"""
import pytest

from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from support_github_flow import error_of
from test_catch_up_plan import started

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


def record(python_exe, work, plan, *, against=None):
    return payload(mdf(python_exe, "review-record", "--repo", str(work),
                       "--against", against or plan["left"], "--head", plan["head"]))["result"]["recorded"]


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
