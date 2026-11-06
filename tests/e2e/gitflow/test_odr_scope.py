"""ODR 非 MDF 来源、直接工作与范围外历史。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import local_repo, commit


def start_scope(python_exe, repo, tmp_path, entries):
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps(entries))
    result = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "on-demand-release",
                         "--version", "1.3.0", "--scope-file", str(scope),
                         "--objectives-file", str(write_release_objectives(tmp_path))))
    return Path(result["worktree"])


def accept(python_exe, work, tmp_path, entries):
    evidence = {}
    for key in ("review", "tests", "fact"):
        path = f"changes/unreleased/1.3.0/{key}.md"
        (work / path).write_text(f"{key}: 已核对本项 diff，通过。\n")
        evidence[key] = path
    if git(work, "status", "--porcelain").stdout.strip():
        commit(work)
    for item in entries:
        item.update(result="passed", evidence=evidence)
    scope = tmp_path / "accepted.json"
    scope.write_text(json.dumps(entries))
    payload(mdf(python_exe, "delivery", "scope", "--repo", str(work), "--scope-file", str(scope)))
    commit(work)


def checkpoint(python_exe, work):
    return mdf(python_exe, "delivery", "checkpoint", "--repo", str(work))


def test_non_mdf_branch_requires_no_child_materials(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    base = git(repo, "rev-parse", "master").stdout.strip()
    git(repo, "checkout", "-b", "external", "master")
    (repo / "external.py").write_text("value = 1\n")
    commit(repo)
    tip = git(repo, "rev-parse", "HEAD").stdout.strip()
    entries = [dict(id="external", kind="branch", scope="外部功能", source="external", base=base, tip=tip)]
    work = start_scope(python_exe, repo, tmp_path, entries)
    assert not payload(checkpoint(python_exe, work))["result"]["ready"]
    git(work, "merge", "--no-ff", "--no-edit", "external")
    accept(python_exe, work, tmp_path, entries)
    assert payload(checkpoint(python_exe, work))["result"]["ready"]
    assert not (work / "changes/unreleased/external").exists()
    (work / "unselected.py").write_text("unselected = True\n")
    commit(work)
    assert "unexpected_changes" in checkpoint(python_exe, work).stderr


def test_direct_work_requires_scope_and_evidence(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    entries = [dict(id="fix", kind="direct", scope="修复", source="ODR 内修复")]
    work = start_scope(python_exe, repo, tmp_path, entries)
    (work / "fix.py").write_text("fixed = True\n")
    commit(work)
    entries[0]["commits"] = [git(work, "rev-parse", "HEAD").stdout.strip()]
    assert "unexpected_changes" in checkpoint(python_exe, work).stderr
    accept(python_exe, work, tmp_path, entries)
    assert payload(checkpoint(python_exe, work))["result"]["ready"]
    (work / entries[0]["evidence"]["tests"]).write_text("")
    assert not payload(checkpoint(python_exe, work))["result"]["ready"]


def test_develop_history_requires_cherry_pick(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    base = git(repo, "rev-parse", "master").stdout.strip()
    git(repo, "checkout", "develop")
    (repo / "unselected.py").write_text("unselected = True\n")
    commit(repo)
    (repo / "selected.py").write_text("selected = True\n")
    commit(repo)
    original = git(repo, "rev-parse", "HEAD").stdout.strip()
    entries = [dict(id="pick", kind="cherry-pick", scope="单独修复", source="develop commit", originals=[original])]
    work = start_scope(python_exe, repo, tmp_path, entries)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([dict(id="bad", kind="branch", scope="错误来源", source="develop", base=base, tip=original)]))
    assert "unreleased_dependency" in mdf(python_exe, "delivery", "scope", "--repo", str(work), "--scope-file", str(bad)).stderr
    git(work, "cherry-pick", original)
    entries[0]["commits"] = [git(work, "rev-parse", "HEAD").stdout.strip()]
    accept(python_exe, work, tmp_path, entries)
    assert payload(checkpoint(python_exe, work))["result"]["ready"]
    assert not (work / "unselected.py").exists()


def test_direct_only_release_archives_evidence_and_preserves_commits(python_exe, tmp_path):
    from support_delivery import start_repo
    from mdf_core.workspace.squash import inspect
    repo, _remote = start_repo(tmp_path)
    replace(repo / "docs/bugs" / BUG_NAME, "status: open", "status: closed\nfixed_in: 1.3.0")
    commit(repo)
    git(repo, "branch", "-f", "develop", "master")
    git(repo, "push", "origin", "master", "develop")
    entries = [dict(id="fix", kind="direct", scope="修正健康检查", source="ODR 修复")]
    work = start_scope(python_exe, repo, tmp_path, entries)
    (work / "fix.py").write_text("fixed = True\n")
    commit(work)
    applied = git(work, "rev-parse", "HEAD").stdout.strip()
    entries[0]["commits"] = [applied]
    accept(python_exe, work, tmp_path, entries)
    plan = inspect(work, refresh=False)
    assert applied not in plan["commits"] and plan["floor"] == applied
    obj = work / "changes/unreleased/1.3.0/objectives.md"
    obj.write_text(obj.read_text().replace("[ ]", "[x]"))
    commit(work)
    seed_verify_branch(python_exe, work)
    result = payload(mdf(python_exe, "release-closeout", "--repo", str(work), "--release-date", "2026-11-06"))
    assert result["release_set"] == []
    assert "修正健康检查" in (work / "CHANGELOG.md").read_text()
    commit(work)
    assert payload(checkpoint(python_exe, work))["result"]["ready"]
    published = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert published["targets"] == ["master", "develop"]


def test_merge_resolution_must_be_registered(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    (repo / "shared.txt").write_text("base\n")
    commit(repo)
    base = git(repo, "rev-parse", "master").stdout.strip()
    git(repo, "checkout", "-b", "external", "master")
    (repo / "shared.txt").write_text("external\n")
    commit(repo)
    tip = git(repo, "rev-parse", "HEAD").stdout.strip()
    entries = [dict(id="branch", kind="branch", scope="外部改动", source="external", base=base, tip=tip),
               dict(id="direct", kind="direct", scope="本版改动", source="ODR 修复")]
    work = start_scope(python_exe, repo, tmp_path, entries)
    (work / "shared.txt").write_text("direct\n")
    commit(work)
    entries[1]["commits"] = [git(work, "rev-parse", "HEAD").stdout.strip()]
    from mdf_core.workspace.merge_policy import git as raw_git
    assert raw_git(work, "merge", "--no-ff", "--no-edit", "external", check=False).returncode != 0
    (work / "shared.txt").write_text("resolved\n")
    commit(work)
    resolution = git(work, "rev-parse", "HEAD").stdout.strip()
    accept(python_exe, work, tmp_path, entries)
    assert "unexpected_changes" in checkpoint(python_exe, work).stderr
    entries[1]["commits"].append(resolution)
    accept(python_exe, work, tmp_path, entries)
    assert payload(checkpoint(python_exe, work))["result"]["ready"]


def test_master_catchup_is_not_unselected_work(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    entries = [dict(id="fix", kind="direct", scope="本版修复", source="ODR 修复")]
    work = start_scope(python_exe, repo, tmp_path, entries)
    (work / "fix.py").write_text("fixed = True\n")
    commit(work)
    entries[0]["commits"] = [git(work, "rev-parse", "HEAD").stdout.strip()]
    accept(python_exe, work, tmp_path, entries)
    (repo / "published.py").write_text("published = True\n")
    commit(repo)
    git(work, "merge", "--no-ff", "--no-edit", "master")
    assert payload(checkpoint(python_exe, work))["result"]["ready"]
