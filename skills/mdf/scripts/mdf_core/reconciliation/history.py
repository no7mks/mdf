"""历史快照读取与未发布净增量分离；所有歧义在写入前停止。"""
import json
from pathlib import Path
from dataclasses import dataclass
import subprocess

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.yamlutil import frontmatter_span, parse_yaml
from mdf_core.reconciliation.context import metadata
from mdf_core.workspace.merge_policy import git

OUTCOMES = ("proposals", "fixed", "closed", "deferred", "adrs")


@dataclass(frozen=True)
class SnapshotFile:
    content: bytes
    mode: int = 0o644


def snapshot(value):
    return value if isinstance(value, SnapshotFile) else SnapshotFile(value.encode("utf-8"))


def read_snapshot(path):
    if path.is_symlink():
        raise MDFError("当前材料不得为 symlink", code="invalid_release_snapshot")
    return SnapshotFile(path.read_bytes(), 0o755 if path.stat().st_mode & 0o111 else 0o644)


def write_snapshot(path, value):
    entry = snapshot(value)
    mode = entry.mode if isinstance(value, SnapshotFile) or not path.exists() else read_snapshot(path).mode
    path.write_bytes(entry.content)
    path.chmod(mode)


def yaml_lines(value, indent=0):
    lines = []
    for key, item in value.items():
        prefix = " " * indent + str(key) + ":"
        if isinstance(item, dict) and item:
            lines += [prefix, *yaml_lines(item, indent + 2)]
        elif isinstance(item, list) and any(isinstance(v, dict) for v in item):
            lines.append(prefix)
            for entry in item:
                nested = yaml_lines(entry, indent + 4)
                lines += [" " * (indent + 2) + "- " + nested[0].lstrip(), *nested[1:]]
        else:
            lines.append(prefix + " " + json.dumps(item, ensure_ascii=False))
    return lines


def document(meta, body):
    return "---\n" + "\n".join(yaml_lines(meta)) + "\n---\n" + body


def tree_files(repo, ref, prefix):
    result = {}
    for row in git(repo, "ls-tree", "-r", "-z", ref, "--", prefix).stdout.split("\0"):
        if not row:
            continue
        entry, path = row.split("\t", 1)
        mode, kind, oid = entry.split()
        if mode not in {"100644", "100755"} or kind != "blob":
            raise MDFError("历史材料含 symlink 或非普通文件", code="invalid_release_snapshot")
        shown = subprocess.run(["git", "cat-file", "blob", oid], cwd=repo, capture_output=True, check=True)
        result[path] = SnapshotFile(shown.stdout, int(mode, 8) & 0o777)
    return result


def children(repo, release):
    head = release.get("release_commit") or release["head"]
    files = tree_files(repo, head, "changes")
    result = {}
    for path, text in files.items():
        parts = Path(path).parts
        if len(parts) != 4 or parts[-1] != "CHANGE.md" or parts[1] not in {"unreleased", release["version"]}:
            continue
        meta, _ = metadata(text)
        if meta.get("change_kind") not in {"feature", "bugfix", "fix", "adhoc"}:
            continue
        slug = parts[2]
        if slug in result:
            raise MDFError("历史版本中同一 slug 同时存在两份材料", code="ambiguous_release")
        prefix = str(Path(path).parent) + "/"
        result[slug] = {name[len(prefix):]: value for name, value in files.items() if name.startswith(prefix)}
    return result


def previously_archived(repo, release, slug, files):
    """既有归档和其发布快照必须同时证明同一批字节及权限。"""
    from mdf_core.foundation.textutil import stable_semver
    from mdf_core.foundation.yamlutil import read_frontmatter
    from mdf_core.workspace.merge_policy import ancestor, sha
    from mdf_core.inspection.validate_reconcile import historical_head
    for directory in (repo / "changes").iterdir():
        version = stable_semver(directory.name)
        root, archive = directory / "CHANGE.md", directory / slug
        if (version is None or version >= stable_semver(release["version"]) or not root.is_file() or not archive.is_dir()):
            continue
        meta, _ = read_frontmatter(root)
        anchor = (historical_head(repo, meta) if meta.get("record_mode") == "post_hoc"
                  else sha(repo, f"refs/tags/v{directory.name}"))
        if not ancestor(repo, anchor, release["base"]):
            continue
        actual = {p.relative_to(archive).as_posix(): read_snapshot(p) for p in archive.rglob("*") if p.is_file()}
        original = children(repo, {**release, "version": directory.name, "release_commit": anchor}).get(slug)
        if actual == files == original:
            return True
    return False


def historical_children(repo, release):
    snapshots = children(repo, release)
    if not release.get("base"):
        return snapshots
    prior = children(repo, {**release, "version": release["previous_version"], "release_commit": release["base"]})
    for slug in snapshots.keys() & prior.keys():
        if snapshots[slug] != prior[slug] or not previously_archived(repo, release, slug, prior[slug]):
            raise MDFError("同一 child 跨版本归属尚不明确，先核对已有发布记录", code="ambiguous_release", details={"slug": slug})
        del snapshots[slug]
    return snapshots


