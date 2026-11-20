"""incremental-integration-plan：0/1/多次 merge 拓扑下独立输出 review/verify/fact 动作，且只读。"""
from mdf_test_support import *  # noqa: F403
from _support import run
from support_delivery import commit, local_repo

SPACED = "".join(f"line{i} = {i}\n" for i in range(1, 9))


def lib_module(depends=""):
    return ("  lib:\n    sourceset:\n      - \"lib/**\"\n    ignore: []\n    lint: \"true\"\n    build: \"true\"\n"
            + "".join(f"    {s}:\n      command: \"true\"\n      tests:\n        - \"tests/**\"\n"
                      for s in ("quick", "smoke", "release"))
            + "    named: []\n" + (f"    depends_on: [{depends}]\n" if depends else ""))


def started(python_exe, tmp_path, seed=None, extra_module=""):
    repo = local_repo(tmp_path)
    if seed or extra_module:
        git(repo, "checkout", "-q", "develop")
        if seed:
            (repo / "src/shared.py").write_text(seed)
        if extra_module:
            path = repo / ".mdf/modules.yaml"
            path.write_text(path.read_text() + extra_module)
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
    return payload(mdf(python_exe, "incremental-integration-plan", "--repo", str(work), *extra))["result"]


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


def test_clean_upstream_merge_reviews_new_code_and_verifies_modules(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path, extra_module=lib_module())
    (work / "src/own.py").write_text("own = 1\n")
    commit(work, "feat: 本分支代码")
    tick_fact(work, root)
    upstream(repo, "lib/other.py", "other = 1\n")
    merge(work)
    result = plan(python_exe, work)
    assert [m["kind"] for m in result["merges"]] == ["upstream"] and len(result["incoming_commits"]) == 1
    assert result["review"]["action"] == "focused" and result["review"]["reasons"] == ["upstream_code"]
    assert result["verify"]["action"] == "smart" and result["verify"]["paths"] == ["lib/other.py"]
    assert result["verify"]["modules"] == ["default", "lib"]
    assert result["fact"]["action"] == "audit"


