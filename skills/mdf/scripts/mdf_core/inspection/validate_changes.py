import re
from pathlib import Path

from mdf_core.foundation.errors import Finding, MDFError, add_finding
from mdf_core.foundation.paths import path_stays_in_repo, relative
from mdf_core.foundation.textutil import stable_semver
from mdf_core.inspection.validate_change_schema import validate_change_file, validate_version_change_file
from mdf_core.foundation.yamlutil import read_frontmatter


def validate_changes(repo: Path, findings: list[Finding], *, paths: set[Path] | None = None, scan=None) -> None:
    root = repo / "changes"
    if (
        not root.is_dir()
        or root.is_symlink()
        or not path_stays_in_repo(repo, root)
    ):
        return
    def present(path):
        return path.is_file() and (scan is None or scan.contains(path))

    def included(path):
        return scan is None or scan.contains(path) or not scan.ignored_directory(path)

    for directory in sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and included(path)
        and not path.is_symlink()
        and path_stays_in_repo(repo, path)
    ):
        if paths is not None and not any(p == directory or directory in p.parents for p in paths):
            continue
        if directory.name == "unreleased":
            for change_dir in sorted(
                path
                for path in directory.iterdir()
                if path.is_dir() and included(path)
                and not path.is_symlink()
                and path_stays_in_repo(repo, path)
            ):
                if paths is not None and not any(p == change_dir or change_dir in p.parents for p in paths):
                    continue
                semver = stable_semver(change_dir.name) is not None
                if not semver and not re.fullmatch(
                    r"[a-z0-9][a-z0-9-]*", change_dir.name
                ):
                    add_finding(
                        findings,
                        "change.directory",
                        "Unreleased change directory must be an ASCII "
                        "kebab-case slug or stable SemVer",
                        relative(repo, change_dir),
                    )
                    continue
                review = change_dir / "code-review.md"
                if semver:
                    identity = change_dir / "delivery.json"
                    if not present(identity) and not present(review):
                        add_finding(
                            findings,
                            "change.missing",
                            "release/hotfix 目录需要 delivery.json 或 "
                            "code-review.md",
                            relative(repo, change_dir),
                        )
                    continue
                change = change_dir / "CHANGE.md"
                identity = change_dir / "delivery.json"
                # start 写入身份；CHANGE.md 到 finish 才补齐。
                # bugfix 可在补齐 CHANGE.md 前先写入 code-review.md。
                if present(change):
                    validate_change_file(
                        repo,
                        change,
                        findings,
                        expected_slug=change_dir.name,
                    )
                elif not present(identity) and not present(review):
                    add_finding(
                        findings,
                        "change.missing",
                        "unreleased Change 目录需要 CHANGE.md",
                        relative(repo, change_dir),
                    )
            continue
        if stable_semver(directory.name) is None:
            add_finding(
                findings,
                "release.directory",
                "Released change directory must be a stable SemVer",
                relative(repo, directory),
            )
            continue
        release = directory / "CHANGE.md"
        if not present(release):
            add_finding(
                findings,
                "release.missing",
                "已发布版本目录需要根 CHANGE.md",
                relative(repo, directory),
            )
        else:
            validate_version_change_file(
                repo, release, findings, directory.name
            )
            try:
                root_metadata, _ = read_frontmatter(release)
            except MDFError:
                root_metadata = {}
            root_kind = root_metadata.get("change_kind")
            child_dirs = sorted(
                path.name
                for path in directory.iterdir()
                if path.is_dir() and included(path)
                and not path.is_symlink()
                and path_stays_in_repo(repo, path)
            )
            included_changes = root_metadata.get("included_changes")
            if isinstance(included_changes, list):
                if any(not isinstance(item, str) for item in included_changes):
                    add_finding(
                        findings,
                        "release.included_changes",
                        "版本根 included_changes 必须是字符串列表",
                        relative(repo, release),
                    )
                elif sorted(included_changes) != child_dirs:
                    add_finding(
                        findings,
                        "release.included_changes",
                        "版本根 included_changes 必须等于其子 Change 目录",
                        relative(repo, release),
                    )
            aggregate: dict[str, set[str]] = {
                key: set()
                for key in (
                    "proposals",
                    "fixed",
                    "closed",
                    "deferred",
                    "adrs",
                )
            }
            for child_dir in child_dirs:
                child = directory / child_dir / "CHANGE.md"
                if not present(child):
                    continue
                try:
                    child_metadata, _ = read_frontmatter(child)
                except MDFError:
                    continue
                for key in aggregate:
                    values = child_metadata.get(key)
                    if isinstance(values, list):
                        aggregate[key].update(str(value) for value in values)
            # A hotfix is a direct version-level Change: it intentionally has
            # no unreleased child slug to aggregate. Release roots must include
            # every child outcome and may supersets from release-level closures.
            if not (root_kind == "hotfix" and not child_dirs):
                for key, values in aggregate.items():
                    root_values = root_metadata.get(key)
                    if not isinstance(root_values, list):
                        if values:
                            add_finding(
                                findings,
                                "release.aggregate",
                                f"版本根 {key} 必须包含子 Change outcomes",
                                relative(repo, release),
                            )
                        continue
                    root_set = {str(value) for value in root_values}
                    if not values.issubset(root_set):
                        add_finding(
                            findings,
                            "release.aggregate",
                            f"版本根 {key} 必须覆盖全部子 Change outcome",
                            relative(repo, release),
                        )
        for change_dir in sorted(
            path
            for path in directory.iterdir()
            if path.is_dir() and included(path)
            and not path.is_symlink()
            and path_stays_in_repo(repo, path)
        ):
            change = change_dir / "CHANGE.md"
            if not present(change):
                if paths is None or release in paths or any(
                    p == change_dir or change_dir in p.parents for p in paths
                ):
                    add_finding(
                        findings,
                        "change.missing",
                        "已发布 Change 快照需要 CHANGE.md",
                        relative(repo, change_dir),
                    )
            elif paths is None or change in paths:
                validate_change_file(
                    repo,
                    change,
                    findings,
                    expected_slug=change_dir.name,
                )
