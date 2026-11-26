"""单次只读检查的 Git inventory 与 frontmatter 缓存。"""

import posixpath
import subprocess
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path, PurePosixPath

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.paths import path_stays_in_repo
from mdf_core.foundation.yamlutil import frontmatter_span, parse_yaml
from mdf_core.inspection.validate_evidence import fact_documents, frontmatter_evidence
from mdf_core.workspace.gitutil import run


def _metadata(text):
    start, end, body = frontmatter_span(text)
    return parse_yaml(text[start:end]), text[body:]


def dependencies(metadata):
    paths = frontmatter_evidence(metadata)
    generated = metadata.get("generated")
    if isinstance(generated, dict):
        paths.extend(value for key in ("source", "generator")
                     if isinstance(value := generated.get(key), str) and value.strip())
    return {posixpath.normpath(path) for path in paths}


def _with_dirs(names):
    return names | {"."} | {parent.as_posix() for name in names for parent in PurePosixPath(name).parents}


@dataclass
class RepoScanContext:
    repo: Path
    base: str | None = None
    include_ignored: bool = False
    original_tracked: set[str] | None = None

    @cached_property
    def tracked(self):
        return self._paths("ls-files", "-z")

    @cached_property
    def untracked(self):
        return self._paths("ls-files", "--others", "--exclude-standard", "-z")

    @cached_property
    def visible(self):
        return self.tracked | self.untracked

    @cached_property
    def visible_with_dirs(self):
        return _with_dirs(self.visible)

    @cached_property
    def tracked_with_dirs(self):
        return _with_dirs(self.tracked if self.original_tracked is None else self.original_tracked)

    def contains(self, path):
        return self.include_ignored or self.name(path) in self.visible_with_dirs

    def ignored_directory(self, path):
        result = run(["git", "check-ignore", "-q", "--", self.name(path) + "/"], cwd=self.repo, check=False)
        return result.returncode == 0

    @cached_property
    def changed(self):
        flags = ("--name-only", "--no-renames", "--ignore-submodules=none", "-z")
        return (self.untracked | self._paths("diff", *flags, self.base, "--")
                | self._paths("diff", "--cached", *flags, self.base, "--"))

    @cached_property
    def facts(self):
        return {path for path in fact_documents(self.repo) if self.include_ignored or self.name(path) in self.visible}

    @cached_property
    def _anchors(self):
        return {}

    def anchors(self, path):
        from mdf_core.inspection.validate_links import document_anchors
        if path not in self._anchors:
            self._anchors[path] = document_anchors(path)
        return self._anchors[path]

    @cached_property
    def _metadata_cache(self):
        return {}

    def name(self, path):
        return path.relative_to(self.repo).as_posix()

    def safe_file(self, path):
        return not path.is_symlink() and path_stays_in_repo(self.repo, path) and path.is_file()

    def frontmatter(self, path):
        if path not in self._metadata_cache:
            try:
                data = _metadata(path.read_text(encoding="utf-8"))
            except (MDFError, UnicodeError) as exc:
                data = exc
            self._metadata_cache[path] = data
        data = self._metadata_cache[path]
        if isinstance(data, Exception):
            raise data
        return data

    def _paths(self, *args):
        result = run(["git", *args], cwd=self.repo)
        return set(result.stdout.split("\0")) - {""}

    def base_frontmatter(self, changed):
        if not self.base:
            return {}
        from mdf_core.foundation.constants import FACT_ROOTS

        entries = run(["git", "ls-tree", "-rz", self.base], cwd=self.repo).stdout
        names = {}
        for entry in filter(None, entries.split("\0")):
            header, name = entry.split("\t", 1)
            mode, kind, oid = header.split()
            is_fact = name.endswith(".md") and any(name.startswith(root + "/") for root in FACT_ROOTS)
            if kind == "blob" and mode != "120000" and (is_fact or name in changed and name.endswith((".md", ".html"))):
                names[name] = oid
        if not names:
            return {}
        oids = list(dict.fromkeys(names.values()))
        result = subprocess.run(
            ["git", "cat-file", "--batch"], cwd=self.repo,
            input=("\n".join(oids) + "\n").encode(), capture_output=True,
        )
        if result.returncode:
            raise MDFError(result.stderr.decode(errors="replace"), code="command_failed")
        contents = {}
        offset = 0
        for oid in oids:
            boundary = result.stdout.index(b"\n", offset)
            header = result.stdout[offset:boundary].split()
            if len(header) != 3:
                raise MDFError(f"Git blob 读取失败：{oid}", code="command_failed")
            length = int(header[2])
            start = boundary + 1
            try:
                contents[oid] = _metadata(result.stdout[start:start + length].decode("utf-8"))[0]
            except (MDFError, UnicodeError):
                pass
            offset = start + length + 1
        return {name: contents[oid] for name, oid in names.items() if oid in contents}

    def affected_facts(self, changed, previous):
        affected = set()
        for path in self.facts:
            name = self.name(path)
            try:
                current = self.frontmatter(path)[0]
            except (MDFError, UnicodeError):
                current = {}
            refs = dependencies(current) | dependencies(previous.get(name, {}))
            if name in changed or any(ref == "." or item == ref or item.startswith(ref + "/")
                                      for ref in refs for item in changed):
                affected.add(path)
        return affected
