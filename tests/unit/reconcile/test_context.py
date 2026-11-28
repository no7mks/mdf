"""新记录探测不得破坏已删除 source 的标准发布恢复。"""
from support_reconcile import repository
from mdf_core.reconciliation.context import external_record
from mdf_core.workspace.workflow_policy import target_for
from mdf_core.reconciliation.context import inspect, state_path
from mdf_core.lifecycle.delivery_state import write_json
from mdf_core.foundation.errors import MDFError
from mdf_test_support import git
from support_reconcile import change
from types import SimpleNamespace
import pytest


def test_missing_source_ref_leaves_recovery_to_publication_receipt(tmp_path):
    repo = repository(tmp_path)
    assert external_record(repo, "hotfix/already-closed", "refs/heads/hotfix/already-closed") is None
    assert target_for(repo, "hotfix/already-closed") == "master"


def test_pending_operation_does_not_ignore_another_commit(tmp_path):
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "release/1.3.0")
    change(repo)
    write_json(state_path(repo), {"source": "release/1.3.0", "record_mode": "ledgerless", "version": "1.3.0", "release_line": "master"})
    args = SimpleNamespace(version="1.3.0", support=None, commit="v1.2.0", tag=None)
    with pytest.raises(MDFError, match="在途"):
        inspect(repo, args)
