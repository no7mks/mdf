"""squash 不能承接文档路径中尚未验收的声明输入。"""
import pytest

from mdf_test_support import git
from support_reconcile import repository
from support_delivery import commit
from mdf_core.lifecycle.squash_state import covered_by_consolidation


@pytest.mark.parametrize("declaration", ["source", "module-extra", "tests", "suite-extra"])
def test_declared_document_input_blocks_acceptance_mapping(tmp_path, declaration):
    repo = repository(tmp_path)
    path = repo / ".mdf/modules.yaml"
    text = path.read_text()
    if declaration == "source":
        text = text.replace('    sourceset:\n', '    sourceset:\n      - "docs/runtime.md"\n')
    elif declaration == "module-extra":
        text = text.replace('    ignore: []', '    ignore: []\n    extra_inputs: [docs/runtime.md]')
    elif declaration == "tests":
        text = text.replace('      tests:\n', '      tests:\n        - "docs/runtime.md"\n', 1)
    else:
        text = text.replace('    smoke:\n', '    smoke:\n      extra_inputs: [docs/runtime.md]\n')
    path.write_text(text)
    commit(repo)
    accepted = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "docs/runtime.md").write_text("未经验收的新输入\n")
    commit(repo)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    assert not covered_by_consolidation(repo, accepted, {"head": head, "start_head": head})
