"""fact audit 共用依赖范围与 quick 的机械结论。"""
from pathlib import Path

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.yamlutil import read_frontmatter
from mdf_core.inspection.validate_evidence import frontmatter_evidence


def affected_documents(repo: Path, facts: set[Path], changed: list[Path]) -> set[Path]:
    """包含删除路径、目录 evidence 与 generated 依赖；无法解析的页面不能静默漏掉。"""
    documents = facts.intersection(changed)
    if not changed:
        return documents
    for document in facts:
        try:
            metadata, _ = read_frontmatter(document)
        except MDFError:
            documents.add(document)
            continue
        references = frontmatter_evidence(metadata)
        generated = metadata.get("generated")
        if isinstance(generated, dict):
            references += [value for key in ("source", "generator")
                           if isinstance(value := generated.get(key), str)]
        for raw in references:
            evidence = (repo / raw).resolve()
            if any(path == evidence or evidence in path.parents for path in changed):
                documents.add(document)
                break
    return documents


def quick_exit_code(audit):
    # quick 没有 LLM 处置 warning；任何尚待裁定的机械问题都不能表示通过。
    return 2 if audit['findings'] or audit['warnings'] else 0
