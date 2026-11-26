"""against 的影响集隔离与删除目标保护。"""
from mdf_test_support import copy_fixture, init_git, git
from mdf_core.reviewing.fact_context import fact_context
from mdf_core.inspection import strict_validation


def repository(tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    return repo


def test_unrelated_invalid_fact_is_excluded(tmp_path):
    repo = repository(tmp_path)
    bad = repo / 'docs/system/interfaces/unrelated.md'
    bad.write_text('invalid fact\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'test: 基线错误')
    base = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    (repo / 'src/service.py').write_text('changed = True\n')
    context = fact_context(repo, base)
    assert not any(f.get('path') == bad.relative_to(repo).as_posix() for f in context['audit']['findings'])
    assert any(f.path == bad.relative_to(repo).as_posix() for f in strict_validation.collect_findings(repo))


def test_incoming_anchor_and_unrelated_outgoing_link(tmp_path):
    repo = repository(tmp_path)
    source = repo / 'docs/context/research/source.md'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('[标题](target.md#old)\n[旧错误](missing.md)\n')
    target = source.with_name('target.md')
    target.write_text('# Old\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'test: 入链基线')
    base = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    target.write_text('# New\n')
    findings = fact_context(repo, base)['audit']['findings']
    broken = [f for f in findings if f['code'] == 'link.broken']
    assert len(broken) == 1 and 'target.md#old' in broken[0]['message']
    target.unlink()
    broken = [f for f in fact_context(repo, base)['audit']['findings'] if f['code'] == 'link.broken']
    assert len(broken) == 1 and 'target.md#old' in broken[0]['message']


def test_deleted_record_keeps_incoming_id_reference(tmp_path):
    repo = repository(tmp_path)
    source = repo / 'docs/bugs/bug-CD34-unreleased-timeout.md'
    reference = repo / 'changes/unreleased/example/CHANGE.md'
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text('---\nfixed: [bug-CD34]\nclosed: [bug-MISSING]\n---\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'test: 对象引用基线')
    base = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    source.unlink()
    findings = fact_context(repo, base)['audit']['findings']
    missing = [f for f in findings if f['code'] == 'change.record_missing']
    assert len(missing) == 1 and 'bug-CD34' in missing[0]['message']


def test_against_never_runs_full_doctor_and_only_registers_selected_facts(tmp_path, monkeypatch):
    from mdf_core.inspection import check_engine
    repo = repository(tmp_path)
    base = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    selected = []
    original = check_engine.validate_evidence

    def evidence(repo, findings, **kwargs):
        selected.extend(p.relative_to(repo).as_posix() for p in kwargs['documents'])
        return original(repo, findings, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError('against must not run full doctor')

    monkeypatch.setattr(check_engine, 'validate_evidence', evidence)
    monkeypatch.setattr(strict_validation, 'collect_findings', forbidden)
    doc = repo / 'docs/system/interfaces/api.md'
    doc.write_text(doc.read_text() + '\n<!-- changed -->\n')
    context = fact_context(repo, base)
    assert selected == context['document_paths'] == ['docs/system/interfaces/api.md']


def test_unmanaged_html_and_frontmatter_or_fenced_anchors(tmp_path):
    repo = repository(tmp_path)
    source = repo / 'docs/context/research/source.md'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('[伪锚点](target.md#key-value)\n[代码内锚点](target.md#fake)\n')
    target = source.with_name('target.md')
    target.write_text('---\nkey: value\n---\n```html\n<a id="fake"></a>\n```\n# Real\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'test: 锚点与非受管链接基线')
    base = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    (repo / 'src/index.html').write_text('<a href="/app">App</a>\n')
    target.write_text(target.read_text() + '\nParagraph\n')
    findings = fact_context(repo, base)['audit']['findings']
    assert not any(f['code'] == 'link.outside_repo' for f in findings)
    broken = [f['message'] for f in findings if f['code'] == 'link.broken']
    assert len(broken) == 2 and any('#key-value' in m for m in broken) and any('#fake' in m for m in broken)
