from pathlib import Path

from .constants import EPOCH_RE
from .errors import MDFError, serialize_findings
from .moves import replacement_plan, managed_delivery_markdown
from .paths import relative
from .textutil import slugify
from .validate_change_schema import validate_change_file
from .validate_objects import iter_object_files
from .yamlutil import read_frontmatter


def archive_plan(
    repo: Path, epoch: str
) -> tuple[dict[Path, Path], dict[Path, str]]:
    if not EPOCH_RE.fullmatch(epoch):
        raise MDFError("Archive epoch must be MAJOR.MINOR", code="bad_epoch")
    moves: dict[Path, Path] = {}
    records: dict[str, tuple[Path, dict[str, Any]]] = {}
    for kind, directory in (("proposal", "proposals"), ("bug", "bugs")):
        for path in iter_object_files(repo, kind):
            records_path_parts = path.relative_to(repo).parts
            try:
                metadata, _ = read_frontmatter(path)
            except MDFError as exc:
                raise MDFError(
                    "Cannot archive invalid object "
                    f"{relative(repo, path)}: {exc}",
                    code="invalid_object",
                ) from exc
            identifier = metadata.get("id")
            if isinstance(identifier, str):
                records[identifier] = (path, metadata)
            if len(records_path_parts) != 2:
                continue
            allowed_statuses = (
                {"released", "replaced", "rejected"}
                if kind == "proposal" else {"closed", "rejected"}
            )
            if metadata.get("status") not in allowed_statuses:
                continue
            root = repo / directory
            target = root / "archive" / epoch / path.name
            if target.exists():
                raise MDFError(
                    "Archive destination already exists: "
                    f"{relative(repo, target)}",
                    code="collision",
                )
            moves[path] = target
    # A duplicate is an archive-group member, never an independent record.
    # The canonical Bug must already be closed; otherwise closeout/audit must
    # stop instead of silently splitting the group across archive epochs.
    for path, metadata in list(records.values()):
        if (
            metadata.get("type") != "bug"
            or metadata.get("status") != "rejected"
            or metadata.get("reject-reason") != "duplicate"
        ):
            continue
        primary_id = metadata.get("duplicate_of")
        primary = (
            records.get(primary_id) if isinstance(primary_id, str) else None
        )
        if primary is None:
            continue
        primary_path, primary_metadata = primary
        if primary_metadata.get("status") not in {"closed", "rejected"}:
            raise MDFError(
                "Duplicate archive group is not closed: "
                f"{relative(repo, primary_path)}",
                code="duplicate_group_open",
            )
        primary_parts = primary_path.relative_to(repo).parts
        group_epoch = (
            primary_parts[2]
            if len(primary_parts) == 4 and primary_parts[1] == "archive"
            else epoch
        )
        if len(primary_parts) == 2:
            target = repo / "bugs" / "archive" / group_epoch / primary_path.name
            if target.exists() and primary_path not in moves:
                raise MDFError(
                    "Archive destination already exists: "
                    f"{relative(repo, target)}",
                    code="collision",
                )
            moves.setdefault(primary_path, target)
        if len(path.relative_to(repo).parts) == 2:
            target = repo / "bugs" / "archive" / group_epoch / path.name
            if target.exists() and path not in moves:
                raise MDFError(
                    "Archive destination already exists: "
                    f"{relative(repo, target)}",
                    code="collision",
                )
            moves[path] = target
    rewrites = replacement_plan(repo, moves)
    return moves, rewrites


def change_move_plan(
    repo: Path, source: Path | None, branch_slug: str
) -> tuple[dict[Path, Path], dict[Path, str], Path]:
    slug = slugify(branch_slug)
    target = repo / "changes" / "unreleased" / slug
    moves: dict[Path, Path] = {}
    if target.exists():
        if source is None or source.resolve() != target.resolve():
            raise MDFError(
                f"Change directory already exists: {target}", code="collision"
            )
    elif source is not None:
        source = source.expanduser().resolve()
        try:
            source.relative_to(repo)
        except ValueError as exc:
            raise MDFError("源路径必须位于仓库内", code="outside_repo") from exc
        if not source.is_dir():
            raise MDFError(f"源目录不存在: {source}", code="missing_source")
        try:
            source_slug = slugify(source.name)
        except MDFError as exc:
            raise MDFError(
                "Source directory has no valid branch slug",
                code="source_slug",
            ) from exc
        if source_slug != slug:
            raise MDFError(
                "Source path does not match the requested branch slug",
                code="source_slug",
                details={"expected": slug, "actual": source_slug},
            )
        source_symlinks = sorted(
            path for path in source.rglob("*") if path.is_symlink()
        )
        if source_symlinks:
            raise MDFError(
                "External planning source contains symbolic links",
                code="source_symlink",
                details={
                    "paths": [
                        path.relative_to(repo).as_posix()
                        for path in source_symlinks
                    ]
                },
            )
        reserved_change = source / "CHANGE.md"
        if reserved_change.exists():
            reserved_findings: list[Finding] = []
            validate_change_file(
                repo,
                reserved_change,
                reserved_findings,
                expected_slug=slug,
            )
            if reserved_findings:
                raise MDFError(
                    "Source contains a non-canonical file at reserved name "
                    "CHANGE.md",
                    code="reserved_change",
                    details={"findings": serialize_findings(reserved_findings)},
                )
        if source == target or source in target.parents:
            raise MDFError(
                "Source cannot contain the target change directory",
                code="recursive_move",
            )
        moves[source] = target
    rewrites = replacement_plan(
        repo, moves, rewrite_inside_sources=False,
        rewrite_inside_filter=(managed_delivery_markdown
                               if source and (source / "delivery.json").is_file() else None),
    )
    return moves, rewrites, target
