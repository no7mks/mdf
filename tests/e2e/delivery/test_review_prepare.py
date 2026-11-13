"""review-prepare：统一的审查左端点、未审净增量、交互文件集与体积结论。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from support_github_flow import error_of
from test_catch_up_plan import SPACED, merge, started, upstream

load_core_module()
from mdf_core.reviewing import credentials  # noqa: E402


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
    assert result["skip_review"] is False and result["interaction"] == []
    assert len(result["rules_sha256"]) == 64 and result["force"] is False


def test_nothing_to_review_needs_no_reviewer(python_exe, tmp_path):
    _, work, _ = started(python_exe, tmp_path)
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    result = prepare(python_exe, work, "--against", head)
    assert result["net_increment"] == [] and result["size"]["reviewers"] == 0 and result["skip_review"] is True


def test_large_increment_scales_reviewers_by_numstat_lines(python_exe, tmp_path):
    _, work, _ = started(python_exe, tmp_path)
    (work / "src/big.py").write_text("".join(f"v{i} = {i}\n" for i in range(2300)))
    commit(work, "feat: 大文件")
    size = prepare(python_exe, work)["size"]
    assert size["lines"] == 2300 and size["reviewers"] == 3


def test_credential_covers_unchanged_content_until_forced(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    (work / "src/service.py").write_text("VALUE = 2\n")
    commit(work, "feat: 实现")
    first = prepare(python_exe, work)
    identity = credentials.code_identity(work, "HEAD", first["paths"], first["rules_sha256"], "", {})
    credentials.record_code_credential(work, {"source": "feature/service-health", "kind": "feature",
                                              "credential": identity}, 1)
    covered = prepare(python_exe, work)
    assert covered["net_increment"] == [] and list(covered["covered"]) == ["src/service.py"]
    assert covered["skip_review"] is True and covered["size"]["reviewers"] == 0
    forced = prepare(python_exe, work, "--force")
    assert forced["net_increment"] == ["src/service.py"] and forced["covered"] == {}
    (work / "src/service.py").write_text("VALUE = 3\n")
    commit(work, "fix: 修改后凭证失效")
    assert prepare(python_exe, work)["net_increment"] == ["src/service.py"]


def test_upstream_interaction_files_are_listed_and_block_skip(python_exe, tmp_path):
    repo, work, _ = started(python_exe, tmp_path, seed=SPACED)
    (work / "src/shared.py").write_text(SPACED.replace("line1 = 1", "line1 = 100"))
    commit(work, "feat: 本分支改共享文件")
    upstream(repo, "src/shared.py", SPACED + "line9 = 9\n")
    merge(work)
    result = prepare(python_exe, work)
    assert result["interaction"] == ["src/shared.py"] and result["skip_review"] is False


def test_requires_clean_worktree_and_explicit_left_outside_delivery(python_exe, tmp_path):
    repo, work, _ = started(python_exe, tmp_path)
    (work / "dirty.txt").write_text("x\n")
    assert error_of(mdf(python_exe, "review-prepare", "--repo", str(work)))["error"] == "dirty_worktree"
    git(repo, "checkout", "-q", "develop")
    assert error_of(mdf(python_exe, "review-prepare", "--repo", str(repo)))["error"] == "missing_review_base"
