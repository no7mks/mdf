"""catch-up-plan：0/1/多次 merge 拓扑下独立输出 review/verify/fact 动作，且只读。"""
from mdf_test_support import *  # noqa: F403
from _support import run
from support_delivery import commit, local_repo

SPACED = "".join(f"line{i} = {i}\n" for i in range(1, 9))


def started(python_exe, tmp_path, seed=None):
    repo = local_repo(tmp_path)
    if seed:
        git(repo, "checkout", "-q", "develop")
        (repo / "src/shared.py").write_text(seed)
        commit(repo, "feat: 共享文件")
        git(repo, "checkout", "-q", "master")
        git(repo, "merge", "-q", "--ff-only", "develop")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature", "--proposal", PRP_ID,
                       "--roster", "solo", "--objectives-file", str(write_work_objectives(tmp_path))))
    work = Path(data["worktree"])
    return repo, work, work / "changes/unreleased/service-health"


def tick_fact(work, root):
    text = (root / "objectives.md").read_text()
    (root / "objectives.md").write_text(text.replace("- [ ] fact audit", "- [x] fact audit"))
    commit(work)
    return git(work, "rev-parse", "HEAD").stdout.strip()


def upstream(repo, name, content, message="feat: 上游改动"):
    git(repo, "checkout", "-q", "develop")
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    commit(repo, message)
    git(repo, "checkout", "-q", "master")


def plan(python_exe, work, *extra):
    return payload(mdf(python_exe, "catch-up-plan", "--repo", str(work), *extra))["result"]


def merge(work, *, resolve=None):
    result = run(["git", "merge", "--no-ff", "--no-edit", "develop"], cwd=work)
    if resolve:
        assert result.returncode != 0
        for name, content in resolve.items():
            (work / name).write_text(content)
        commit(work, "merge: 解决冲突")
    else:
        assert result.returncode == 0, result.stdout


def test_zero_merge_without_increment_skips_everything(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    base = tick_fact(work, root)
    result = plan(python_exe, work)
    assert result["base"] == base and result["merges"] == []
    assert [result[k]["action"] for k in ("review", "verify", "fact")] == ["skip", "skip", "skip"]


def test_zero_merge_rework_requires_focused_review_and_smart_verify(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    tick_fact(work, root)
    (work / "src/service.py").write_text("VALUE = 2\n")
    commit(work, "fix: 返工")
    result = plan(python_exe, work)
    assert result["review"]["action"] == "focused" and result["review"]["reasons"] == ["post_base_code"]
    assert result["verify"] == {**result["verify"], "action": "smart", "paths": ["src/service.py"],
                                "modules": ["default"], "depends_on_declared": False}
    assert result["fact"]["action"] == "audit" and result["fact"]["implementation"] == ["src/service.py"]


def test_clean_upstream_merge_on_disjoint_files_skips_review_but_not_verify(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    (work / "src/own.py").write_text("own = 1\n")
    commit(work, "feat: 本分支代码")
    tick_fact(work, root)
    upstream(repo, "src/other.py", "other = 1\n")
    merge(work)
    result = plan(python_exe, work)
    assert [m["kind"] for m in result["merges"]] == ["upstream"] and len(result["incoming_commits"]) == 1
    assert result["review"]["action"] == "skip" and result["review"]["reasons"] == []
    assert result["verify"]["action"] == "smart" and result["verify"]["paths"] == ["src/other.py"]
    assert result["fact"]["action"] == "audit"


def test_upstream_touching_branch_file_is_an_uncovered_interaction(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path, seed=SPACED)
    (work / "src/shared.py").write_text(SPACED.replace("line1 = 1", "line1 = 100"))
    commit(work, "feat: 本分支改共享文件头部")
    tick_fact(work, root)
    upstream(repo, "src/shared.py", SPACED + "line9 = 9\n")
    merge(work)
    result = plan(python_exe, work)
    assert result["review"]["action"] == "focused" and "interaction" in result["review"]["reasons"]
    assert result["review"]["paths"] == ["src/shared.py"]


def test_conflict_resolution_is_net_change_that_blocks_review_skip(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    (work / "src/conflict.py").write_text("value = 'branch'\n")
    commit(work, "feat: 分支版本")
    tick_fact(work, root)
    upstream(repo, "src/conflict.py", "value = 'upstream'\n")
    merge(work, resolve={"src/conflict.py": "value = 'both'\n"})
    result = plan(python_exe, work)
    assert result["merges"][0]["resolution_paths"] == ["src/conflict.py"]
    assert result["review"]["action"] == "focused" and "conflict_resolution" in result["review"]["reasons"]


def test_consecutive_merges_aggregate_all_incoming_commits(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    (work / "src/own.py").write_text("own = 1\n")
    commit(work, "feat: 本分支代码")
    tick_fact(work, root)
    upstream(repo, "src/one.py", "one = 1\n")
    merge(work)
    upstream(repo, "src/two.py", "two = 1\n")
    merge(work)
    result = plan(python_exe, work)
    assert len(result["merges"]) == 2 and len(result["incoming_commits"]) == 2
    assert result["verify"]["paths"] == ["src/one.py", "src/two.py"]
    assert result["review"]["action"] == "skip"


def test_upstream_rule_or_contract_change_blocks_review_skip(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    tick_fact(work, root)
    upstream(repo, "AGENTS.md", (repo / "AGENTS.md").read_text() + "\n新增约束\n")
    merge(work)
    result = plan(python_exe, work)
    assert result["review"]["action"] == "focused"
    assert result["review"]["reasons"] == ["rules_or_contract_changed"]


def test_docs_only_branch_does_not_need_verify_for_upstream_code(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    tick_fact(work, root)
    upstream(repo, "src/other.py", "other = 1\n")
    merge(work)
    result = plan(python_exe, work)
    assert result["verify"]["action"] == "skip" and result["review"]["action"] == "skip"
    assert result["fact"]["action"] == "audit"


def test_explicit_base_and_read_only(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    tick_fact(work, root)
    (work / "src/service.py").write_text("VALUE = 3\n")
    commit(work, "fix: 返工")
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    before = git(work, "status", "--porcelain").stdout, head
    assert plan(python_exe, work, "--base", head)["review"]["action"] == "skip"
    assert plan(python_exe, work, "--base", "HEAD~1")["review"]["action"] == "focused"
    assert (git(work, "status", "--porcelain").stdout, git(work, "rev-parse", "HEAD").stdout.strip()) == before
