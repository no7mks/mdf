"""pm/reconcile-* 的逐提交文档边界；manifest 仅可更新 latest_release。"""
import re

from mdf_core.execution.modules import parse_modules
from mdf_core.execution.verification_inputs import input_patterns, is_input
from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.yamlutil import parse_yaml
from mdf_core.workspace.merge_policy import git, paths

MANIFEST = ".mdf/manifest.yaml"


def is_reconcile(source):
    return bool(re.fullmatch(r"pm/reconcile-[a-z0-9][a-z0-9.-]*", source))


def allowed(path):
    return path.startswith(("docs/", "changes/")) or path in {"CHANGELOG.md", "GLOSSARY.md", "README.md", "PROJECT.md"}


def require_diff(repo, base, head):
    from mdf_core.execution.verification import FIXED_INPUTS, SUITES
    changed = paths(repo, base, head)
    outside = [p for p in changed if p != MANIFEST and not allowed(p)]
    for path in changed:
        modes = [git(repo, "ls-tree", ref, "--", path).stdout.split() for ref in (base, head)]
        if any(row and row[0] not in {"100644", "100755"} for row in modes):
            outside.append(path)
        if path == MANIFEST and (not all(modes) or modes[0][0] != modes[1][0]):
            outside.append(path)
    if outside:
        raise MDFError("reconcile 通道包含非文档路径", code="pm_paths_forbidden", details={"paths": outside})
    patterns = set(input_patterns(repo, include_fixed=False))
    for ref in (base, head):
        config = parse_modules(parse_yaml(git(repo, "show", f"{ref}:.mdf/modules.yaml").stdout))
        manifest = parse_yaml(git(repo, "show", f"{ref}:{MANIFEST}").stdout)
        patterns.update(v for v in (manifest.get("rules") or {}).values() if isinstance(v, str))
        for module in config.modules.values():
            patterns.update((*module.sourceset, *module.extra_inputs))
            for suite in SUITES:
                entry = module.suite(suite)
                patterns.update((*entry.tests, *entry.extra_inputs))
    patterns = {p.removeprefix("./") for p in patterns}
    outside = [p for p in changed if p != MANIFEST and is_input(p, patterns | set(FIXED_INPUTS))]
    if MANIFEST in changed:
        if is_input(MANIFEST, patterns):
            outside.append(MANIFEST)
        before, after = [parse_yaml(git(repo, "show", f"{ref}:{MANIFEST}").stdout) for ref in (base, head)]
        for value in (before, after):
            versioning = value.get("versioning")
            if not isinstance(versioning, dict):
                outside.append(MANIFEST)
            else:
                versioning.pop("latest_release", None)
        if before != after:
            outside.append(MANIFEST)
    if outside:
        raise MDFError("reconcile 通道只允许不属于验证输入的文档与 latest_release", code="pm_paths_forbidden",
                       details={"paths": sorted(set(outside))})


def require_history(repo, target, head):
    from mdf_core.workspace.merge_policy import ancestor
    base = git(repo, "merge-base", target, head).stdout.strip()
    require_diff(repo, base, head)
    for row in git(repo, "rev-list", "--parents", f"{target}..{head}").stdout.splitlines():
        commit, *parents = row.split()
        if len(parents) == 2 and ancestor(repo, parents[1], target):
            parents = parents[1:]
        for parent in parents:
            require_diff(repo, parent, commit)
