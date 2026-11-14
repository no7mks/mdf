"""github-flow local mode：从 trunk 起、合回 trunk，无 develop；发布 tag 固定在 release_head。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from support_delivery import write_changelog_release
from support_github_flow import commit, error_of, github_flow_repo, has_ref


def start(python_exe, repo, tmp_path, kind, *extra, objectives=None):
    from mdf_core.lifecycle.manual import STEPS
    if kind == "feature":
        obj = tmp_path / "manual.md"
        obj.write_text("# 目标\n\n" + "".join(f"- [{'x' if n == 'start' else ' '}] {n}\n" for n in STEPS))
        extra = ("--manual", "--name", "manual-work", *extra)
    else:
        obj = objectives or (write_release_objectives(tmp_path) if kind == "release" else write_work_objectives(tmp_path))
    return payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", kind,
                       "--objectives-file", str(obj), *extra))


def finishable(python_exe, tmp_path, kind, version="1.2.1"):
    load_core_module()
    repo, remote = github_flow_repo(tmp_path, origin=True)
    if kind == "hotfix":
        git(repo, "tag", "-a", "v1.2.0", "-m", "test: v1.2.0")
        git(repo, "push", "origin", "--tags")
    extra = ("--bug", "bug-CD34") if kind == "bugfix" else (("--version", version) if kind != "feature" else ())
    data = start(python_exe, repo, tmp_path, kind, *extra)
    work = Path(data["worktree"])
    if kind == "feature":
        from mdf_core.lifecycle.manual import STEPS
        root = work / "changes/unreleased/manual-work"
        (root / "objectives.md").write_text("# 目标\n\n" + "".join(f"- [x] {n}\n" for n in STEPS))
        (root / "CHANGE.md").write_text(
            "---\nchange_kind: feature\nsource_branch: feature/manual-work\nproposals: []\n---\n成果\n")
    elif kind in {"release", "hotfix"}:
        write_changelog_release(work, version)
    (work / "finish.txt").write_text("本次交付\n")
    commit(work)
    return repo, remote, work, data


@pytest.mark.parametrize("kind", ["feature", "bugfix"])
def test_feature_and_bugfix_start_and_finish_on_trunk(python_exe, tmp_path, kind):
    repo, remote, work, data = finishable(python_exe, tmp_path, kind)
    assert data["base"] == "master"
    assert not has_ref(repo, "develop")
    if kind == "feature":
        identity = json.loads((work / "changes/unreleased/manual-work/delivery.json").read_text())
        assert identity["target"] == "master" and "base_branch" not in identity
    source = git(work, "rev-parse", "HEAD").stdout.strip()
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert done["targets"] == ["master"]
    git(repo, "merge-base", "--is-ancestor", source, "master")
    assert not has_ref(repo, "develop")


@pytest.mark.parametrize("kind", ["release", "hotfix"])
def test_publish_merges_only_trunk_and_tags_release_head(python_exe, tmp_path, kind):
    repo, remote, work, data = finishable(python_exe, tmp_path, kind)
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    trunk_before = git(repo, "rev-parse", "master").stdout
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    target = "support/1.2" if kind == "hotfix" else "master"
    assert done["targets"] == [target] and done["tag"] == "v1.2.1" and done["pushed"] is True
    assert git(repo, "rev-parse", "v1.2.1^{commit}").stdout.strip() == head
    git(repo, "merge-base", "--is-ancestor", head, target)
    if kind == "hotfix":
        assert git(repo, "rev-parse", "master").stdout == trunk_before
    assert git(remote, "rev-parse", "master").stdout == git(repo, "rev-parse", "master").stdout
    assert not has_ref(repo, "develop")


@pytest.mark.parametrize("entry", [
    ("start", "--kind", "on-demand-release", "--version", "1.3.0"),
    ("start", "--kind", "feature", "--from-master", "--manual", "--name", "x"),
])
def test_gitflow_only_start_entries_are_rejected(python_exe, tmp_path, entry):
    repo = github_flow_repo(tmp_path)
    args = list(entry)
    args[1:1] = ["--repo", str(repo)]
    result = mdf(python_exe, *args, "--objectives-file", str(write_work_objectives(tmp_path)))
    assert error_of(result)["error"] == "github_flow_unsupported"


def test_publish_state_records_fixed_release_head(python_exe, tmp_path):
    repo, remote, work, data = finishable(python_exe, tmp_path, "release")
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    state = Path(git(repo, "rev-parse", "--absolute-git-dir").stdout.strip()) / "mdf/finish/release/1.2.1.json"
    stored = json.loads(state.read_text())
    assert stored["release_head"] == stored["head"] and len(stored["release_head"]) == 40
    assert stored["publish_branch"] == "master" and done["tag"] == "v1.2.1"
