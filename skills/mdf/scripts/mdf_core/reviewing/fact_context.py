"""固定 commit 的事实审阅 context；临时 snapshot 不执行仓库代码或过滤器。"""
import subprocess
import posixpath
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from mdf_core.execution.modules import parse_modules
from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.yamlutil import parse_yaml, read_frontmatter
from mdf_core.inspection.audit import audit_payload
from mdf_core.inspection.code_size import is_source
from mdf_core.inspection.validate_evidence import fact_documents, frontmatter_evidence
from mdf_core.reviewing.context import blob, fingerprint
from mdf_core.workspace.merge_policy import git, manifest_at, paths, sha


def snapshot(repo, ref, destination):
    """独立 index/HEAD + 只读共享对象；不用 checkout/archive，不触发 hooks 或 filters。"""
    destination.mkdir()
    object_format = git(repo, 'rev-parse', '--show-object-format').stdout.strip()
    git(destination, 'init', '--quiet', '--template=', '--object-format=' + object_format)
    git(destination, 'config', 'core.fsmonitor', 'false')
    git(destination, 'config', 'core.hooksPath', '/dev/null')
    info = destination / '.git/info'
    info.mkdir(exist_ok=True)
    (info / 'attributes').write_text('* -filter -diff -text -ident -working-tree-encoding\n')
    objects = git(repo, 'rev-parse', '--git-path', 'objects').stdout.strip()
    objects = (repo / objects).resolve()
    (destination / '.git/objects/info/alternates').write_text(str(objects) + '\n')
    shallow = repo / git(repo, 'rev-parse', '--git-path', 'shallow').stdout.strip()
    if shallow.is_file():
        (destination / '.git/shallow').write_bytes(shallow.read_bytes())
    git(destination, 'update-ref', '--no-deref', 'HEAD', ref)
    git(destination, 'read-tree', ref)
    entries = git(repo, 'ls-tree', '-rz', ref).stdout.split('\0')
    for entry in filter(None, entries):
        metadata, name = entry.split('\t', 1)
        mode, kind, oid = metadata.split()
        if (mode not in {'100644', '100755'} or kind != 'blob'
                or any(part.lower() in {'.git', '..'} for part in PurePosixPath(name).parts)
                or PurePosixPath(name).is_absolute()):
            raise MDFError(f'snapshot 不支持非普通文件或不安全路径：{name}', code='invalid_fact_snapshot')
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = subprocess.run(['git', 'cat-file', 'blob', oid], cwd=repo, capture_output=True, check=True).stdout
        path.write_bytes(data)
        path.chmod(0o755 if mode == '100755' else 0o644)


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


def fact_context(repo, source, target):
    head, policy = sha(repo, source), sha(repo, target)
    bases = git(repo, 'merge-base', '--all', head, policy, check=False).stdout.split()
    if len(bases) != 1:
        raise MDFError('source 与 target 需要唯一 merge-base', code='invalid_review_base')
    base = bases[0]
    manifest = manifest_at(repo, policy)
    modules = blob(repo, policy, '.mdf/modules.yaml')
    parse_modules(parse_yaml(modules))
    ignore_modules = blob(repo, head, '.mdf/modules.yaml')
    ignore_config = parse_modules(parse_yaml(ignore_modules))
    ignore_paths = [entry.split('\t', 1)[1] for ref in (base, head)
                    for entry in git(repo, 'ls-tree', '-rz', ref).stdout.split('\0')
                    if entry.startswith(('100644 blob ', '100755 blob '))]
    references = Path(__file__).resolve().parents[3] / 'references'
    rules = {'mdf': {name: (references / name).read_text(encoding='utf-8') for name in
                     ('fact-audit-commits.md', 'fact-audit.md', 'repository-contract.md',
                      'repository-documents.md', 'modules.md', 'doc-structure.md')},
             'manifest': manifest, 'modules': modules,
             'ignore': {'ref': head, 'modules': ignore_modules},
             'agents': blob(repo, policy, 'AGENTS.md', required=False)}
    changed = paths(repo, base, head)
    valid_rules = [(owner, rule) for owner, rule in ignore_config.all_ignore_rules()
                   if any(ignore_config.ignore_matches(p, owner, rule) for p in ignore_paths)]
    def excluded(path):
        return ignore_config.is_ignored(path) and any(
            ignore_config.ignore_matches(path, owner, rule) for owner, rule in valid_rules)

    ignored = {}
    for path in changed:
        for owner, rule in valid_rules:
            if excluded(path) and ignore_config.ignore_matches(path, owner, rule):
                ignored[path] = {'path': path, 'ignore_path': rule.pattern, 'reason': rule.reason}
                break
    review_paths = [p for p in changed if p not in ignored]
    with TemporaryDirectory(prefix='mdf-fact-') as folder:
        before, after = Path(folder).resolve() / 'base', Path(folder).resolve() / 'source'
        snapshot(repo, base, before)
        snapshot(repo, head, after)
        old, new = inventory(before), inventory(after)
        documents = sorted({p for p in old.keys() | new.keys()
                            if not excluded(p) and (p in changed or any(
                                e == '.' or c == e or c.startswith(e.rstrip('/') + '/')
                                for raw in old.get(p, []) + new.get(p, [])
                                for e in [posixpath.normpath(raw)] for c in changed))})
        roots = set()
        for ref in (base, head, policy):
            config = manifest_at(repo, ref)
            configured_roots = config.get('implementation_roots') if isinstance(config, dict) else None
            if (not isinstance(configured_roots, list) or not configured_roots
                    or any(not isinstance(r, str) or not r.strip() for r in configured_roots)):
                raise MDFError(f'{ref} 的 implementation_roots 必须为非空路径列表', code='invalid_fact_context')
            roots.update(posixpath.normpath(r) for r in configured_roots)
        implementations = sorted(p for p in review_paths if is_source(Path(p)) or
                                 any(r == '.' or p == r or p.startswith(r.rstrip('/') + '/') for r in roots))
        audit, _ = audit_payload(after, 'branch', [], [], base,
                                 extra_documents=documents, ignore_modules=ignore_config, ignore_paths=ignore_paths)
        audit.pop('repo')
        result = {'schema_version': 3, 'mode': 'commits', 'operation': 'fact-audit',
                  'review_base': base, 'review_head': head, 'policy_ref': policy, 'ignore_ref': head,
                  'paths': review_paths, 'implementation_paths': implementations, 'document_paths': documents,
                  'ignored': [ignored[p] for p in sorted(ignored)],
                  'base_mappings': old, 'source_mappings': new, 'audit': audit,
                  'rules': rules, 'rules_sha256': fingerprint(rules), 'incomplete': []}
    for key, ref in (('diff', head), ('target_diff', policy)):
        selected = review_paths if key == 'diff' else paths(repo, base, ref)
        result[key] = git(repo, 'diff', '--no-ext-diff', '--no-textconv', '--no-renames', base, ref,
                          '--', *(':(literal)' + p for p in selected)).stdout if selected else ''
    result['target_paths'] = paths(repo, base, policy)
    result['context_sha256'] = fingerprint(result)
    return result
