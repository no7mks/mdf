"""roster 冻结的默认值与取值约束。"""
from mdf_test_support import *  # noqa: F403


def frozen(qa, dev, reviewers, **extra):
    body = {
        "qa": qa,
        "dev": dev,
        "reviewers": reviewers,
        "qa_strategy": "best-of-n",
        "dev_strategy": "best-of-n",
        "review_strategy": "replicate",
    }
    body.update(extra)
    return body


def test_freeze_roster_defaults_and_coercion():
    load_core_module()
    from mdf_core.foundation.errors import MDFError
    from mdf_core.lifecycle.roster import freeze_roster, merge_branches, role_branch, require_roster
    assert freeze_roster("feature") == frozen(1, 1, 2)
    assert freeze_roster("bugfix") == frozen(0, 0, 1)
    assert freeze_roster("release") == frozen(0, 0, 3, review_strategy="partition")
    assert freeze_roster("release", named="solo") == frozen(0, 0, 1)
    assert freeze_roster("release", reviewers=2, review_strategy="replicate") == frozen(0, 0, 2)
    assert freeze_roster("hotfix") == frozen(0, 0, 1)
    assert freeze_roster("feature", 0, 0, 2) == frozen(0, 0, 2)
    assert freeze_roster("feature", 0, 2, None) == frozen(1, 2, 2)
    assert freeze_roster("bugfix", 2, 0, 4) == frozen(2, 1, 4)
    assert freeze_roster("feature", named="solo") == frozen(0, 0, 1)
    assert freeze_roster("bugfix", named="min-tdd") == frozen(1, 1, 2)
    assert freeze_roster("feature", named="competing-pair") == frozen(2, 2, 3)
    assert freeze_roster("feature", named="coop-pair") == frozen(
        2, 2, 3, qa_strategy="partition", dev_strategy="partition",
    )
    assert freeze_roster("feature", 3, named="competing-pair") == frozen(3, 2, 3)
    with pytest.raises(MDFError, match="roster 名必须是"):
        freeze_roster("feature", named="squad")
    assert role_branch("qa", "feature/foo", 1) == "qa/feature/foo"
    assert role_branch("qa", "feature/foo", 2) == "qa/2/feature/foo"
    with pytest.raises(MDFError, match="至少为 1"):
        freeze_roster("feature", 1, 1, 0)
    with pytest.raises(MDFError, match="同时为 0"):
        require_roster(frozen(0, 1, 3))
    with pytest.raises(MDFError, match="策略字段"):
        require_roster({"qa": 1, "dev": 1, "reviewers": 3})
    with pytest.raises(MDFError, match="qa_strategy"):
        freeze_roster("feature", qa_strategy="compete")
    assert freeze_roster(
        "feature", models={"code-review": "opus"},
    ) == frozen(1, 1, 2, models={"code-review": "opus"})
    assert freeze_roster(
        "feature", models={"code-review": "opus 和 sonnet"},
    ) == frozen(1, 1, 2, models={"code-review": "opus 和 sonnet"})
    with pytest.raises(MDFError, match="按 intent"):
        require_roster(frozen(1, 1, 3, models="opus"))
    with pytest.raises(MDFError, match="只接受"):
        require_roster(frozen(1, 1, 3, models={"qa": "opus"}))
    roster = frozen(1, 2, 3, dev_strategy="partition")
    assert merge_branches("dev", "feature/foo", roster, None) == [
        "dev/feature/foo", "dev/2/feature/foo",
    ]
    with pytest.raises(MDFError, match="不要传 winner"):
        merge_branches("dev", "feature/foo", roster, "dev/feature/foo")
