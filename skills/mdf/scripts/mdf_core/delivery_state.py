"""交付材料定位、稳定基线与内容指纹。"""
import fnmatch
import hashlib
import json
from pathlib import Path

from .errors import MDFError
from .gitutil import current_branch, run
from .paths import load_manifest, path_stays_in_repo
from .verification import manifest_items

STAGES = ("design", "write-tests", "implement", "converge", "code-review", "fact-update")


def owner_branch(branch: str) -> str:
    if branch.startswith(("qa/", "dev/")):
        owner = branch.split("/", 1)[1]
        if not owner.startswith("feature/"):
            raise MDFError("阶段操作需要 feature/qa/dev 分支",
                           code="unsupported_branch")
        return owner
    if branch.startswith("feature/"):
        return branch
    raise MDFError("阶段操作需要 feature/qa/dev 分支", code="unsupported_branch")


def role_names(owner: str) -> dict[str, str]:
    return {"qa": f"qa/{owner}", "dev": f"dev/{owner}"}


def git(repo, *args, check=True):
    return run(["git", *args], cwd=repo, check=check)


def safe(repo, path):
    path = Path(path)
    if not path.is_absolute():
        path = repo / path
    if not path_stays_in_repo(repo, path) or any(p.is_symlink() for p in (path, *path.parents)):
        raise MDFError("交付材料路径必须留在仓库内且不含符号链接", code="unsafe_path")
    return path


def read_json(path):
    try:
        value = json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        raise MDFError(f"无法读取记录: {path.name}", code="invalid_delivery") from exc
    if not isinstance(value, dict):
        raise MDFError("记录必须为 JSON 对象", code="invalid_delivery")
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    temp.replace(path)


def locate(repo, slug=None):
    branch = current_branch(repo)
    if slug is None:
        slug = owner_branch(branch).split("/", 1)[1]
    root = safe(repo, repo / "changes" / "unreleased" / slug)
    if not (root / "delivery.json").is_file():
        raise MDFError("交付记录缺失", code="invalid_delivery")
    data = read_json(safe(repo, root / "delivery.json"))
    if data.get("slug") != slug or data.get("branch") != f"feature/{slug}":
        raise MDFError("交付身份不匹配", code="invalid_delivery")
    base = data.get("start_commit", "")
    if not isinstance(base, str) or len(base) != 40 or any(c not in "0123456789abcdef" for c in base):
        raise MDFError("起点必须为完整 commit hash", code="invalid_delivery")
    if git(repo, "merge-base", "--is-ancestor", base, "HEAD", check=False).returncode:
        raise MDFError("当前分支不包含交付起点", code="invalid_delivery")
    return root, data


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def matches(path, patterns):
    return any(path == item.rstrip("/") or path.startswith(item.rstrip("/") + "/")
               or fnmatch.fnmatchcase(path, item) for item in patterns)


def inventory(repo):
    raw = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout
    result = {}
    for name in sorted(set(raw.split("\0")) - {""}):
        path = safe(repo, repo / name)
        if path.is_file():
            result[name] = digest([hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mode & 0o111])
    return result


def fingerprints(repo, root, data, config=None):
    config = config or read_json(safe(repo, root / "gates/design.json")).get("policy", {})
    files = inventory(repo)
    protected = config.get("protected_paths", [])
    commands = manifest_items(load_manifest(repo))
    facts = {name: value for name, value in files.items()
             if name == "GLOSSARY.md" or (name.endswith(".md")
                 and name.startswith(("docs/product/", "docs/system/")))}
    # 文档与 Change 材料的改动不使实现审查或全绿失效；事实文档另由 facts 覆盖。
    code = {name: value for name, value in files.items()
            if name not in facts and not name.startswith(("changes/", "docs/"))
            and not ("/" not in name and name.endswith(".md"))
            and name != ".mdf/manifest.yaml"}
    tests = {name: value for name, value in code.items() if matches(name, protected)}
    implementation = {name: value for name, value in code.items() if name not in tests}
    design = {}
    for name in ("objectives.md", "design.md"):
        path = safe(repo, root / name)
        if not path.is_file() or not path.read_text().strip():
            raise MDFError(f"缺少 {name}", code="missing_artifact")
        from .constants import ALL_MARKDOWN_LINK_RE, MARKER_RE
        from .moves import rewrite_link_raw
        from .validate_links import canonical_local_link, split_link_target
        text = path.read_text()
        if MARKER_RE.search(text):
            raise MDFError("设计材料仍含模板占位内容", code="missing_artifact")
        def normalize(match):
            raw = match.group(1)
            target = split_link_target(raw)
            canonical = canonical_local_link(repo, path, target, root)
            if canonical is None:
                return match.group(0)
            # 只改 href。str.replace 会把链接文字里的同一子串一并改掉。
            full = match.group(0)
            start = match.start(1) - match.start(0)
            end = match.end(1) - match.start(0)
            return full[:start] + rewrite_link_raw(raw, canonical) + full[end:]
        design[name] = hashlib.sha256(ALL_MARKDOWN_LINK_RE.sub(normalize, text).encode()).hexdigest()
    return {"design": digest([design, data, config]), "tests": digest([tests, commands]),
            "implementation": digest(implementation), "code": digest([code, commands]),
            "facts": digest(facts)}


def gate(repo, root, stage):
    return read_json(safe(repo, root / "gates" / f"{stage}.json"))


def require_design(repo, root, data):
    record = gate(repo, root, "design")
    current = fingerprints(repo, root, data, record.get("policy"))
    if record.get("fingerprints", {}).get("design") != current["design"]:
        raise MDFError("设计基线已变化，需用户确认后原地重新记录", code="stale_gate")
    rels = [str((root / name).relative_to(repo))
            for name in ("objectives.md", "design.md", "delivery.json", "gates/design.json")]
    if git(repo, "ls-files", "--error-unmatch", *rels, check=False).returncode:
        raise MDFError("设计基线必须提交", code="uncommitted_design")
    if git(repo, "diff", "HEAD", "--", *rels).stdout:
        raise MDFError("设计基线必须提交", code="uncommitted_design")
    return current


def require_green(repo, root, data):
    record = gate(repo, root, "verification")
    current = fingerprints(repo, root, data)
    if (any(record.get("fingerprints", {}).get(key) != current[key] for key in ("code", "design"))
            or not record.get("all_passed")):
        raise MDFError("全量验证缺失或过期", code="stale_verification")
    return current


def require_finish(repo, root, data):
    require_design(repo, root, data)
    current = require_green(repo, root, data)
    for stage, keys in (("code-review", ("code", "design")),
                        ("fact-update", ("facts", "code", "design"))):
        record = gate(repo, root, stage)
        if any(record.get("fingerprints", {}).get(key) != current[key] for key in keys):
            raise MDFError(f"{stage} 证据缺失或过期", code="stale_gate")
    return current
