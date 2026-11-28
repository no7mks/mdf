"""验证声明输入：文档路径也可能是实现、测试或项目规则。"""
from mdf_core.execution.modules import load_modules, match
from mdf_core.execution.verification import FIXED_INPUTS, LOCKFILES, SUITES
from mdf_core.foundation.paths import load_manifest


def input_patterns(repo, config=None):
    config = config or load_modules(repo)
    patterns = set(FIXED_INPUTS) | {"AGENTS.md"}
    patterns.update(value for value in (load_manifest(repo).get("rules") or {}).values() if isinstance(value, str))
    for module in config.modules.values():
        patterns.update((*module.sourceset, *module.extra_inputs))
        for suite in SUITES:
            entry = module.suite(suite)
            patterns.update((*entry.tests, *entry.extra_inputs))
    return {pattern.removeprefix("./") for pattern in patterns}


def is_input(path, patterns):
    name = path.rsplit("/", 1)[-1]
    return (any(match(path, pattern) for pattern in patterns) or name in LOCKFILES
            or (name.startswith("requirements") and name.endswith(".txt")))


def document_path(path):
    return path.startswith(("docs/", "changes/")) or ("/" not in path and path.endswith(".md"))
