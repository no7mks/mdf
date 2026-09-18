"""复盘发现的跨流程衔接与失败恢复回归。"""
from types import SimpleNamespace

from mdf_test_support import *  # noqa: F403
from test_mdf_delivery import setup_delivery, sync_roles, record, commit
from test_mdf_upgrade import init_target, init_upstream, source_head
from test_mdf_gitflow_delivery import start_repo


def test_batch_prp_ids_do_not_write_or_repeat(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    git(repo, "checkout", "develop")
    work = planning_worktree(python_exe, repo)
    head = source_head(work)
    data = payload(mdf(python_exe, "make-id", "--type", "proposal", "--repo", str(work),
                       "--slug", "part-one", "--slug", "part-two"))
    assert [item["id"] for item in data["items"]] == ["prp-002", "prp-003"]
    assert data["items"][1]["filename"] == "prp-003-part-two.md"
    assert source_head(work) == head
    assert not git(work, "status", "--porcelain").stdout
    body = (work / "docs/proposals" / PRP_NAME).read_text().split("---", 2)[2]
    spec = {"source": "prp-001", "children": [
        {"id": item["id"], "filename": item["filename"], "depends_on": [], "body": body}
        for item in data["items"]], "downstream": {}, "rationale": "用户确认分成两项"}
    path = tmp_path / "split.json"
    path.write_text(json.dumps(spec))
    args = ["prp-split", "--repo", str(work), "--spec-file", str(path)]
    preview = payload(mdf(python_exe, *args, "--dry-run"))
    applied = payload(mdf(python_exe, *args))
    assert preview["files"] == applied["files"]


def test_upgrade_rejects_source_movement_before_writing(python_exe, tmp_path):
    upstream = init_upstream(tmp_path, "reviewed")
    repo = init_target(tmp_path)
    preview = payload(mdf(python_exe, "upgrade", "--repo", str(repo), "--source", str(upstream), "--dry-run"))
    head = source_head(repo)
    (upstream / "skills/mdf/SKILL.md").write_text("not reviewed\n")
    commit(upstream)
    result = mdf(python_exe, "upgrade", "--repo", str(repo), "--source", str(upstream),
                 "--expected-commit", preview["new_commit"])
    assert "upgrade_source_changed" in result.stderr
    assert source_head(repo) == head
    assert (repo / ".codex/skills/mdf/SKILL.md").read_text() == "old-codex\n"
    missing = mdf(python_exe, "upgrade", "--repo", str(repo), "--source", str(upstream))
    assert "missing_expected_commit" in missing.stderr


def test_worktree_check_rejects_wrong_role_and_stale_handoff(python_exe, tmp_path):
    owner, _, _ = setup_delivery(python_exe, tmp_path)
    qa, _ = sync_roles(python_exe, owner)
    design = source_head(owner)
    args = ["worktree-check", "--owner", str(owner), "--role", "qa", "--design-commit", design]
    assert "wrong_worktree" in mdf(python_exe, *args, "--repo", str(owner)).stderr
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    result = payload(mdf(python_exe, *args, "--repo", str(qa), "--handoff"))["result"]
    assert result["path"] == str(qa)
    (qa / "tests").mkdir(exist_ok=True)
    (qa / "tests/late.py").write_text("assert True\n")
    commit(qa)
    assert "stale_gate" in mdf(python_exe, *args, "--repo", str(qa), "--handoff").stderr


def test_non_feature_verification_binds_inputs_and_records_failure(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "bugfix", "--bug", "bug-CD34"))
    work = Path(created["worktree"])
    args = ["--repo", str(work)]
    payload(mdf(python_exe, "project-verify", "run", *args))
    payload(mdf(python_exe, "project-verify", "check", *args))
    evidence = work / "changes/unreleased/bug-cd34/code-review.verification.json"
    assert evidence.is_file()
    assert not list((work / "docs/context/research").glob("code-review*"))
    (work / "src/service.py").write_text("changed = True\n")
    assert "stale_verification" in mdf(python_exe, "project-verify", "check", *args).stderr
    manifest = work / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace('command: "true"', 'command: "false"'))
    assert "verify_command_failed" in mdf(python_exe, "project-verify", "run", *args).stderr
    assert "stale_verification" in mdf(python_exe, "project-verify", "check", *args).stderr


