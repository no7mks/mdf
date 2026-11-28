"""reconcile 的真实 Git 历史与结构化外部 evidence 夹具。"""
import json
from pathlib import Path

from mdf_test_support import copy_fixture, init_git, git, mdf, payload
from support_delivery import commit
from support_github_flow import set_workflow


def repository(tmp_path, *, github=True, pr=False, remote=False):
    repo = copy_fixture(tmp_path)
    set_workflow(repo, model="github-flow" if github else "gitflow")
    if pr:
        path = repo / ".mdf/manifest.yaml"
        path.write_text(path.read_text() + "closeout:\n  mode: pr\n  provider: github\n")
    init_git(repo, previous_release=True)
    git(repo, "branch", "-m", "master")
    if not github:
        git(repo, "branch", "develop")
    if remote:
        bare = tmp_path / "origin.git"
        bare.mkdir()
        git(bare, "init", "--bare")
        git(bare, "symbolic-ref", "HEAD", "refs/heads/master")
        git(repo, "remote", "add", "origin", str(bare))
        git(repo, "push", "origin", "--all")
        git(repo, "push", "origin", "--tags")
        git(repo, "remote", "set-head", "origin", "--auto")
    return repo


def call(python_exe, repo, action, *args):
    return mdf(python_exe, "reconcile", action, "--repo", str(repo), *args)


def proof(repo, scopes=("fact", "lint", "build", "quick", "smoke", "release", "code-review")):
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    return {"commit": head, "tree": git(repo, "rev-parse", "HEAD^{tree}").stdout.strip(),
            "checks": [{"scope": list(scopes), "passed": True, "artifacts": ["https://ci.example.test/runs/1"]}]}


def change(repo, name="delta"):
    (repo / "src" / f"{name}.py").write_text(f"{name} = True\n")
    commit(repo)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def spec_file(tmp_path, repo, head, commits=None):
    path = tmp_path / "record.json"
    path.write_text(json.dumps({"commit": head, "fact": proof(repo),
                               "changes": [{"slug": "external-work", "commits": commits or [head],
                                            "release_notes": {"Changed": ["已核实的外部实现"]}}]}))
    return path


def apply(python_exe, work, spec, version="1.3.0"):
    return call(python_exe, work, "apply", "--version", version, "--release-date", "2026-11-28", "--record-file", str(spec))


def prepare(python_exe, repo, version="1.3.0", *extra):
    result = payload(call(python_exe, repo, "prepare", "--version", version, *extra))["result"]
    return Path(result["worktree"])
