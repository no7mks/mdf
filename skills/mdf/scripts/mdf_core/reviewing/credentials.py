"""审查/事实审阅的内容凭证：存于 Git common dir，按内容摘要匹配，不依赖 commit SHA。"""
import json
import os
import time
from pathlib import Path

from mdf_core.reviewing.context import fingerprint
from mdf_core.workspace.merge_policy import git

PROTOCOL = 1


def store(repo, kind):
    common = git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').stdout.strip()
    return Path(common) / 'mdf' / 'attestations' / kind


def write(repo, kind, key, record):
    directory = store(repo, kind)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f'{key}.{os.getpid()}.tmp'
    body = {**record, 'protocol': PROTOCOL, 'key': key, 'kind': kind,
            'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    temporary.write_text(json.dumps(body, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(directory / f'{key}.json')
    return body


def records(repo, kind):
    """当前协议版本且可解析的凭证；损坏或旧协议一律忽略。"""
    found = []
    for path in sorted(store(repo, kind).glob('*.json')):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and record.get('protocol') == PROTOCOL:
            found.append(record)
    return found


def key_of(value):
    return fingerprint(value)


def blob_ids(repo, ref, paths):
    """ref 下各路径的 blob id；ref 中不存在（已删除）记为 None。"""
    found = {}
    if paths:
        rows = git(repo, 'ls-tree', '-rz', ref, '--', *(':(literal)' + p for p in paths)).stdout.split('\0')
        for row in filter(None, rows):
            meta, name = row.split('\t', 1)
            found[name] = meta.split()[2]
    return {p: found.get(p) for p in sorted(paths)}


def requirements_digest(repo, ref, objectives, delivery):
    """objectives（忽略勾选进度）与关联 Proposal/Bug 正文的摘要。"""
    import re
    text = re.sub(r'(?m)^(\s*- )\[[xX]\]', r'\1[ ]', objectives or '')
    linked = {}
    for key, root in (('proposal', 'docs/proposals'), ('bug', 'docs/bugs')):
        identifier = delivery.get(key)
        if isinstance(identifier, str):
            names = git(repo, 'ls-tree', '-r', '--name-only', ref, '--', root, check=False).stdout.splitlines()
            for name in names:
                if name.rsplit('/', 1)[-1].startswith(identifier + '-'):
                    linked[name] = git(repo, 'rev-parse', f'{ref}:{name}').stdout.strip()
    return fingerprint({'objectives': text, 'linked': linked})


def code_identity(repo, head, paths, rules_sha256, objectives, delivery):
    files = blob_ids(repo, head, paths)
    base = {'code_digest': fingerprint(files), 'rules_sha256': rules_sha256,
            'requirements_digest': requirements_digest(repo, head, objectives, delivery), 'paths': sorted(paths)}
    return {**base, 'key': key_of(base), 'files': files}


def reuse_analysis(repo, source, identity, config):
    """release 复用子交付 code-review 证据；净增量与未覆盖组合影响面（文件或 module 接口层）均空才允许 0 reviewer。"""
    children = [r for r in records(repo, 'code-review')
                if r.get('decision') == 'pass' and r.get('source') != source
                and r.get('delivery_kind') not in {'release', 'on-demand-release'}
                and r.get('rules_sha256') == identity['rules_sha256']]
    covered = {p for p in identity['paths'] if any(
        identity['files'][p] is not None and r['files'].get(p) == identity['files'][p] for r in children)}
    net = [p for p in identity['paths'] if p not in covered]
    touched = {p: sorted({r['source'] for r in children if p in r['paths']}) for p in identity['paths']}
    combined = [p for p, sources in touched.items() if len(sources) >= 2]
    own = set(identity['paths'])
    by_source = {}
    for r in children:
        by_source.setdefault(r['source'], set()).update(set(r['paths']) & own)
    modules = {s: config.modules_for_paths(repo, sorted(paths)) for s, paths in by_source.items() if paths}
    names = sorted(modules)
    combined_modules = sorted({m for i, a in enumerate(names) for b in names[i + 1:]
                               for m in config.interacting(modules[a], modules[b])})
    return {'net_increment': net, 'combined_impact': combined, 'combined_modules': combined_modules,
            'child_credentials': sorted(r['key'] for r in children if set(r['paths']) & own),
            'zero_reviewers_allowed': not net and not combined and not combined_modules}


def confirm_code_context(repo, context):
    """写凭证前用仓库现场重算规则与代码身份；与 context 不一致则拒写。"""
    from mdf_core.foundation.errors import MDFError
    from mdf_core.reviewing.context import effective_rules
    credential = context.get('credential')
    if not isinstance(credential, dict):
        raise MDFError('context 缺少现场代码身份', code='credential_mismatch')
    if context.get('policy_ref') and context.get('review_head'):
        try:
            rules, _ = effective_rules(repo, context['policy_ref'], context['review_head'])
        except MDFError:
            rules = None
        if rules is not None and fingerprint(rules) != context.get('rules_sha256'):
            raise MDFError('context 规则与仓库现场不符', code='credential_mismatch')
    objectives, delivery = '', {}
    artifacts = context.get('artifacts') or {}
    if isinstance(artifacts, dict):
        for key, value in artifacts.items():
            if not isinstance(value, str):
                continue
            if key.endswith('/objectives.md'):
                objectives = value
            elif key.endswith('/delivery.json'):
                import json
                try:
                    delivery = json.loads(value)
                except ValueError:
                    delivery = {}
    fresh = code_identity(repo, context.get('review_head') or 'HEAD', credential.get('paths') or [],
                          credential.get('rules_sha256'), objectives, delivery if isinstance(delivery, dict) else {})
    if (fresh['key'] != credential.get('key') or fresh['code_digest'] != credential.get('code_digest')
            or fresh['rules_sha256'] != credential.get('rules_sha256')):
        raise MDFError('context 代码身份与仓库现场不符', code='credential_mismatch')


def record_code_credential(repo, context, reviewers, *, decision='pass'):
    identity = context['credential']
    stored = 'pass' if decision == 'pass' else 'failed'
    return write(repo, 'code-review', key_of({'identity': identity['key'], 'source': context['source']}), {
        'source': context['source'], 'delivery_kind': context['kind'], 'decision': stored, 'reviewers': reviewers,
        'rules_sha256': identity['rules_sha256'], 'code_digest': identity['code_digest'],
        'requirements_digest': identity['requirements_digest'], 'paths': identity['paths'],
        'files': identity['files']})
