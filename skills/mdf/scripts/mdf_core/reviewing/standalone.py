"""独立 commit 审查：固定 Git 输入与单份 findings 报告，不依赖交付调度。"""
import json
from pathlib import Path

from mdf_core.foundation.errors import MDFError
from mdf_core.reviewing.context import blob, fingerprint
from mdf_core.reviewing.schema import check
from mdf_core.workspace.merge_policy import git, manifest_at, paths, sha


def commit_context(repo, source, target):
    head, policy = sha(repo, source), sha(repo, target)
    bases = git(repo, 'merge-base', '--all', head, policy, check=False).stdout.split()
    if len(bases) != 1:
        raise MDFError('source 与 target 需要唯一 merge-base', code='invalid_review_base')
    base = bases[0]
    manifest = manifest_at(repo, policy)
    rule = manifest.get('rules', {}).get('code-review')
    protocol = Path(__file__).resolve().parents[3] / 'references/reviewer-protocol.md'
    rules = {'mdf': protocol.read_text(encoding='utf-8'),
             'project': {'path': rule, 'content': blob(repo, policy, rule)} if rule else None,
             'agents': blob(repo, policy, 'AGENTS.md', required=False),
             'modules': blob(repo, policy, '.mdf/modules.yaml', required=False)}
    result = {'schema_version': 3, 'mode': 'commits', 'scope': 'merge',
              'review_base': base, 'merge_base': base, 'review_head': head, 'policy_ref': policy,
              'paths': paths(repo, base, head),
              'diff': git(repo, 'diff', '--no-ext-diff', '--no-textconv', '--no-renames', base, head).stdout,
              'target_paths': paths(repo, base, policy),
              'target_diff': git(repo, 'diff', '--no-ext-diff', '--no-textconv', '--no-renames', base, policy).stdout,
              'rules': rules, 'rules_sha256': fingerprint(rules), 'incomplete': []}
    result['context_sha256'] = fingerprint(result)
    return result


def validate_commit_report(context, report):
    from mdf_core.reviewing.report import require
    template = Path(__file__).resolve().parents[3] / 'assets/templates/commit-review-report.schema.json'
    check(report, json.loads(template.read_text(encoding='utf-8')))
    required = {'schema_version', 'mode', 'scope', 'review_base', 'merge_base', 'review_head', 'policy_ref',
                'paths', 'rules', 'rules_sha256', 'context_sha256', 'incomplete'}
    require(required <= set(context), 'context 缺少必需字段')
    require(not {'source', 'delivery_base', 'roster', 'artifacts'} & set(context), '独立 context 不接受交付字段')
    require(context['schema_version'] == 3 and context['scope'] == 'merge', 'context 模式无效')
    require(context['review_base'] == context['merge_base'], '独立审查必须覆盖 merge-base 起的完整范围')
    require(isinstance(context['paths'], list) and all(isinstance(p, str) for p in context['paths']), 'context paths 无效')
    require(isinstance(context['incomplete'], list), 'context incomplete 无效')
    original = {k: v for k, v in context.items() if k != 'context_sha256'}
    require(context['context_sha256'] == fingerprint(original), 'context 内容与指纹不符')
    require(context['rules_sha256'] == fingerprint(context['rules']), 'context 规则与指纹不符')
    for key in ('mode', 'review_base', 'review_head', 'policy_ref', 'rules_sha256', 'context_sha256'):
        require(report[key] == context[key], f'报告 {key} 与本轮不符')
    require(set(report['paths']) == set(context['paths']), '报告路径覆盖不完整')
    identifiers = set()
    for finding in report['findings']:
        for key in ('id', 'path', 'trigger', 'impact', 'evidence'):
            require(bool(finding[key].strip()), f'finding 需要 {key}')
        require(finding['id'] not in identifiers, 'finding id 重复')
        identifiers.add(finding['id'])
    decision = report['decision']
    if context['incomplete'] or report['incomplete']:
        require(decision in {'needs-review', 'error'}, '未完成时不能批准或拒绝')
    elif any(f['priority'] <= 1 for f in report['findings']):
        require(decision in {'changes_requested', 'needs-review', 'error'}, '阻断项不能批准')
    if decision == 'changes_requested':
        require(bool(report['findings']), 'request changes 需要 findings')
    return {'valid': True, 'decision': decision, 'review_head': context['review_head']}
