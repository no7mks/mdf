"""evidence.verification 命令与「# 」文字二选一。"""
from mdf_test_support import *  # noqa: F403


def form_error(method: str) -> str | None:
    load_core_module()
    from mdf_core.validate_evidence import verification_form_error

    return verification_form_error(method)


def test_command_and_hash_text_are_accepted():
    assert form_error("python -m pytest") is None
    assert form_error("npm run test:shared") is None
    assert form_error("# 对照路由表是否指向已有主题叶") is None
    assert form_error("  python -m pytest  ") is None


def test_empty_hash_text_and_hash_without_space_are_rejected():
    assert form_error("#") is not None
    assert form_error("# ") is not None
    assert form_error("#确认本页") is not None


def test_command_mixed_with_text_is_rejected():
    mixed = (
        "npm run test:shared；启动保留可恢复 pending 的细节在 "
        "client-persistence.md"
    )
    assert form_error(mixed) is not None
    assert form_error("python -m pytest # 读源码") is not None
    assert form_error("读取函数签名并运行 python -m pytest") is not None
