"""稳定 SemVer 解析与发布所需的版本递增。"""
import random

from mdf_test_support import *  # noqa: F403


def core():
    load_core_module()
    from mdf_core import semver, textutil
    from mdf_core.errors import MDFError
    return semver, textutil, MDFError


@pytest.mark.parametrize(("raw", "parsed"), [
    ("1.2.3", (1, 2, 3)), ("0.0.0", (0, 0, 0)),
    ("01.2.3", None), ("1.2", None), ("1.2.3-rc.1", None), ("v1.2.3", None), (None, None),
])
def test_stable_semver(raw, parsed):
    _, textutil, _ = core()
    assert textutil.stable_semver(raw) == parsed


@pytest.mark.parametrize(("categories", "breaking", "previous", "bump"), [
    (set(), False, (1, 0, 0), "patch"),
    ({"Fixed"}, False, (1, 0, 0), "patch"),
    ({"Added"}, False, (1, 0, 0), "minor"),
    ({"Removed"}, False, (1, 0, 0), "major"),
    ({"Removed"}, False, (0, 4, 0), "minor"),
    (set(), True, (2, 0, 0), "major"),
])
def test_required_bump(categories, breaking, previous, bump):
    semver, _, _ = core()
    assert semver.required_bump(previous, categories, breaking) == bump


def test_bump_kind_matches_the_highest_changed_part():
    """PT：任意递增的版本对，bump_kind 等于首个不同的位；非递增一律拒绝。"""
    semver, _, MDFError = core()
    rng = random.Random(20260927)
    for _ in range(500):
        previous = tuple(rng.randint(0, 3) for _ in range(3))
        candidate = tuple(rng.randint(0, 3) for _ in range(3))
        if candidate <= previous:
            with pytest.raises(MDFError):
                semver.bump_kind(previous, candidate)
            continue
        first = next(index for index in range(3) if candidate[index] != previous[index])
        assert semver.bump_kind(previous, candidate) == ("major", "minor", "patch")[first]
