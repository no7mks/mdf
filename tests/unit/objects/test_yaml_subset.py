"""MDF 使用的 YAML 子集解析。"""
import random
import string

from mdf_test_support import *  # noqa: F403


def core():
    load_core_module()
    from mdf_core import yamlutil
    from mdf_core.errors import MDFError
    return yamlutil, MDFError


def test_nested_maps_lists_and_scalars():
    yamlutil, _ = core()
    text = (
        "a: 1\n"
        "b: null\n"
        "c: [x, \"y z\", 3]\n"
        "d:\n"
        "  e: true\n"
        "  f:\n"
        "    - g: 1\n"
        "      h: two\n"
        "    - plain\n"
        "i: 'single' # 注释\n"
    )
    assert yamlutil.parse_yaml_subset(text) == {
        "a": 1, "b": None, "c": ["x", "y z", 3],
        "d": {"e": True, "f": [{"g": 1, "h": "two"}, "plain"]},
        "i": "single",
    }


@pytest.mark.parametrize("text", ["a:\n\t- x\n", "- orphan\n", "just text\n"])
def test_malformed_yaml_is_rejected(text):
    yamlutil, MDFError = core()
    with pytest.raises(MDFError) as error:
        yamlutil.parse_yaml_subset(text)
    assert error.value.code == "invalid_yaml"


def test_quoted_values_round_trip():
    """PT：不含控制字符的任意文本经 yaml_quote 写出后按原值读回。"""
    yamlutil, _ = core()
    alphabet = string.ascii_letters + string.digits + string.punctuation + " 中文é"
    rng = random.Random(20260927)
    for _ in range(2000):
        value = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 16)))
        parsed = yamlutil.parse_yaml_subset(f"k: {yamlutil.yaml_quote(value)}\n")
        assert parsed["k"] == value, value
