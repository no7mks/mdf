"""无 PRP 的人工 feature 启动与收口。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import local_repo, commit

STEPS = ("start", "人工工作", "lint", "code-review", "verify smoke", "fact update", "catch-up", "close-out")


def objectives(done=False):
    return "# 交付目标\n\n" + "".join(
        f"- [{'x' if done or name == 'start' else ' '}] {name}\n" for name in STEPS
    )


def start_manual(python_exe, tmp_path, *extra):
    repo = local_repo(tmp_path)
    obj = tmp_path / "manual.md"
    obj.write_text(objectives())
    result = mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                 "--manual", "--name", "manual-work", "--objectives-file", str(obj), *extra)
    return repo, result


def test_manual_feature_start_and_finish_without_changing_prp(python_exe, tmp_path):
    repo, result = start_manual(python_exe, tmp_path)
    data = payload(result)
    work = Path(data["worktree"])
    root = work / "changes/unreleased/manual-work"
    identity = json.loads((root / "delivery.json").read_text())
    assert data["branch"] == "feature/manual-work"
    assert data["roles"] == {"qa": [], "dev": []}
    assert tuple(data["roster"][key] for key in ("qa", "dev", "reviewers")) == (0, 0, 1)
    assert identity["manual"] is True and identity["needs_design"] is False
    assert "proposal" not in identity
    assert (root / "objectives.md").read_text() == objectives()
    before = git(repo, "show", f"develop:docs/proposals/{PRP_NAME}").stdout
    (root / "CHANGE.md").write_text(
        "---\nchange_kind: feature\nsource_branch: feature/manual-work\nproposals: []\n---\n成果\n"
    )
    commit(work)
    failed = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    assert "manual_work_pending" in failed.stderr
    (root / "objectives.md").write_text(objectives(done=True))
    commit(work)
    result = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert result["targets"] == ["develop"]
    assert git(repo, "show", f"develop:docs/proposals/{PRP_NAME}").stdout == before
    assert not git(work, "branch", "--show-current").stdout.strip()
    assert git(repo, "show", "develop:changes/unreleased/manual-work/delivery.json").stdout


@pytest.mark.parametrize("extra,error", [
    (["--proposal", "prp-0001"], "invalid_manual"),
    (["--reviewers", "2"], "invalid_manual"),
    (["--roster", "min-tdd"], "invalid_manual"),
    (["--name", "bad/name"], "invalid_slug"),
])
def test_manual_rejects_invalid_parameters_before_creating_branch(python_exe, tmp_path, extra, error):
    repo, result = start_manual(python_exe, tmp_path, *extra)
    assert result.returncode != 0 and error in result.stderr
    assert not git(repo, "for-each-ref", "refs/heads/feature/").stdout
