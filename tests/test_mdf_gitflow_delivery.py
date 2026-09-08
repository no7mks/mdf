"""在隔离 Git 远端中验证启动失败现场与版本收口后的交付。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403


def attach_origin(repo: Path, tmp_path: Path) -> Path:
    remote = tmp_path / "origin.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    git(remote, "symbolic-ref", "HEAD", "refs/heads/master")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "--all", "--set-upstream", "origin")
    git(repo, "remote", "set-head", "origin", "--auto")
    return remote


def start_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "-m", "master")
    git(repo, "branch", "develop")
    return repo, attach_origin(repo, tmp_path)


def test_start_rejected_push_preserves_local_branch_and_reports_state(
    python_exe: str, tmp_path: Path,
):
    repo, remote = start_repo(tmp_path)
    before = git(repo, "rev-parse", "develop").stdout.strip()
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    result = mdf(python_exe, "start", "--repo", str(repo),
                 "--kind", "feature", "--name", "delivery")

    assert result.returncode != 0
    error = json.loads(result.stderr)
    assert error["error"] == "start_push_failed"
    assert error["details"]["branch"] == "feature/delivery"
    assert error["details"]["local_head"] == before
    assert error["details"]["remote_state"] == "unknown"
    assert git(repo, "branch", "--show-current").stdout.strip() == "feature/delivery"
    assert not git(remote, "for-each-ref", "refs/heads/feature/delivery").stdout
    assert not git(repo, "status", "--porcelain").stdout

    hook.unlink()
    git(repo, "push", "-u", "origin", "feature/delivery")
    assert git(repo, "rev-parse", "@{upstream}").stdout.strip() == before


@pytest.mark.parametrize("kind", ["feature", "bugfix", "release", "hotfix"])
def test_start_sets_upstream_from_expected_base(
    python_exe: str, tmp_path: Path, kind: str,
):
    repo, _remote = start_repo(tmp_path)
    git(repo, "checkout", "develop")
    (repo / "development.txt").write_text("开发线\n", encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 区分开发线与发布线")
    git(repo, "push")
    base = "master" if kind == "hotfix" else "develop"
    expected = git(repo, "rev-parse", base).stdout.strip()
    identifier = ["--name", "delivery"] if kind in {"feature", "bugfix"} else [
        "--version", "1.3.0",
    ]

    result = payload(mdf(python_exe, "start", "--repo", str(repo),
                         "--kind", kind, *identifier))

    assert result["base"] == base
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == expected
    assert git(repo, "rev-parse", "@{upstream}").stdout.strip() == expected


@pytest.mark.parametrize("kind", ["release", "hotfix"])
def test_preview_then_committed_closeout_can_finish_without_reapplying(
    python_exe: str, tmp_path: Path, kind: str,
):
    if kind == "release":
        repo = prepare_release_closeout_repo(tmp_path)
        version = "1.3.0"
        git(repo, "branch", "master", "main^")
        git(repo, "branch", "develop", "main")
        extra = []
    else:
        repo = copy_fixture(tmp_path)
        replace(repo / "bugs" / BUG_NAME, "status: open", "status: fixed")
        init_git(repo)
        git(repo, "branch", "master")
        git(repo, "branch", "develop")
        version = "1.2.1"
        git(repo, "checkout", "-b", f"hotfix/{version}")
        extra = ["--hotfix-change-json", json.dumps({
            "body": "修复服务超时。",
            "fixed": [BUG_ID],
            "release_notes": {"Fixed": ["修复服务超时"]},
            "evidence": {"tests": [], "commands": ["true"], "artifacts": []},
        })]
    remote = attach_origin(repo, tmp_path)
    before_local = git(repo, "show-ref").stdout
    before_remote = git(remote, "show-ref").stdout
    args = ["release-closeout", "--repo", str(repo),
            "--release-date", "2026-09-08", *extra]

    preview = payload(mdf(python_exe, *args, "--dry-run"))
    assert preview["dry_run"] is True
    assert git(repo, "show-ref").stdout == before_local
    assert git(remote, "show-ref").stdout == before_remote
    assert not git(repo, "status", "--porcelain").stdout
    assert not (repo / "changes" / version).exists()

    payload(mdf(python_exe, *args))
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "chore: 复核并提交版本收口")
    git(repo, "push")
    root_change = repo / "changes" / version / "CHANGE.md"
    root_before = root_change.read_bytes()
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full"))
    assert_ok(mdf(python_exe, "audit", "--repo", str(repo)))

    finished = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo)))

    assert finished["tag"] == f"v{version}"
    assert root_change.read_bytes() == root_before
    git(repo, "merge-base", "--is-ancestor", "master", "develop")
    assert git(remote, "rev-parse", f"v{version}^{{}}").stdout == git(
        repo, "rev-parse", "master",
    ).stdout
    assert not git(remote, "for-each-ref", f"refs/heads/{kind}/{version}").stdout
    assert not git(repo, "for-each-ref", f"refs/heads/{kind}/{version}").stdout
    assert not git(repo, "status", "--porcelain").stdout
