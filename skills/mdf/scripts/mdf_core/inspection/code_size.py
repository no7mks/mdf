"""源代码与测试源代码的文件行数硬限制，不检查配置、数据或文档。"""
from collections import Counter
from pathlib import Path
from typing import Iterable

from mdf_core.foundation.errors import Finding
from mdf_core.foundation.paths import relative

MAX_CODE_LINES = 1000
SOURCE_SUFFIXES = {
    ".py", ".pyi", ".sh", ".bash", ".zsh", ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte", ".go", ".rs", ".java",
    ".kt", ".kts", ".scala", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp",
    ".cs", ".fs", ".fsx", ".vb", ".swift", ".m", ".mm", ".rb", ".php",
    ".pl", ".pm", ".r", ".lua", ".ex", ".exs", ".erl", ".hrl", ".hs",
    ".dart", ".clj", ".cljs", ".cljc", ".groovy", ".jl", ".sql",
    ".css", ".scss", ".sass", ".less",
}


def is_source(path: Path) -> bool:
    return path.suffix.lower() in SOURCE_SUFFIXES


def code_size_findings(repo: Path, paths: Iterable[Path]) -> list[Finding]:
    findings = []
    for path in sorted(set(paths)):
        if not is_source(path) or not path.is_file() or path.is_symlink():
            continue
        count = len(path.read_text(encoding="utf-8").splitlines())
        if count > MAX_CODE_LINES:
            findings.append(Finding(
                "code.size",
                f"源代码 {count} 行，超过限制 {MAX_CODE_LINES}；必须按职责与设计模式拆分，每个结果最多 700 行",
                relative(repo, path),
            ))
    return findings


MAX_PACKAGE_FILES = 50


def is_test_source(path: Path) -> bool:
    return (bool({"test", "tests", "__tests__"}.intersection(path.parts[:-1]))
            or path.name.startswith("test_")
            or path.stem.endswith(("_test", "Test", "Tests"))
            or ".test." in path.name or ".spec." in path.name)


def package_size_findings(repo: Path, paths: Iterable[Path], *,
                          scope_paths: Iterable[Path] | None = None) -> list[Finding]:
    """按目录统计直属成员，源码和测试分别计数；范围内触及一个成员即检查完整 package。"""
    touched = None if scope_paths is None else {path.parent for path in scope_paths if is_source(path)}
    counts = Counter((path.parent, is_test_source(path.relative_to(repo))) for path in set(paths)
                     if is_source(path) and path.is_file() and not path.is_symlink()
                     and (touched is None or path.parent in touched))
    return [Finding("package.size",
                    f"package 的{'测试' if tests else '实现'}文件 {count} 个，超过 {MAX_PACKAGE_FILES}；"
                    "必须按职责与设计模式拆分，每个结果同类直属文件最多 35 个",
                    relative(repo, package))
            for (package, tests), count in sorted(counts.items()) if count > MAX_PACKAGE_FILES]
