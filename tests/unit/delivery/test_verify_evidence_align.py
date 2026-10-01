"""verify full 证据对齐：文档不伤，实现/测试/配置会伤。"""
from mdf_test_support import *  # noqa: F403


def test_affects_verification_uses_sourceset_and_suite_tests(tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    load_core_module()
    from mdf_core.module_verify import _affects_verification
    from mdf_core.modules import load_modules

    modules = load_modules(repo)
    assert _affects_verification("src/service.py", modules)
    assert _affects_verification("tests/test_x.py", modules)
    assert _affects_verification(".mdf/modules.yaml", modules)
    assert _affects_verification("changes/unreleased/bug-cd34/suites.json", modules)
    assert not _affects_verification("docs/user-guide/README.md", modules)
    assert not _affects_verification("GLOSSARY.md", modules)
    assert not _affects_verification(
        "changes/unreleased/bug-cd34/verify.full.json", modules
    )
