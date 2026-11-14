"""ODR 的显式范围、固定来源与实际提交覆盖检查。"""
import json
from pathlib import Path

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.delivery_state import safe, locate, write_json
from mdf_core.workspace.gitutil import ensure_clean, current_branch
from mdf_core.workspace.merge_policy import git, commit_paths


def fail(message):
    raise MDFError(message, code="invalid_release_scope")


def commit_id(repo, value):
    if not isinstance(value, str) or not value or value.startswith("-"):
        fail("来源需要有效 commit")
    result = git(repo, "rev-parse", "--verify", value + "^{commit}", check=False)
    if result.returncode:
        fail("来源 commit 不存在")
    return result.stdout.strip()


def ancestors(repo, tip, base):
    return set(git(repo, "rev-list", tip, "^" + base).stdout.split())


def ancestor(repo, base, tip):
    return git(repo, "merge-base", "--is-ancestor", base, tip, check=False).returncode == 0


def normalize(repo, entries):
    if not isinstance(entries, list):
        fail("scope 必须为数组")
    result, identifiers = [], set()
    for raw in entries:
        if not isinstance(raw, dict):
            fail("scope item 必须为对象")
        item = dict(raw)
        for key in ("id", "kind", "scope", "source"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                fail(f"scope item 缺少 {key}")
        if item["id"] in identifiers or item["kind"] not in {"branch", "cherry-pick", "direct"}:
            fail("scope id 重复或 kind 无效")
        identifiers.add(item["id"])
        if item["kind"] == "branch":
            for key in ("base", "tip"):
                item[key] = commit_id(repo, item.get(key))
            from mdf_core.lifecycle.late_decision import require_independent
            require_independent(repo, item["tip"])
            from mdf_core.workspace.workflow_policy import trunk_branch
            trunk = trunk_branch(repo)
            if not ancestor(repo, item["base"], trunk) or not ancestor(repo, item["base"], item["tip"]):
                fail(f"整分支来源必须基于 {trunk}；其他来源使用 cherry-pick")
            # 已有 MDF 材料不可通过 branch 来源绕过原契约。
            from mdf_core.workspace.gitutil import branch_details, unreleased_slug
            details = branch_details(item["source"])
            folder = unreleased_slug(details) if details["kind"] == "feature" else item["source"].rsplit("/", 1)[-1]
            if git(repo, "cat-file", "-e", f'{item["tip"]}:changes/unreleased/{folder}/delivery.json', check=False).returncode == 0:
                fail("已有 MDF delivery 材料的分支须通过 --feature 纳入")
        commits = item.get("commits", [])
        if not isinstance(commits, list):
            fail("commits 必须为数组")
        item["commits"] = [commit_id(repo, value) for value in commits]
        if item["kind"] == "cherry-pick":
            originals = item.get("originals")
            if not isinstance(originals, list) or not originals:
                fail("cherry-pick 需要解析 PR/commit 后的 originals")
            item["originals"] = [commit_id(repo, value) for value in originals]
            if commits and len(commits) != len(originals):
                fail("originals 与 commits 必须逐一对应")
        result.append(item)
    return result


def load_scope(repo, filename):
    try:
        return normalize(repo, json.loads(Path(filename).read_text()))
    except (OSError, ValueError, TypeError) as exc:
        raise MDFError("无法读取 scope JSON", code="invalid_release_scope") from exc


def update_scope(repo, filename):
    ensure_clean(repo)
    root, data = locate(repo)
    if not data.get("branch", "").startswith("on-demand-release/"):
        fail("scope 仅适用于 ODR")
    if current_branch(repo) != data["branch"]:
        fail("仅 ODR owner 可更新范围")
    entries = load_scope(repo, filename)
    if not entries and not data.get("features"):
        fail("ODR 范围不得为空")
    if entries != data.get("scope", []):
        from mdf_core.lifecycle.odr_acceptance import ACCEPTANCE
        objectives = safe(repo, root / "objectives.md")
        objectives.write_text(objectives.read_text().replace(f"- [x] {ACCEPTANCE}", f"- [ ] {ACCEPTANCE}"))
    data["scope"] = entries
    write_json(safe(repo, root / "delivery.json"), data)
    return {"scope": entries, "path": str(root / "delivery.json")}


def patch_id(repo, commit):
    patch = git(repo, "show", "--format=", "--no-ext-diff", commit).stdout
    import subprocess
    result = subprocess.run(["git", "patch-id", "--stable"], cwd=repo, input=patch,
                            text=True, capture_output=True, check=True)
    return result.stdout.split()[0] if result.stdout.strip() else None


def check_scope(repo, data, covered):
    entries = normalize(repo, data.get("scope", []))
    pending = []
    for item in entries:
        commits = set(item["commits"])
        if item["kind"] == "branch":
            commits = ancestors(repo, item["tip"], item["base"])
            included = ancestor(repo, item["tip"], "HEAD")
        else:
            included = bool(commits) and all(ancestor(repo, c, "HEAD") for c in commits)
            if item["kind"] == "direct" and included:
                first_parent = set(git(repo, "rev-list", "--first-parent", "HEAD", "^" + data["start_commit"]).stdout.split())
                if not commits <= first_parent:
                    fail("direct 只接受 ODR 首父链上的工作；外部分支使用 branch 或 cherry-pick")
        if item["kind"] == "cherry-pick" and included:
            for original, applied in zip(item["originals"], item["commits"]):
                if patch_id(repo, original) != patch_id(repo, applied):
                    # 冲突解决必须显式记录差异及复核，不假装 patch 相同。
                    if not item.get("resolution"):
                        fail("cherry-pick patch 不同，须记录 resolution 并补审补验")
        if not included:
            pending.append(item["id"])
        covered.update(commits)
    # release 材料提交由原 release 契约验收；其余提交必须有来源记录。
    version = data["branch"].split("/", 1)[1]
    material_prefixes = (f"changes/unreleased/{version}/", f"changes/{version}/",
                         *(f"changes/unreleased/{b.split('/', 1)[1]}/" for b in data.get("features", [])))
    from mdf_core.workspace.workflow_policy import trunk_branch
    covered.update(ancestors(repo, trunk_branch(repo), data["start_commit"]))
    unexpected = []
    for commit in ancestors(repo, "HEAD", data["start_commit"]) - covered:
        paths = commit_paths(repo, commit)
        if release_document_changes(repo, commit):
            paths = [p for p in paths if not p.startswith("docs/")]
        if any(not (p.startswith(material_prefixes) or p in {"CHANGELOG.md", ".mdf/manifest.yaml"}) for p in paths):
            unexpected.append(commit)
    if unexpected:
        raise MDFError("ODR 含范围外提交", code="unexpected_changes", details={"commits": sorted(unexpected)})
    return pending


def release_document_changes(repo, commit):
    """只豁免发布状态、元数据引号与归档链接重写，不豁免任意文档改动。"""
    import re
    raw = git(repo, "show", "--format=", "--remerge-diff", "--find-renames", commit, "--", "docs/").stdout
    removed, added = [], []
    object_path = False
    for line in raw.splitlines():
        if line.startswith("diff --git "):
            if removed != added:
                return False
            removed, added = [], []
            object_path = " b/docs/proposals/" in line or " b/docs/bugs/" in line
        if line.startswith(("new file mode", "deleted file mode", "old mode", "new mode", "Binary files")):
            return False
        if line.startswith("rename from "):
            renamed_from = re.sub(r"/(bugs|proposals)/archive/[^/]+/", r"/\1/", line[len("rename from "):])
        if line.startswith("rename to "):
            renamed_to = re.sub(r"/(bugs|proposals)/archive/[^/]+/", r"/\1/", line[len("rename to "):])
            if renamed_from != renamed_to:
                return False
        if line.startswith(("---", "+++")) or not line.startswith(("-", "+", " ")):
            continue
        value = line[1:]
        if object_path and re.match(r"^(status|released_in|fixed_in|found_in):", value):
            continue
        if object_path and re.match(r"^(id|type):", value):
            value = value.replace('"', "")
        value = re.sub(r"/(bugs|proposals)/archive/[^/]+/", r"/\1/", value)
        if line[0] != "-":
            added.append(value)
        if line[0] != "+":
            removed.append(value)
    return removed == added
