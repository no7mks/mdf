"""against → 当前工作区的事实审阅 context（允许 dirty）。"""
import posixpath
from pathlib import Path
from tempfile import TemporaryDirectory

from mdf_core.execution.modules import parse_modules
from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.yamlutil import parse_yaml, read_frontmatter
from mdf_core.inspection.audit import audit_payload
from mdf_core.inspection.validate_evidence import fact_documents, frontmatter_evidence
from mdf_core.reviewing.context import fingerprint
from mdf_core.reviewing.fact_identity import input_identity
from mdf_core.reviewing.policy import current_policy
from mdf_core.reviewing.scope import review_document, selected_diff
from mdf_core.reviewing.worktree import git, sha, snapshot, working_snapshot


def inventory(repo):
    result = {}
    for path in fact_documents(repo):
        try:
            metadata, _ = read_frontmatter(path)
            dependencies = frontmatter_evidence(metadata)
            generated = metadata.get('generated')
            if isinstance(generated, dict):
                dependencies += [generated[key] for key in ('source', 'generator')
                                 if isinstance(generated.get(key), str) and generated[key].strip()]
            result[path.relative_to(repo).as_posix()] = sorted(set(dependencies))
        except MDFError:
            # 确定性 validation 报告格式错误；仍将该页纳入候选。
            result[path.relative_to(repo).as_posix()] = []
    return result


def fact_context(repo, against, *, include_index=False):
    base = sha(repo, against)
    identity = input_identity(repo)
    with TemporaryDirectory(prefix='mdf-fact-') as folder:
        before, after = Path(folder).resolve() / 'base', Path(folder).resolve() / 'worktree'
        snapshot(repo, base, before)
        files = working_snapshot(repo, after)
        local = current_policy(after)
        config = parse_modules(parse_yaml(local['modules']))
        references = Path(__file__).resolve().parents[3] / 'references'
        rules = {**local, 'mdf': {name: (references / name).read_text(encoding='utf-8') for name in
                 ('fact-audit-against.md', 'fact-audit-delivery.md', 'fact-audit.md', 'repository-contract.md',
                  'repository-documents.md', 'modules.md', 'doc-structure.md')}}
        changed = git(after, 'diff', '--no-renames', '--name-only', '-z', base, '--').stdout.split('\0')
        changed = [p for p in changed if p]
        if include_index:
            from mdf_core.workspace.clear_commits import changed_paths

            changed = sorted(set(changed) | changed_paths(repo, base, dirty=True))
        validation_paths = sorted(set(files) | set(
            git(before, 'ls-tree', '-rz', '--name-only', base).stdout.split('\0')) - {''})
        ignored = {}
        for path in changed:
            for owner, rule in config.all_ignore_rules():
                if config.is_ignored(path) and config.ignore_matches(path, owner, rule):
                    ignored[path] = {'path': path, 'ignore_path': rule.pattern, 'reason': rule.reason}
                    break
        implementations = [p for p in changed if config.owns(p) and not review_document(p) and p not in ignored]
        review_paths = [p for p in changed if (p in implementations or review_document(p)) and p not in ignored]
        old, new = inventory(before), inventory(after)
        documents = sorted({p for p in old.keys() | new.keys()
                            if not config.is_ignored(p) and (p in changed or any(
                                e == '.' or c == e or c.startswith(e.rstrip('/') + '/')
                                for raw in old.get(p, []) + new.get(p, [])
                                for e in [posixpath.normpath(raw)] for c in changed if c not in ignored))})
        audit, _ = audit_payload(after, 'branch', [], [], base,
                                 extra_documents=documents, ignore_modules=config, ignore_paths=validation_paths,
                                 scope_changes=[p for p in changed if config.owns(p) or review_document(p)])
        audit.pop('repo')
        result = {'schema_version': 3, 'mode': 'against', 'operation': 'fact-audit',
                  'against': base, 'worktree_sha256': fingerprint(files), 'input_identity': identity,
                  'paths': review_paths, 'implementation_paths': implementations, 'document_paths': documents,
                  'ignored': [ignored[p] for p in sorted(ignored)],
                  'base_mappings': old, 'worktree_mappings': new, 'audit': audit,
                  'diff': selected_diff(after, base, None, review_paths),
                  'rules': rules, 'rules_sha256': fingerprint(rules), 'incomplete': []}
        if include_index:
            result['staged_diff'] = git(repo, 'diff', '--cached', '--no-ext-diff', '--no-textconv',
                                        '--no-renames', '--binary', '--').stdout
    result['context_sha256'] = fingerprint(result)
    return result
