"""fact-audit 内容凭证：仅覆盖超集、摘要一致且语义审阅过的 pass 可被复用。"""
import json

from mdf_test_support import git, mdf, payload
from mdf_core.reviewing import fact_context as context_module, fact_identity
from test_commit_fact_audit import commit, repository
from test_fact_inputs import report_files


def reviewed(python_exe, tmp_path, repo, base):
    ctx = context_module.fact_context(repo, base)
    context_file, report_file = report_files(tmp_path, ctx)
    checked = payload(mdf(python_exe, 'fact-audit-report-check', '--repo', str(repo),
                          '--context-file', context_file, '--report-file', report_file))
    assert checked['result']['decision'] == 'pass'
    return ctx


def audit(python_exe, repo, base, *extra):
    return payload(mdf(python_exe, 'fact-audit', '--repo', str(repo), '--against', base, *extra))


def test_passed_review_is_reused_by_identical_content_even_after_history_only_commit(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    assert audit(python_exe, repo, base)['reuse'] is None
    reviewed(python_exe, tmp_path, repo, base)
    git(repo, 'commit', '--allow-empty', '-m', 'test: 仅更新历史')
    reuse = audit(python_exe, repo, base)['reuse']
    assert reuse['semantic_reviewed'] is True and reuse['scope'] == 'against'


def test_quick_never_gets_a_reusable_credential(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    reviewed(python_exe, tmp_path, repo, base)
    assert audit(python_exe, repo, base, '--quick')['reuse'] is None


def test_changed_content_or_unreviewed_semantic_credential_is_not_reused(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    ctx = reviewed(python_exe, tmp_path, repo, base)
    (repo / 'src/service.py').write_text('VALUE = 99\n')
    commit(repo)
    assert audit(python_exe, repo, base)['reuse'] is None
    # 仅机械结论（semantic_reviewed=False）的凭证不得替代语义审阅
    repo2, base2 = repository(tmp_path / 'other')
    ctx2 = context_module.fact_context(repo2, base2)
    fact_identity.record_fact_credential(repo2, ctx2, semantic_reviewed=False)
    assert audit(python_exe, repo2, base2)['reuse'] is None
    assert ctx['input_identity'] != context_module.fact_context(repo, base)['input_identity']


def test_new_warning_failure_and_force_all_miss(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    ctx = reviewed(python_exe, tmp_path, repo, base)
    assert audit(python_exe, repo, base)['reuse']['semantic_reviewed'] is True
    assert audit(python_exe, repo, base, '--force')['reuse'] is None
    fact_identity.record_fact_credential(repo, ctx, semantic_reviewed=True, decision='changes_requested')
    assert audit(python_exe, repo, base)['reuse'] is None
    fact_identity.record_fact_credential(repo, ctx, semantic_reviewed=True)
    current = fact_identity.warning_keys(ctx['audit']['warnings'])
    assert fact_identity.find_fact_credential(
        repo, ctx['input_identity'], ctx['implementation_paths'], ctx['document_paths'],
        warning_keys=[*current, 'audit.uncovered|src/extra.py']) is None


def test_credential_requires_superset_coverage(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    ctx = context_module.fact_context(repo, base)
    narrow = {**ctx, 'implementation_paths': [], 'document_paths': []}
    fact_identity.record_fact_credential(repo, narrow, semantic_reviewed=True)
    wide = ctx['implementation_paths'] + ctx['document_paths']
    found = fact_identity.find_fact_credential(repo, ctx['input_identity'], ctx['implementation_paths'],
                                               ctx['document_paths'])
    assert (found is None) == bool(wide)