def test_integration_resumes_after_first_role_was_removed(python_exe, tmp_path, monkeypatch):
    owner, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, owner)
    for path, stage in ((qa, "write-tests"), (dev, "implement")):
        payload(record(python_exe, path, stage))
        commit(path)
    load_core_module()
    from mdf_core import delivery_git
    from mdf_core.delivery_state import locate
    from mdf_core.errors import MDFError
    original = delivery_git.git

    def fail_cleanup(repo, *args, **kwargs):
        if args[:2] == ("worktree", "remove") and args[2] == str(dev):
            raise MDFError("模拟第二路清理失败", code="test_interruption")
        return original(repo, *args, **kwargs)

    _, data = locate(owner)
    with monkeypatch.context() as patch:
        patch.setattr(delivery_git, "git", fail_cleanup)
        with pytest.raises(MDFError):
            delivery_git.integrate(owner, root, data, None)
    assert not qa.exists() and dev.exists()
    merged_head = source_head(owner)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(owner)))
    assert source_head(owner) == merged_head
    assert not dev.exists()
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(owner)))
    assert source_head(owner) == merged_head


@pytest.mark.parametrize("after_push", [False, True])
def test_publish_resumes_without_remerging_or_retagging(python_exe, tmp_path, monkeypatch, after_push):
    repo, remote = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "hotfix", "--version", "1.2.1"))
    work = Path(created["worktree"])
    (work / "src/service.py").write_text("fixed = True\n")
    commit(work)
    load_core_module()
    from mdf_core import gitflow
    from mdf_core.errors import MDFError
    original = gitflow._git

    def fail_push(repo, *args, **kwargs):
        if args and args[0] == "push":
            if after_push:
                original(repo, *args, **kwargs)
            raise MDFError("模拟推送结果丢失" if after_push else "模拟网络中断", code="test_interruption")
        return original(repo, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(gitflow, "_git", fail_push)
        with pytest.raises(MDFError):
            gitflow.command_finish_gitflow(SimpleNamespace(repo=str(work), source=None))
    before = {ref: git(repo, "rev-parse", ref).stdout for ref in ("master", "develop", "v1.2.1")}
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert done["pushed"] is True
    assert not work.exists()
    for ref, head in before.items():
        assert git(repo, "rev-parse", ref).stdout == head
    assert git(remote, "rev-parse", "master").stdout == before["master"]
    # 清理后仍可从主 worktree 核验同一次成功操作，不重复创建提交/tag。
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", "hotfix/1.2.1"))
    assert git(repo, "rev-parse", "v1.2.1").stdout == before["v1.2.1"]


@pytest.mark.parametrize("push_develop", [False, True])
def test_publish_recovers_unrecorded_develop_merge(python_exe, tmp_path, monkeypatch, push_develop):
    repo, remote = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "hotfix", "--version", "1.2.1"))
    work = Path(created["worktree"])
    (work / "src/service.py").write_text("fixed = True\n")
    commit(work)
    load_core_module()
    from mdf_core import gitflow, publish
    from mdf_core.errors import MDFError
    original = publish.write_json

    def fail_record(path, state):
        if "develop" in state["merged"]:
            raise MDFError("模拟合并记录写入中断", code="test_interruption")
        original(path, state)

    with monkeypatch.context() as patch:
        patch.setattr(publish, "write_json", fail_record)
        with pytest.raises(MDFError, match="模拟合并记录写入中断"):
            gitflow.command_finish_gitflow(SimpleNamespace(repo=str(work), source=None))
    path = publish.state_path(work, "hotfix/1.2.1")
    before = json.loads(path.read_text())["before"]["develop"]
    merged = git(repo, "rev-parse", "develop").stdout.strip()
    if push_develop:
        git(repo, "push", "origin", "develop")
    assert payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))["pushed"] is True
    assert git(repo, "rev-parse", "develop").stdout.strip() == merged
    assert git(remote, "rev-parse", "develop").stdout.strip() == merged
    assert json.loads(path.read_text())["before"]["develop"] == before


@pytest.mark.parametrize("kind", ["release", "hotfix"])
@pytest.mark.parametrize("advance,pushed", [("develop", True), ("develop", False), ("master", True)])
def test_publish_resume_after_dirty_worktree_and_branch_advance(python_exe, tmp_path, kind, advance, pushed):
    repo, remote = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", kind, "--version", "1.2.1"))
    work = Path(created["worktree"])
    (work / "src/service.py").write_text("fixed = True\n")
    commit(work)
    load_core_module()
    from mdf_core.publish import state_path
    path = state_path(work, f"{kind}/1.2.1")
    dirty = repo / "dirty.txt"
    dirty.write_text("未提交\n")
    assert "dirty_worktree" in mdf(python_exe, "finish-gitflow", "--repo", str(work)).stderr
    state = json.loads(path.read_text())
    assert state["merged"] == {}
    dirty.unlink()
    git(repo, "checkout", advance)
    (repo / "development.txt").write_text("后续开发\n")
    commit(repo)
    advanced = source_head(repo)
    if pushed:
        git(repo, "push", "origin", advance)
    result = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    if advance == "master" or not pushed:
        assert "publish_state_changed" in result.stderr
        assert json.loads(path.read_text())["before"][advance] == state["before"][advance]
        assert git(remote, "rev-parse", advance).stdout.strip() == (
            advanced if pushed else state["before"][advance])
        return
    assert payload(result)["pushed"] is True
    state = json.loads(path.read_text())
    assert state["before"]["develop"] == advanced
    assert git(repo, "show", "-s", "--format=%P", "develop").stdout.split() == [
        advanced, state["merged"]["master"]]
    assert state["pushed"] is True
    for ref in ("master", "develop", "refs/tags/v1.2.1"):
        assert git(remote, "rev-parse", ref).stdout == git(repo, "rev-parse", ref).stdout
    assert not work.exists()


