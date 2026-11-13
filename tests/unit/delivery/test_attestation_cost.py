"""凭证核验开销：固定 fixture 上一次指纹计算加命中核验的耗时有上界。"""
from __future__ import annotations
import time

from mdf_test_support import *  # noqa: F403

load_core_module()
from mdf_core.execution import attestations  # noqa: E402

ITEM = {"id": "quick:default", "entry": "quick", "command": "true", "module": "default", "budget": 60}


def test_fingerprint_and_hit_check_stay_under_the_budget(tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    (repo / ".mdf/logs/ev").mkdir(parents=True)
    (repo / ".mdf/logs/ev/run.log").write_text("ok\n")
    fp = attestations.fingerprint(repo, ITEM)
    attestations.record_result(repo, ITEM, fp, {"log": ".mdf/logs/ev", "exit_code": 0}, 0.5)
    started = time.perf_counter()
    again = attestations.fingerprint(repo, ITEM)
    record = attestations.reusable(repo, ITEM, again)
    elapsed = time.perf_counter() - started
    assert record is not None and record["key"] == fp["key"]
    assert elapsed < 2
