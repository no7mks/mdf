"""fact 前 hook 的真实执行、失败改动与 rule 交接。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def hook_repo(tmp_path, script=None, *, hook_type="command", path="pre finish.sh"):
    repo = local_repo(tmp_path / "with space")
    (repo / "README.md").write_text("# 测试项目\n")
    (repo / "GLOSSARY.md").write_text("# 测试术语\n")
    if script is not None:
        target = repo / path
        target.write_text(("#!/bin/sh\n" if hook_type == "command" else "") + script)
        if hook_type == "command":
            target.chmod(0o755)
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() +
                        f'\nhooks:\n  pre-gitflow-finish:\n    type: {hook_type}\n'
                        f'    path: "{path}"\n')
    commit(repo, "test: 配置 fact 前 hook")
    git(repo, "checkout", "-b", "feature/hook")
    return repo


@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize("code_change", [False, True])
def test_finish_command_classifies_changes_even_on_failure(python_exe, tmp_path, exit_code, code_change):
    script = 'printf "%s\\n%s\\n%s\\n" "$PWD" "$MDF_WORKTREE" "$MDF_BRANCH" > docs/hook.md\n'
    if code_change:
        script += "printf '# new code\\n' > new.py\n"
    repo = hook_repo(tmp_path, script + 'echo hook-output\nprintf "\\377"\n' + f"exit {exit_code}\n")
    before = git(repo, "rev-parse", "HEAD").stdout.strip()
    response = mdf(python_exe, "pre-gitflow-finish", "--repo", str(repo))
    result = payload(response)
    assert result["before_head"] == before
    assert result["hook"]["returncode"] == exit_code
    assert result["hook"]["status"] == ("success" if exit_code == 0 else "failed")
    assert result["changed_paths"] == (["docs/hook.md", "new.py"] if code_change else ["docs/hook.md"])
    assert result["needs_recheck"] is code_change
    assert (repo / "docs/hook.md").read_text().splitlines() == [str(repo), str(repo), "feature/hook"]
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == before
    assert "hook-output" in response.stderr and "\ufffd" in response.stderr
    assert "失败仅汇报" in response.stderr


@pytest.mark.parametrize("mutation,expected", [
    ("printf '# code\\n' > new.py\ngit add new.py\ngit commit -m 'test: hook 修改'\n", ["new.py"]),
    ("rm tests/test_service.py\n", ["tests/test_service.py"]),
    ("git mv tests/test_service.py docs/renamed.md\n", ["docs/renamed.md", "tests/test_service.py"]),
    ("chmod +x README.md\n", ["README.md"]),
    ("ln -s README.md hook.md\n", ["hook.md"]),
    ("git update-index --chmod=+x README.md\n", ["README.md"]),
    ("printf '# code\\n' > tests/test_service.py\ngit add tests/test_service.py\n"
     "git show HEAD:tests/test_service.py > tests/test_service.py\n", ["tests/test_service.py"]),
])
def test_non_document_changes_require_recheck(python_exe, tmp_path, mutation, expected):
    repo = hook_repo(tmp_path, mutation)
    result = payload(mdf(python_exe, "pre-gitflow-finish", "--repo", str(repo)))
    assert result["hook"]["status"] == "success"
    assert result["changed_paths"] == expected
    assert result["needs_recheck"] is True


def test_rule_is_classified_after_execution_without_repeating(python_exe, tmp_path):
    repo = hook_repo(tmp_path, "规则内容。\n", hook_type="rule", path="rule.md")
    prepared = payload(mdf(python_exe, "pre-gitflow-finish", "--repo", str(repo)))
    assert prepared["hook"]["status"] == "pending"
    assert prepared["hook"]["cwd"] == str(repo)
    assert "needs_recheck" not in prepared
    (repo / "new.py").write_text("# Agent 修改\n")
    result = payload(mdf(python_exe, "pre-gitflow-finish", "--repo", str(repo),
                         "--after", prepared["before_head"]))
    assert result["changed_paths"] == ["new.py"]
    assert result["needs_recheck"] is True
    assert "hook" not in result


@pytest.mark.parametrize("hook_type", ["command", "rule"])
def test_missing_file_is_nonblocking(python_exe, tmp_path, hook_type):
    repo = hook_repo(tmp_path, hook_type=hook_type)
    result = payload(mdf(python_exe, "pre-gitflow-finish", "--repo", str(repo)))
    assert result["hook"]["status"] == "failed"
    assert result["changed_paths"] == []
    assert result["needs_recheck"] is False


def test_nonexecutable_command_is_nonblocking(python_exe, tmp_path):
    repo = hook_repo(tmp_path, "exit 0\n")
    (repo / "pre finish.sh").chmod(0o644)
    commit(repo)
    result = payload(mdf(python_exe, "pre-gitflow-finish", "--repo", str(repo)))
    assert result["hook"]["status"] == "failed"
    assert result["needs_recheck"] is False


@pytest.mark.parametrize("branch", ["feature/hook", "bugfix/hook", "release/1.3.0", "hotfix/1.2.1"])
def test_unconfigured_hook_is_skipped_on_all_delivery_kinds(python_exe, tmp_path, branch):
    repo = local_repo(tmp_path)
    git(repo, "checkout", "-b", branch)
    result = payload(mdf(python_exe, "pre-gitflow-finish", "--repo", str(repo)))
    assert result["hook"]["status"] == "skipped"
    assert result["changed_paths"] == []
    assert result["needs_recheck"] is False


def test_dirty_entry_does_not_execute_hook(python_exe, tmp_path):
    repo = hook_repo(tmp_path, "touch executed\n")
    (repo / "unrelated.py").write_text("# 未提交\n")
    response = mdf(python_exe, "pre-gitflow-finish", "--repo", str(repo))
    assert response.returncode == 1
    assert not (repo / "executed").exists()
    assert json.loads(response.stderr.splitlines()[-1])["error"] == "dirty_worktree"


@pytest.mark.parametrize("before_head", ["", "HEAD", "0" * 40])
def test_invalid_after_never_executes_hook(python_exe, tmp_path, before_head):
    repo = hook_repo(tmp_path, "touch executed\n")
    response = mdf(python_exe, "pre-gitflow-finish", "--repo", str(repo), "--after", before_head)
    assert response.returncode == 1
    assert not (repo / "executed").exists()


def test_rule_doc_deletion_and_rename_are_document_only(python_exe, tmp_path):
    repo = hook_repo(tmp_path, "规则内容。\n", hook_type="rule", path="rule.md")
    prepared = payload(mdf(python_exe, "pre-gitflow-finish", "--repo", str(repo)))
    git(repo, "mv", "README.md", "docs/renamed.md")
    (repo / "GLOSSARY.md").unlink()
    result = payload(mdf(python_exe, "pre-gitflow-finish", "--repo", str(repo),
                         "--after", prepared["before_head"]))
    assert result["changed_paths"] == ["GLOSSARY.md", "README.md", "docs/renamed.md"]
    assert result["needs_recheck"] is False