def test_codewiki_runtime_checks_existing_environment_without_installing(tmp_path, monkeypatch):
    load_core_module()
    from mdf_core import codewiki_runtime
    root = tmp_path / "codewiki"
    (root / "codewiki").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    python = root / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("stub")
    commands = []

    def fake_run(args, cwd):
        commands.append(args)
        return str(root) if "--show-toplevel" in args else ""

    monkeypatch.setattr(codewiki_runtime, "run", fake_run)
    result = codewiki_runtime.prepare(root)
    assert result["python"] == str(python)
    assert commands[-1] == [str(python), "-c", "from codewiki.mcp.server import server"]
    assert not any("install" in args or "clone" in args for args in commands)


def test_review_resume_routes_to_repair_without_replacing_initial_head():
    from conftest import skill_dir
    text = (skill_dir("mdf") / "references/code-review.md").read_text()
    assert "修复续办 3；否则 2" in text
    assert "三份报告有效且修复续办" in text
    assert "保留原 review_head，不覆盖原报告" in text
    assert "首轮未齐时进入 2 补齐" in text
    assert "增量新一轮" in text
    assert "git diff <previous_final_head> <review_head>" in text
    assert "仍解决 / 复开 / 不适用" in text
    assert "changes/unreleased/<slug>/code-review.md" in text


def test_layered_bugfix_requires_existing_suite(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
                          "--bug", "bug-CD34"))
    work = Path(created["worktree"])
    item = '    - id: check\n      kind: custom\n      command: "true"'
    layered = (
        item + "\n      collections: [quick, full]\n"
        "    - id: slow\n      kind: e2e\n      command: \"true\"\n"
        "      collections: [full, billing]"
    )
    (work / ".mdf/manifest.yaml").write_text(
        (work / ".mdf/manifest.yaml").read_text().replace(item, layered, 1)
    )
    args = ["--repo", str(work)]
    missing = mdf(python_exe, "project-verify", "run", *args)
    assert "missing_delivery_suite" in missing.stderr
    suites = work / "changes/unreleased/bug-cd34/suites.json"
    suites.parent.mkdir(parents=True, exist_ok=True)
    suites.write_text(json.dumps({"suites": ["unknown"]}) + "\n")
    unknown = mdf(python_exe, "project-verify", "run", *args)
    assert "unknown_suite" in unknown.stderr
    suites.write_text(json.dumps({"suites": ["billing"]}) + "\n")
    payload(mdf(python_exe, "project-verify", "run", *args))
    evidence = json.loads(
        (work / "changes/unreleased/bug-cd34/code-review.verification.json").read_text()
    )
    assert evidence["collections"] == ["quick", "billing"]
    payload(mdf(python_exe, "project-verify", "check", *args))
    evidence["collections"] = ["quick"]
    (work / "changes/unreleased/bug-cd34/code-review.verification.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    assert "stale_verification" in mdf(python_exe, "project-verify", "check", *args).stderr


def test_layered_release_rejects_quick_only_evidence(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "release",
                          "--version", "1.3.0"))
    work = Path(created["worktree"])
    item = '    - id: check\n      kind: custom\n      command: "true"'
    layered = (
        item + "\n      collections: [quick, full]\n"
        "    - id: slow\n      kind: e2e\n      command: \"true\"\n"
        "      collections: [full]"
    )
    (work / ".mdf/manifest.yaml").write_text(
        (work / ".mdf/manifest.yaml").read_text().replace(item, layered, 1)
    )
    args = ["--repo", str(work)]
    payload(mdf(python_exe, "project-verify", "run", *args))
    path = work / "changes/unreleased/1.3.0/code-review.verification.json"
    evidence = json.loads(path.read_text())
    assert evidence["collections"] == ["full"]
    assert {item["id"] for item in evidence["results"]} == {"check", "slow"}
    evidence["collections"] = ["quick"]
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    assert "stale_verification" in mdf(python_exe, "project-verify", "check", *args).stderr
