"""squash 负责流程 SHA 映射，未覆盖的验收端点作为安全边界。"""
import json

import pytest

from mdf_test_support import git
from mdf_core.lifecycle.squash_state import paths, protected_commits, remap
from mdf_core.lifecycle.delivery_state import write_json


@pytest.fixture
def history(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--initial-branch=master", "--template=")
    tips = []
    for content in ("start", "accepted", "consolidated"):
        (repo / "material.md").write_text(content)
        git(repo, "add", ".")
        git(repo, "commit", "-m", "test: " + content)
        tips.append(git(repo, "rev-parse", "HEAD").stdout.strip())
    return repo, tips


def test_maps_completed_catchup_through_consolidated_tip(history):
    repo, (floor, accepted, tip) = history
    catchup, integration, consolidation = paths(repo, "release/1.0.0")
    write_json(catchup, {"base": floor, "completed_head": accepted, "summary": "已验收", "remote": floor})
    write_json(integration, {"base": tip, "accepted_head": tip})
    write_json(consolidation, {"head": tip})
    assert protected_commits(repo, "release/1.0.0", tip) == set()
    git(repo, "reset", "--soft", floor)
    git(repo, "commit", "-m", "test: 整理历史")
    new = git(repo, "rev-parse", "HEAD").stdout.strip()
    remap(repo, "release/1.0.0", tip, [new], [tip])
    state = json.loads(catchup.read_text())
    assert state["completed_head"] == new and state["remote"] == floor
    assert state["summary"] == "已验收"
    assert json.loads(consolidation.read_text())["head"] == new
    assert json.loads(integration.read_text())["accepted_head"] == new
    before = [p.read_text() for p in (catchup, integration, consolidation)]
    remap(repo, "release/1.0.0", tip, [new], [tip])
    assert before == [p.read_text() for p in (catchup, integration, consolidation)]


@pytest.mark.parametrize("pending", [False, True])
def test_uncovered_endpoint_is_protected(history, pending):
    repo, (_, accepted, tip) = history
    catchup, _, consolidation = paths(repo, "release/1.0.0")
    write_json(catchup, {"base" if pending else "completed_head": accepted})
    assert accepted in protected_commits(repo, "release/1.0.0", tip)
    write_json(consolidation, {"head": tip, "pending": True})
    assert accepted in protected_commits(repo, "release/1.0.0", tip)


def test_missing_mapping_does_not_advance_acceptance(history):
    repo, (floor, accepted, tip) = history
    catchup, _, _ = paths(repo, "release/1.0.0")
    write_json(catchup, {"base": floor, "completed_head": accepted})
    before = catchup.read_text()
    git(repo, "reset", "--soft", floor)
    git(repo, "commit", "-m", "test: 无可用映射")
    remap(repo, "release/1.0.0", tip, [git(repo, "rev-parse", "HEAD").stdout.strip()], [tip])
    assert catchup.read_text() == before


@pytest.mark.parametrize("name", ["extra.py", "docs/requirements.txt", "AGENTS.md"])
def test_consolidation_cannot_cover_code_committed_after_catchup(history, name):
    repo, (floor, accepted, _) = history
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text("unreviewed = True\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "test: 未验收增量")
    tip = git(repo, "rev-parse", "HEAD").stdout.strip()
    catchup, _, consolidation = paths(repo, "release/1.0.0")
    write_json(catchup, {"base": floor, "completed_head": accepted})
    write_json(consolidation, {"head": tip, "start_head": tip})
    assert accepted in protected_commits(repo, "release/1.0.0", tip)
    git(repo, "reset", "--soft", floor)
    git(repo, "commit", "-m", "test: 整理增量")
    remap(repo, "release/1.0.0", tip, [git(repo, "rev-parse", "HEAD").stdout.strip()], [tip])
    assert json.loads(catchup.read_text())["completed_head"] == accepted


def test_gitlink_difference_is_not_an_equivalent_endpoint(history):
    repo, (floor, accepted, tip) = history
    git(repo, "config", "submodule.vendor.ignore", "all")
    (repo / ".gitmodules").write_text('[submodule "vendor"]\n path = vendor\n url = ./vendor\n')
    git(repo, "add", ".gitmodules")
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{accepted},vendor")
    git(repo, "commit", "-m", "test: 原 gitlink")
    old = git(repo, "rev-parse", "HEAD").stdout.strip()
    catchup, _, _ = paths(repo, "release/1.0.0")
    write_json(catchup, {"completed_head": old})
    git(repo, "reset", "--soft", tip)
    git(repo, "update-index", "--cacheinfo", f"160000,{floor},vendor")
    git(repo, "commit", "-m", "test: 不同 gitlink")
    new = git(repo, "rev-parse", "HEAD").stdout.strip()
    assert not git(repo, "diff", old, new).stdout
    remap(repo, "release/1.0.0", old, [new], [old])
    assert json.loads(catchup.read_text())["completed_head"] == old
