import os
import shutil
from pathlib import Path
from typing import Any, Callable

from .constants import ALL_MARKDOWN_LINK_RE
from .digests import text_diff
from .errors import MDFError
from .paths import path_stays_in_repo, relative
from .validate_links import split_link_target


def move_entry_for(
    path: Path, moves: dict[Path, Path]
) -> tuple[Path, Path] | None:
    resolved = path.resolve()
    for old, new in moves.items():
        old_resolved = old.resolve()
        if resolved == old_resolved or old_resolved in resolved.parents:
            return old, new
    return None


def moved_destination(path: Path, moves: dict[Path, Path]) -> Path:
    entry = move_entry_for(path, moves)
    if entry is None:
        return path
    old, new = entry
    return new / path.resolve().relative_to(old.resolve())


def fenced_code_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of fenced (```) code blocks, including fence lines."""
    spans: list[tuple[int, int]] = []
    open_start: int | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            if open_start is None:
                open_start = offset
            else:
                spans.append((open_start, offset + len(line)))
                open_start = None
        offset += len(line)
    if open_start is not None:
        spans.append((open_start, len(text)))
    return spans


def rewrite_link_raw(raw: str, rewritten_path: str) -> str:
    stripped = raw.strip()
    leading = raw[: len(raw) - len(raw.lstrip())]
    trailing = raw[len(raw.rstrip()) :]
    if stripped.startswith("<") and ">" in stripped:
        close = stripped.index(">")
        token = stripped[1:close]
        suffix_start = min(
            (
                index
                for index in (token.find("#"), token.find("?"))
                if index >= 0
            ),
            default=len(token),
        )
        suffix = token[suffix_start:]
        rest = stripped[close + 1 :]
        return f"{leading}<{rewritten_path}{suffix}>{rest}{trailing}"
    token, separator, rest = stripped.partition(" ")
    suffix_start = min(
        (index for index in (token.find("#"), token.find("?")) if index >= 0),
        default=len(token),
    )
    suffix = token[suffix_start:]
    tail = f"{separator}{rest}" if separator else ""
    return f"{leading}{rewritten_path}{suffix}{tail}{trailing}"


def replacement_plan(
    repo: Path,
    moves: dict[Path, Path],
    *,
    rewrite_inside_sources: bool = True,
    rewrite_inside_filter: Callable[[Path], bool] | None = None,
) -> dict[Path, str]:
    replacements: dict[Path, str] = {}
    text_extensions = {".md", ".yaml", ".yml"}
    for path in repo.rglob("*"):
        if (
            not path.is_file()
            or path.is_symlink()
            or not path_stays_in_repo(repo, path)
            or path.suffix.lower() not in text_extensions
        ):
            continue
        path_relative = path.relative_to(repo)
        if path_relative.parts and path_relative.parts[0] == ".git":
            continue
        if (
            not rewrite_inside_sources
            and moved_destination(path, moves) != path
        ):
            if rewrite_inside_filter is not None and not rewrite_inside_filter(
                path
            ):
                continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        fenced = fenced_code_spans(original)
        edits: list[tuple[int, int, str]] = []
        for match in ALL_MARKDOWN_LINK_RE.finditer(original):
            if any(start <= match.start() < end for start, end in fenced):
                continue
            raw = match.group(1)
            target = split_link_target(raw)
            if not target or target.startswith(
                ("http://", "https://", "mailto:", "data:")
            ):
                continue
            absolute = (
                repo / target.lstrip("/")
                if target.startswith("/")
                else path.parent / target
            ).resolve()
            source_after_move = moved_destination(path, moves)
            destination = moved_destination(absolute, moves)
            if source_after_move == path and destination == absolute:
                continue
            if (
                not rewrite_inside_sources
                and rewrite_inside_filter is None
                and source_after_move != path
                and destination != absolute
                and move_entry_for(absolute, moves)
                == move_entry_for(path, moves)
            ):
                # 链接目标随同一目录一起移动，相对路径保持有效。
                continue
            rewritten = os.path.relpath(
                destination, source_after_move.parent
            ).replace(os.sep, "/")
            new_raw = rewrite_link_raw(raw, rewritten)
            if new_raw != raw:
                edits.append((match.start(1), match.end(1), new_raw))
        if edits:
            chunks: list[str] = []
            cursor = 0
            for start, end, replacement in edits:
                chunks.append(original[cursor:start])
                chunks.append(replacement)
                cursor = end
            chunks.append(original[cursor:])
            replacements[path] = "".join(chunks)
    return replacements


def describe_moves(
    repo: Path,
    moves: dict[Path, Path],
) -> list[dict[str, Any]]:
    return [
        {
            "from": relative(repo, old),
            "to": relative(repo, new),
        }
        for old, new in sorted(moves.items())
    ]


def describe_rewrites(
    repo: Path,
    rewrites: dict[Path, str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path, content in sorted(rewrites.items()):
        before = path.read_text(encoding="utf-8")
        result.append(
            {
                "path": relative(repo, path),
                "diff": text_diff(relative(repo, path), before, content),
            }
        )
    return result


def apply_moves_and_rewrites(
    moves: dict[Path, Path], rewrites: dict[Path, str]
) -> set[Path]:
    for old, new in moves.items():
        if new.exists():
            raise MDFError(
                f"Destination already exists: {new}", code="collision"
            )
        if not old.exists():
            raise MDFError(
                f"Source does not exist: {old}", code="missing_source"
            )
    created_directories: set[Path] = set()
    for old, new in moves.items():
        candidate = new.parent
        while not candidate.exists():
            created_directories.add(candidate)
            candidate = candidate.parent
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))
    for path, content in rewrites.items():
        destination = moved_destination(path, moves)
        destination.write_text(content, encoding="utf-8")
    return created_directories


def managed_delivery_markdown(path: Path) -> bool:
    return (path.name in {"objectives.md", "design.md"}
            and (path.parent / "delivery.json").is_file())


def opaque_links_survive_move(
    repo: Path,
    source: Path,
    destination: Path,
) -> list[str]:
    broken: list[str] = []
    moves = {source: destination}
    for path in sorted(source.rglob("*.md")):
        if path.name == "CHANGE.md" or managed_delivery_markdown(path) or path.is_symlink():
            continue
        text = path.read_text(encoding="utf-8")
        for raw in ALL_MARKDOWN_LINK_RE.findall(text):
            target = split_link_target(raw)
            if not target or target.startswith(
                ("http://", "https://", "mailto:", "data:")
            ):
                continue
            absolute = (
                repo / target.lstrip("/")
                if target.startswith("/")
                else path.parent / target
            ).resolve()
            target_after = moved_destination(absolute, moves)
            source_after = moved_destination(path, moves)
            unchanged_target = (
                repo / target.lstrip("/")
                if target.startswith("/")
                else source_after.parent / target
            ).resolve()
            if unchanged_target != target_after:
                broken.append(f"{relative(repo, path)}: {raw}")
    return broken
