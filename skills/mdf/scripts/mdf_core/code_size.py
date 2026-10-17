"""源代码与测试源代码的文件行数硬限制，不检查配置、数据或文档。"""
from pathlib import Path
from typing import Iterable

from .errors import Finding
from .paths import relative

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
                f"源代码 {count} 行，超过限制 {MAX_CODE_LINES}；必须拆分，每个结果最多 700 行",
                relative(repo, path),
            ))
    return findings
