"""start 成功后的 hook cwd、上下文与非阻塞失败。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize("binary_output", [False, True])
def test_start_command_hook(python_exe, tmp_path, exit_code, binary_output):
    repo = local_repo(tmp_path / "with space")
    git(repo, "checkout", "develop")
    script = repo / "post start.sh"
    script.write_text(
        '#!/bin/sh\n'
        'printf "%s\\n%s\\n%s\\n" "$PWD" "$MDF_NEW_WORKTREE" '
        '"$MDF_OLD_WORKTREE" > hook-result.txt\n'
        f'echo hook-output\n'
        + ('printf "\\377"\n' if binary_output else '')
        + f'exit {exit_code}\n'
    )
    script.chmod(0o755)
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() +
                        '\nhooks:\n  post-gitflow-start:\n'
                        '    type: command\n    path: "post start.sh"\n')
    commit(repo, "test: 配置 hook")
    objectives = tmp_path / "objectives.md"
    objectives.write_text("# 目标\n\n- needs_design: yes\n\n测试 hook。\n")
    response = mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                   "--proposal", "prp-001", "--objectives-file", str(objectives))
    result = payload(response)
    work = Path(result["worktree"])
    assert (work / "hook-result.txt").read_text().splitlines() == [str(work), str(work), str(repo)]
    assert result["hook"]["returncode"] == exit_code
    assert result["hook"]["status"] == ("success" if exit_code == 0 else "failed")
    assert result["ok"] is True
    assert "开始执行 hook" in response.stderr
    assert "执行结束" in response.stderr
    assert "hook-output" in response.stderr
    if binary_output:
        assert "\ufffd" in response.stderr
    assert (work / "changes/unreleased/service-health/delivery.json").is_file()


def test_start_rule_hook_is_handed_to_agent(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    git(repo, "checkout", "develop")
    (repo / "rule.md").write_text("记录执行结果。\n")
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() +
                        '\nhooks:\n  post-gitflow-start:\n'
                        '    type: rule\n    path: rule.md\n')
    commit(repo, "test: 配置 rule")
    objectives = tmp_path / "objectives.md"
    objectives.write_text("# 目标\n\n- needs_design: yes\n\n测试 hook。\n")
    result = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                         "--proposal", "prp-001", "--objectives-file", str(objectives)))
    assert result["hook"]["status"] == "pending"
    assert result["hook"]["type"] == "rule"
    assert result["hook"]["cwd"] == result["worktree"]
    assert result["hook"]["old_worktree"] == str(repo)
