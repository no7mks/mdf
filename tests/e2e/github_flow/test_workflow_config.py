"""workflow 配置：init 写入、manifest 校验、空闲态切换与 CI 触发分支。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from support_github_flow import commit, error_of, github_flow_repo, set_workflow


def _init(python_exe, repo, *extra):
    return mdf(python_exe, "init", "--repo", str(repo), "--latest-release", "none",
               *all_not_applicable_baselines(), *verification_args(), *extra)


def test_init_writes_workflow_block(python_exe, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# T\n", encoding="utf-8")
    init_git(repo)
    git(repo, "branch", "-m", "main")
    data = payload(_init(python_exe, repo, "--workflow", "github-flow", "--trunk", "main"))
    assert data["plan"]["workflow"] == {"model": "github-flow", "trunk": "main"}
    manifest = (repo / ".mdf/manifest.yaml").read_text(encoding="utf-8")
    assert "workflow:\n  model: github-flow\n  trunk: main\n" in manifest


def test_init_without_workflow_keeps_manifest_free_of_workflow(python_exe, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# T\n", encoding="utf-8")
    init_git(repo)
    git(repo, "branch", "-m", "master")
    data = payload(_init(python_exe, repo))
    assert data["plan"]["workflow"] == {"model": "gitflow", "trunk": "master"}
    assert "workflow:" not in (repo / ".mdf/manifest.yaml").read_text(encoding="utf-8")


def test_init_rejects_reserved_trunk(python_exe, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# T\n", encoding="utf-8")
    init_git(repo)
    assert error_of(_init(python_exe, repo, "--workflow", "github-flow", "--trunk", "develop"))["error"] == "invalid_workflow"


def test_init_rerun_cannot_silently_change_workflow(python_exe, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# T\n", encoding="utf-8")
    init_git(repo)
    git(repo, "branch", "-m", "master")
    payload(_init(python_exe, repo, "--workflow", "github-flow"))
    commit(repo)
    assert error_of(_init(python_exe, repo, "--workflow", "gitflow"))["error"] == "workflow_switch_required"
    payload(_init(python_exe, repo, "--workflow", "github-flow"))


def test_doctor_reports_invalid_workflow(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path)
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace("trunk: master", "trunk: develop"), encoding="utf-8")
    result = mdf(python_exe, "validate", "--repo", str(repo))
    codes = {item["code"] for item in json.loads(result.stdout)["findings"]}
    assert "manifest.workflow" in codes


def test_switch_gitflow_to_github_flow_preserves_history_and_branches(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    before = git(repo, "rev-parse", "develop").stdout
    data = payload(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow"))
    assert data["changed"] and data["to"] == {"model": "github-flow", "trunk": "master"}
    assert git(repo, "rev-parse", "develop").stdout == before
    assert git(repo, "status", "--porcelain").stdout == ""
    assert "workflow:\n  model: github-flow\n  trunk: master\n" in (repo / ".mdf/manifest.yaml").read_text()
    again = payload(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow"))
    assert again["changed"] is False
    back = payload(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "gitflow"))
    assert back["to"]["model"] == "gitflow"
    assert (repo / ".mdf/manifest.yaml").read_text().count("workflow:") == 1


def local_gitflow(tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "-m", "master")
    git(repo, "branch", "develop")
    return repo


def test_switch_trunk_must_contain_old_history(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    git(repo, "checkout", "--orphan", "main")
    git(repo, "commit", "--allow-empty", "-m", "test: 孤立 trunk")
    result = mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow", "--trunk", "main")
    assert error_of(result)["error"] == "trunk_history_lost"


def test_switch_to_new_trunk_from_current_history(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    git(repo, "checkout", "-b", "main")
    data = payload(mdf(python_exe, "workflow", "switch", "--repo", str(repo),
                       "--model", "github-flow", "--trunk", "main"))
    assert data["from"]["trunk"] == "master" and data["to"]["trunk"] == "main"
    assert git(repo, "rev-parse", "--verify", "master").returncode == 0


def test_switch_requires_running_on_target_trunk(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    git(repo, "checkout", "develop")
    result = mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow")
    assert error_of(result)["error"] == "not_on_trunk"


@pytest.mark.parametrize("setup,detail", [
    ("branch", "feature/x"), ("planning", "planning"), ("finish", "feature-x.json"),
])
def test_switch_refuses_when_not_idle(python_exe, tmp_path, setup, detail):
    repo = local_gitflow(tmp_path)
    if setup == "branch":
        git(repo, "branch", detail)
    elif setup == "planning":
        git(repo, "checkout", "-b", "planning")
        (repo / "plan.txt").write_text("规划\n")
        commit(repo, "docs: 规划")
        git(repo, "checkout", "master")
    else:
        folder = Path(git(repo, "rev-parse", "--absolute-git-dir").stdout.strip()) / "mdf" / "finish"
        folder.mkdir(parents=True)
        (folder / detail).write_text(json.dumps({"completed": False}))
    failed = error_of(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "github-flow"))
    assert failed["error"] == "workflow_not_idle"
    assert "workflow:" not in (repo / ".mdf/manifest.yaml").read_text()


def test_switch_to_gitflow_requires_develop(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path)
    failed = error_of(mdf(python_exe, "workflow", "switch", "--repo", str(repo), "--model", "gitflow"))
    assert failed["error"] == "missing_branch"


@pytest.mark.parametrize("provider,expected", [
    ("github", "branches: [master, 'support/**']"),
    ("gitlab", '$CI_COMMIT_BRANCH == "master" || $CI_COMMIT_BRANCH =~ /^support\\/.*$/'),
])
def test_ci_follows_workflow(python_exe, tmp_path, provider, expected):
    repo = github_flow_repo(tmp_path)
    data = payload(mdf(python_exe, "workflow", "ci", "--repo", str(repo), "--provider", provider))
    assert data["branches"] == ["master", "support/**"]
    assert expected in data["content"]
    assert "develop" not in data["content"].split("mdf-review")[0] or provider == "github"


def test_ci_gitflow_keeps_develop_and_trunk(python_exe, tmp_path):
    repo = local_gitflow(tmp_path)
    set_workflow(repo, "gitflow", "master")
    data = payload(mdf(python_exe, "workflow", "ci", "--repo", str(repo)))
    assert data["branches"] == ["develop", "master"]
    assert "branches: [develop, master]" in data["content"]