def subtract(current, archived):
    now, body = metadata(current)
    old, old_body = metadata(archived)
    allowed = {*OUTCOMES, "release_notes", "evidence"}
    if body != old_body or {k: v for k, v in now.items() if k not in allowed} != {k: v for k, v in old.items() if k not in allowed}:
        raise MDFError("历史成果与当前正文交织，不能可靠拆分；保留现场核对", code="ambiguous_release")
    for key in OUTCOMES:
        if not set(old.get(key, [])) <= set(now.get(key, [])):
            raise MDFError("当前对象归属与历史快照冲突", code="ambiguous_release")
        now[key] = [item for item in now.get(key, []) if item not in old.get(key, [])]
    old_notes = old.get("release_notes") if isinstance(old.get("release_notes"), dict) else {}
    notes = now.get("release_notes") if isinstance(now.get("release_notes"), dict) else {}
    for category, values in old_notes.items():
        if not set(values) <= set(notes.get(category, [])):
            raise MDFError("当前 release_notes 改写了历史成果", code="ambiguous_release")
    notes = {k: [v for v in values if v not in old_notes.get(k, [])] for k, values in notes.items()}
    now["release_notes"] = {k: v for k, v in notes.items() if v} or "none"
    old_evidence = old.get("evidence", {})
    for key in ("tests", "commands", "artifacts"):
        now.setdefault("evidence", {})[key] = [v for v in now.get("evidence", {}).get(key, []) if v not in old_evidence.get(key, [])]
    if now["release_notes"] == "none" and not any(now[key] for key in OUTCOMES):
        raise MDFError("内容变化无法对应尚未发布成果", code="ambiguous_release")
    outcomes = [f"- {item}" for values in now["release_notes"].values() for item in values] if isinstance(now["release_notes"], dict) else []
    body = "\n# 尚未发布的净增量\n\n## 结果\n\n" + ("\n".join(outcomes) or "参见对象 outcome。")
    body += "\n\n## 已更新的当前文档\n\n保留当前实现对应文档。\n\n## 已知偏差\n\n历史已发布成果已从本记录剔除。\n"
    return document(now, body)


def merge_increment(original, incoming):
    """尚未发布的版本追加成果时，保留既有正文、归属和 evidence。"""
    old, body = metadata(original)
    new, _ = metadata(incoming)
    old_notes = old.get("release_notes") if isinstance(old.get("release_notes"), dict) else {}
    notes = new.get("release_notes") if isinstance(new.get("release_notes"), dict) else {}
    added = []
    for category, values in old_notes.items():
        if not set(values) <= set(notes.get(category, [])):
            raise MDFError("增量说明不能丢弃既有 release_notes", code="ambiguous_release")
    for category, values in notes.items():
        added.extend(v for v in values if v not in old_notes.get(category, []))
    old["release_notes"] = notes or "none"
    old["breaking"] = old.get("breaking", False) or new.get("breaking", False)
    for key in OUTCOMES:
        old[key] = list(dict.fromkeys([*old.get(key, []), *new.get(key, [])]))
    from mdf_core.lifecycle.closeout_render import merge_evidence
    old["evidence"] = merge_evidence(old.get("evidence", {}), new.get("evidence", {}))
    if added:
        body += "\n## 增量补记\n\n" + "\n".join(f"- {v}" for v in added) + "\n"
    return document(old, body)


def plan_archive(repo, release, snapshots):
    writes, removals = {}, []
    for slug, files in snapshots.items():
        target = f"changes/{release['version']}/{slug}"
        for name, text in files.items():
            path = f"{target}/{name}"
            if (repo / path).exists() and read_snapshot(repo / path) != snapshot(text) and release["record_mode"] == "post_hoc":
                raise MDFError("目标历史材料与快照不一致", code="collision")
            writes[path] = text
        current = repo / "changes/unreleased" / slug
        if not current.exists():
            continue
        actual = {p.relative_to(current).as_posix(): read_snapshot(p) for p in current.rglob("*") if p.is_file()}
        if actual == {name: snapshot(value) for name, value in files.items()}:
            removals.extend(str(current.relative_to(repo) / name) for name in actual)
        elif "CHANGE.md" in actual:
            for name, text in files.items():
                if name != "CHANGE.md" and actual.get(name) != snapshot(text):
                    raise MDFError("交付证据已继续演进，不能可靠拆分", code="ambiguous_release")
            writes[str(current.relative_to(repo) / "CHANGE.md")] = subtract(actual["CHANGE.md"], files["CHANGE.md"])
        else:
            raise MDFError("当前未发布材料不完整", code="ambiguous_release")
    return writes, removals