def test_same_module_on_disjoint_files_is_a_module_interface_interaction(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    (work / "src/own.py").write_text("own = 1\n")
    commit(work, "feat: 本分支代码")
    tick_fact(work, root)
    upstream(repo, "src/other.py", "other = 1\n")
    merge(work)
    result = plan(python_exe, work)
    assert result["review"]["action"] == "focused" and result["review"]["reasons"] == ["upstream_code", "module_interaction"]
    assert result["review"]["paths"] == ["src/other.py"]
    assert result["review"]["interaction"] == {"files": [], "modules": ["default"], "branch_paths": ["src/own.py"]}


def test_depends_on_between_modules_is_an_interaction_in_either_direction(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path, extra_module=lib_module("default"))
    (work / "src/own.py").write_text("own = 1\n")
    commit(work, "feat: 本分支代码")
    tick_fact(work, root)
    upstream(repo, "lib/other.py", "other = 1\n")
    merge(work)
    result = plan(python_exe, work)
    assert result["review"]["action"] == "focused" and result["review"]["reasons"] == ["upstream_code", "module_interaction"]
    assert result["review"]["interaction"]["modules"] == ["default", "lib"]
    assert result["verify"]["modules"] == ["lib"] and result["verify"]["depends_on_declared"] is True


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
    repo, work, root = started(python_exe, tmp_path, extra_module=lib_module())
    (work / "src/own.py").write_text("own = 1\n")
    commit(work, "feat: 本分支代码")
    tick_fact(work, root)
    upstream(repo, "lib/one.py", "one = 1\n")
    merge(work)
    upstream(repo, "lib/two.py", "two = 1\n")
    merge(work)
    result = plan(python_exe, work)
    assert len(result["merges"]) == 2 and len(result["incoming_commits"]) == 2
    assert result["verify"]["paths"] == ["lib/one.py", "lib/two.py"]
    assert result["review"]["action"] == "focused"


def test_upstream_rule_or_contract_change_blocks_review_skip(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    tick_fact(work, root)
    upstream(repo, "AGENTS.md", (repo / "AGENTS.md").read_text() + "\n新增约束\n")
    merge(work)
    result = plan(python_exe, work)
    assert result["review"]["action"] == "focused"
    assert result["review"]["reasons"] == ["rules_or_contract_changed"]


def test_docs_only_branch_still_verifies_new_target_code(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    tick_fact(work, root)
    upstream(repo, "src/other.py", "other = 1\n")
    merge(work)
    result = plan(python_exe, work)
    assert result["verify"]["action"] == "smart" and result["review"]["action"] == "focused"
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


def test_without_depends_on_verify_also_covers_modules_the_branch_touched(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path, extra_module=lib_module())
    (work / "src/own.py").write_text("own = 1\n")
    commit(work, "feat: 本分支代码")
    tick_fact(work, root)
    upstream(repo, "lib/other.py", "other = 1\n")
    merge(work)
    assert plan(python_exe, work, "--base", git(work, "rev-parse", "HEAD~2").stdout.strip())["verify"]["modules"] \
        == ["default", "lib"]


def test_upstream_lockfile_or_testing_doc_with_branch_code_triggers_smart_for_all_modules(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path, extra_module=lib_module())
    (work / "src/own.py").write_text("own = 1\n")
    commit(work, "feat: 本分支代码")
    tick_fact(work, root)
    upstream(repo, "uv.lock", "locked = 1\n")
    merge(work)
    result = plan(python_exe, work)
    assert result["verify"]["action"] == "smart" and result["verify"]["modules"] == ["default", "lib"]
    assert result["verify"]["paths"] == ["uv.lock"]


def test_upstream_lockfile_triggers_smart_verify(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    tick_fact(work, root)
    upstream(repo, "uv.lock", "locked = 1\n")
    merge(work)
    result = plan(python_exe, work)
    assert result["verify"]["action"] == "smart"
    assert result["verify"]["modules"] == ["default"]


def test_material_only_conflict_does_not_block_review_skip(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path, extra_module=lib_module())
    (work / "src/own.py").write_text("own = 1\n")
    commit(work, "feat: 本分支代码")
    tick_fact(work, root)
    (work / "docs/notes.md").parent.mkdir(parents=True, exist_ok=True)
    (work / "docs/notes.md").write_text("branch\n")
    commit(work, "docs: 分支笔记")
    base = git(work, "rev-parse", "HEAD").stdout.strip()
    upstream(repo, "docs/notes.md", "upstream\n")
    merge(work, resolve={"docs/notes.md": "both\n"})
    result = plan(python_exe, work, "--base", base)
    assert result["merges"][0]["resolution_paths"] == ["docs/notes.md"]
    assert result["review"]["action"] == "skip" and result["fact"]["action"] == "skip"


def test_octopus_merge_is_unknown_and_keeps_verify_and_fact_conservative(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path, extra_module=lib_module())
    tick_fact(work, root)
    git(repo, "checkout", "-q", "-b", "side", "develop")
    (repo / "lib/x.py").parent.mkdir(exist_ok=True)
    (repo / "lib/x.py").write_text("x = 1\n")
    commit(repo, "feat: 侧支")
    git(repo, "checkout", "-q", "develop")
    upstream(repo, "lib/y.py", "y = 1\n")
    git(repo, "checkout", "-q", "master")
    assert run(["git", "merge", "--no-edit", "develop", "side"], cwd=work).returncode == 0
    result = plan(python_exe, work)
    assert result["merges"][0]["resolution_known"] is False
    assert result["review"]["action"] == "focused" and result["review"]["unknown_merges"]
    assert result["verify"]["action"] == "smart" and "lib/x.py" in result["verify"]["paths"]
    assert result["fact"]["action"] == "audit"


def test_unowned_root_script_is_not_skipped(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    tick_fact(work, root)
    (work / "tool.py").write_text("print(1)\n")
    commit(work, "feat: 根脚本")
    result = plan(python_exe, work)
    assert [result[key]["action"] for key in ("review", "verify", "fact")] != ["skip", "skip", "skip"]
    assert "tool.py" in result["review"]["paths"]
    assert "tool.py" in result["verify"]["paths"]
    assert "tool.py" in result["fact"]["implementation"]


def test_branch_agents_change_is_not_skipped(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    tick_fact(work, root)
    (work / "AGENTS.md").write_text((work / "AGENTS.md").read_text() + "\n补充约束。\n")
    commit(work, "docs: 本分支契约")
    result = plan(python_exe, work)
    assert result["review"]["action"] != "skip"
    assert result["verify"]["action"] != "skip"
    assert result["fact"]["action"] != "skip"
    assert result["fact"]["rules_changed"] == ["AGENTS.md"]


def test_upstream_manifest_change_alone_requires_fact_audit(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    tick_fact(work, root)
    upstream(repo, "AGENTS.md", (repo / "AGENTS.md").read_text() + "\n新增约束\n")
    merge(work)
    fact = plan(python_exe, work)["fact"]
    assert fact["action"] == "audit" and fact["rules_changed"] == ["AGENTS.md"]


def test_feature_plan_ignores_mutable_target_field(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    base = tick_fact(work, root)
    git(repo, "checkout", "-b", "feature/other", "develop")
    (repo / "src/other.py").write_text("other = True\n")
    commit(repo)
    incoming = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(work, "merge", "--no-ff", "--no-edit", "feature/other")
    expected = plan(python_exe, work, "--base", base)
    path = root / "delivery.json"
    data = json.loads(path.read_text())
    data["target"] = "feature/other"
    path.write_text(json.dumps(data))
    actual = plan(python_exe, work, "--base", base)
    assert actual == expected
    assert [m["kind"] for m in actual["merges"]] == ["internal"]
    assert incoming in actual["own_commits"] and incoming not in actual["incoming_commits"]
