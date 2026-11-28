"""文档复用排除真实验证输入，不借慢 suite 的记录通过其他检查。"""
import pytest

from mdf_test_support import copy_fixture, init_git, git, mdf, payload
from support_delivery import commit
from test_verify_reuse import verify


@pytest.mark.parametrize("suite", ["smoke", "release"])
@pytest.mark.parametrize("path", ["docs/system/topic.md", "GLOSSARY.md", "README.md", "changes/unreleased/note.md"])
def test_unclaimed_document_reuses_slow_suite(python_exe, tmp_path, suite, path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    verify(python_exe, repo, suite)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# 已核对的文档\n")
    commit(repo)
    assert verify(python_exe, repo, suite)["clear_commit"] == head


@pytest.mark.parametrize("declaration", ["sourceset", "tests", "extra_inputs", "module_extra"])
def test_document_declared_as_input_never_reuses(python_exe, tmp_path, declaration):
    repo = copy_fixture(tmp_path)
    modules = repo / ".mdf/modules.yaml"
    text = modules.read_text()
    if declaration == "sourceset":
        text = text.replace('    sourceset:\n', '    sourceset:\n      - "docs/input.md"\n')
    elif declaration == "module_extra":
        text = text.replace('    ignore: []', '    ignore: []\n    extra_inputs: [docs/input.md]')
    elif declaration == "extra_inputs":
        text = text.replace('    quick:\n', '    quick:\n      extra_inputs: [docs/input.md]\n')
    else:
        text = text.replace('      tests:\n', '      tests:\n        - "docs/input.md"\n', 1)
    modules.write_text(text)
    init_git(repo)
    verify(python_exe, repo, "smoke")
    (repo / "docs/input.md").write_text("输入已变化\n")
    commit(repo)
    assert "clear_commit" not in verify(python_exe, repo, "smoke")


@pytest.mark.parametrize("path", ["AGENTS.md", "docs/system/testing/other.md", "docs/uv.lock", "docs/requirements-dev.txt"])
def test_fixed_input_and_lockfile_in_docs_invalidate(python_exe, tmp_path, path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    verify(python_exe, repo, "smoke")
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("新的输入\n")
    commit(repo)
    assert "clear_commit" not in verify(python_exe, repo, "smoke")


@pytest.mark.parametrize("external", ["module", "suite"])
def test_external_state_does_not_reuse_documents(python_exe, tmp_path, external):
    repo = copy_fixture(tmp_path)
    path = repo / ".mdf/modules.yaml"
    text = path.read_text()
    text = (text.replace('    ignore: []', '    ignore: []\n    external_state: true') if external == "module"
            else text.replace('    smoke:\n', '    smoke:\n      external_state: true\n'))
    path.write_text(text)
    init_git(repo)
    verify(python_exe, repo, "smoke")
    (repo / "README.md").write_text("文档改动\n")
    commit(repo)
    assert "clear_commit" not in verify(python_exe, repo, "smoke")


def test_branch_slow_reuse_still_executes_each_prerequisite(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "switch", "-c", "feature/document-inputs")
    verify(python_exe, repo, "smoke")
    (repo / "README.md").write_text("文档改动\n")
    commit(repo)
    results = payload(mdf(python_exe, "verify", "branch", "--repo", str(repo)))["result"]["results"]
    assert {item["entry"] for item in results} == {"lint", "build", "quick", "smoke"}
    assert all(("clear_commit" in item) == (item["entry"] == "smoke") for item in results)
    assert all(item["passed"] for item in results)
