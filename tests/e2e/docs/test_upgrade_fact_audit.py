"""detach 之后，仓内 Skill 副本不进入事实审阅，项目事实仍要审。"""
import json

import pytest

from mdf_test_support import copy_fixture, fact_audit_view, git, init_git, mdf, payload
from support_upgrade import source_head, write_installed


@pytest.mark.parametrize('scope', ['branch', 'full', 'paths'])
def test_pr_audit_after_detach_excludes_install_but_keeps_project_facts(python_exe, tmp_path, scope):
    repo = copy_fixture(tmp_path)
    manifest = repo / '.mdf/manifest.yaml'
    manifest.write_text(manifest.read_text().replace('implementation_roots: [src]', 'implementation_roots: [.]')
                        + 'closeout:\n  mode: pr\n  provider: github\n')
    installed = write_installed(repo, '.codex/skills', 'old MDF', 'old-revision')
    (installed / 'tool.py').write_text('VALUE = 1\n')
    document = 'docs/system/interfaces/api.md'
    doc = repo / document
    doc.write_text(doc.read_text().replace('evidence:\n', 'evidence:\n  - path: .codex/skills/mdf/tool.py\n'))
    init_git(repo)
    base = source_head(repo)
    docs = (repo / 'docs/README.md').read_text()
    mdf_manifest = (repo / '.mdf/manifest.yaml').read_text()
    detached = payload(mdf(python_exe, 'detach', '--repo', str(repo)))
    assert detached['action'] == 'created'
    assert not installed.exists()
    assert (repo / 'docs/README.md').read_text() == docs
    assert (repo / '.mdf/manifest.yaml').read_text() == mdf_manifest

    def audit():
        extra = ['--base', base] if scope == 'branch' else []
        if scope == 'paths':
            extra = ['--implementation-path', 'src/project.py', '--document-path', document]
        result = mdf(python_exe, 'fact-audit', '--repo', str(repo), '--scope', scope, *extra)
        assert result.returncode in {0, 2}
        return fact_audit_view(json.loads(result.stdout))

    data = audit()
    assert not any(p.startswith('.codex/skills/mdf/') for p in data['implementation_paths'])

    if scope == 'branch':
        (repo / 'src/project.py').write_text('VALUE = 1\n')
        doc.write_text(doc.read_text().replace('evidence:\n', 'evidence:\n  - path: src/project.py\n')
                       + '\n项目代码与 MDF 接入事实。\n')
        git(repo, 'add', '--all')
        git(repo, 'commit', '-m', 'test: 更新项目事实')
        data = audit()
        assert 'src/project.py' in data['implementation_paths']
        assert document in data['document_paths']
        assert not any(p.startswith('.codex/skills/mdf/') for p in data['implementation_paths'])
