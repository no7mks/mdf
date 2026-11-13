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
    rules = ['.mdf/modules.yaml', '.mdf/manifest.yaml', 'AGENTS.md']
    return {'implementation_digest': fingerprint(pick(implementation)), 'facts_digest': fingerprint(pick(facts)),
            'rules_digest': fingerprint(pick(rules))}


def input_identity(repo, manifest=None):
    root = Path(__file__).resolve().parents[3]
    shallow = repo / git(repo, 'rev-parse', '--git-path', 'shallow').stdout.strip()
    manifest = file_manifest(worktree_files(repo)) if manifest is None else manifest
    return {**_digests(repo, manifest),
            'shallow_sha256': hashlib.sha256(shallow.read_bytes()).hexdigest() if shallow.is_file() else None,
            'tool_sha256': fingerprint(tool_manifest(root))}


def record_fact_credential(repo, context, *, semantic_reviewed):
    """pass 的事实审阅写入凭证；quick 仅机械，semantic_reviewed=False，永不被复用。"""
    from mdf_core.reviewing import credentials
    coverage = {'implementation_paths': sorted(context['implementation_paths']),
                'document_paths': sorted(context['document_paths'])}
    identity = context['input_identity']
    key = credentials.key_of({'identity': identity, 'scope': 'against', 'semantic': semantic_reviewed, **coverage})
    return credentials.write(repo, 'fact-audit', key, {
        'scope': 'against', 'identity': identity, **coverage, 'semantic_reviewed': semantic_reviewed,
        'decision': 'pass'})


def find_fact_credential(repo, identity, implementation_paths, document_paths):
    """仅覆盖范围超集、内容摘要全部一致且 semantic_reviewed 的 pass 凭证可复用。"""
    from mdf_core.reviewing import credentials
    for record in credentials.records(repo, 'fact-audit'):
        if (record.get('semantic_reviewed') is True and record.get('decision') == 'pass'
                and record.get('scope') == 'against' and record.get('identity') == identity
                and set(implementation_paths) <= set(record.get('implementation_paths', []))
                and set(document_paths) <= set(record.get('document_paths', []))):
            return {'key': record['key'], 'recorded_at': record['recorded_at'], 'scope': record['scope'],
                    'semantic_reviewed': True}
    return None


def check_fact_inputs(repo, context):
    require(sha(repo, context['against']) == context['against'], 'against 必须为固定完整 SHA')
    require(context.get('input_identity') == input_identity(repo),
            '审阅输入身份已变化（shallow 或 MDF 文件），须重新生成 context 并审阅')
    require(context['worktree_sha256'] == fingerprint(file_manifest(worktree_files(repo))),
            '工作区文件已变化，须重新生成 context 并审阅')
