"""事实审阅输入身份：轻量复核不重建 snapshot 或执行 audit。"""
import hashlib
from pathlib import Path

from mdf_core.reviewing.context import fingerprint
from mdf_core.reviewing.report import require
from mdf_core.reviewing.worktree import file_manifest, git, sha, worktree_files


def tool_manifest(root):
    paths = set((root / 'scripts').rglob('*.py'))
    for directory in ('references', 'assets'):
        paths.update(p for p in (root / directory).rglob('*') if p.is_file())
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def _digests(repo, manifest):
    """实现、事实页与规则三类内容摘要；与 HEAD SHA、未被引用的 changes/** 解耦。"""
    from mdf_core.execution.modules import load_modules
    from mdf_core.inspection.validate_evidence import fact_documents
    from mdf_core.reviewing.scope import review_document
    config = load_modules(repo)
    pick = lambda names: {n: manifest[n]['sha256'] for n in sorted(names) if n in manifest}
    implementation = [n for n in manifest if config.owns(n) and not review_document(n) and not config.is_ignored(n)]
    facts = [p.relative_to(repo).as_posix() for p in fact_documents(repo)]
    from mdf_core.foundation.paths import load_manifest
    rules = ['.mdf/modules.yaml', '.mdf/manifest.yaml', 'AGENTS.md']
    for value in (load_manifest(repo).get('rules') or {}).values():
        if isinstance(value, str):
            rules.append(value)
    return {'implementation_digest': fingerprint(pick(implementation)), 'facts_digest': fingerprint(pick(facts)),
            'rules_digest': fingerprint(pick(sorted(set(rules))))}


def input_identity(repo, manifest=None):
    root = Path(__file__).resolve().parents[3]
    shallow = repo / git(repo, 'rev-parse', '--git-path', 'shallow').stdout.strip()
    manifest = file_manifest(worktree_files(repo)) if manifest is None else manifest
    return {**_digests(repo, manifest),
            'shallow_sha256': hashlib.sha256(shallow.read_bytes()).hexdigest() if shallow.is_file() else None,
            'tool_sha256': fingerprint(tool_manifest(root))}


def warning_keys(warnings):
    keys = []
    for item in warnings or []:
        if isinstance(item, dict) and isinstance(item.get('code'), str):
            keys.append(f"{item['code']}|{item.get('path') or ''}")
    return sorted(set(keys))


def record_fact_credential(repo, context, *, semantic_reviewed, decision='pass'):
    """pass 写入可复用凭证；其他结论写 failed tombstone，覆盖同 key 的旧 pass。quick 仅机械。"""
    from mdf_core.reviewing import credentials
    coverage = {'implementation_paths': sorted(context['implementation_paths']),
                'document_paths': sorted(context['document_paths'])}
    identity = context['input_identity']
    key = credentials.key_of({'identity': identity, 'scope': 'against', 'semantic': semantic_reviewed, **coverage})
    return credentials.write(repo, 'fact-audit', key, {
        'scope': 'against', 'identity': identity, **coverage, 'semantic_reviewed': semantic_reviewed,
        'decision': 'pass' if decision == 'pass' else 'failed',
        'rules_sha256': context.get('rules_sha256'),
        'warning_keys': warning_keys((context.get('audit') or {}).get('warnings'))})


def find_fact_credential(repo, identity, implementation_paths, document_paths, *, warning_keys=None, rules_sha256=None):
    """覆盖超集、摘要一致、warning 不超出已审集合，且未被 failed tombstone 吊销。"""
    from mdf_core.reviewing import credentials
    rows = credentials.records(repo, 'fact-audit')
    revoked = {record['key'] for record in rows if record.get('decision') == 'failed'}
    for record in rows:
        stored_warnings = record.get('warning_keys')
        if (record.get('key') in revoked or record.get('semantic_reviewed') is not True
                or record.get('decision') != 'pass' or record.get('scope') != 'against'
                or record.get('identity') != identity
                or not set(implementation_paths) <= set(record.get('implementation_paths', []))
                or not set(document_paths) <= set(record.get('document_paths', []))):
            continue
        if rules_sha256 is not None and record.get('rules_sha256') != rules_sha256:
            continue
        if warning_keys is not None and (not isinstance(stored_warnings, list)
                                         or not set(warning_keys) <= set(stored_warnings)):
            continue
        return {'key': record['key'], 'recorded_at': record['recorded_at'], 'scope': record['scope'],
                'semantic_reviewed': True}
    return None


def check_fact_inputs(repo, context):
    require(sha(repo, context['against']) == context['against'], 'against 必须为固定完整 SHA')
    require(context.get('input_identity') == input_identity(repo),
            '审阅输入身份已变化（shallow 或 MDF 文件），须重新生成 context 并审阅')
    require(context['worktree_sha256'] == fingerprint(file_manifest(worktree_files(repo))),
            '工作区文件已变化，须重新生成 context 并审阅')
