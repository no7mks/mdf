"""PR 主链普通 audit 在真实 MDF upgrade 后排除安装文件，保留项目事实。"""
import json

import pytest

from mdf_test_support import copy_fixture, git, init_git, mdf, payload
from support_upgrade import init_upstream, source_head, write_installed


@pytest.mark.parametrize('scope', ['branch', 'full', 'paths'])
def test_pr_audit_after_upgrade_excludes_install_but_keeps_project_facts(python_exe, tmp_path, scope):
    repo = copy_fixture(tmp_path)
    manifest = repo / '.mdf/manifest.yaml'
    manifest.write_text(manifest.read_text().replace('implementation_roots: [src]', 'implementation_roots: [.]')
                        + 'closeout:\n  mode: pr\n  provider: github\n')
    modules = repo / '.mdf/modules.yaml'
    modules.write_text('ignore:\n  - pattern: .codex/skills/mdf/**\n    reason: MDF 安装目录\n'
                       + modules.read_text())
    installed = write_installed(repo, '.codex/skills', 'old MDF', 'old-revision')
    (installed / 'tool.py').write_text('VALUE = 1\n')
    document = 'docs/system/interfaces/api.md'
    doc = repo / document
    doc.write_text(doc.read_text().replace('evidence:\n', 'evidence:\n  - path: .codex/skills/mdf/tool.py\n'))
    init_git(repo)
    base = source_head(repo)

    upstream = init_upstream(tmp_path, 'new MDF', agents_body='unused')
    (upstream / 'skills/mdf/tool.py').write_text('VALUE = 2\n')
    # 保持项目 AGENTS 不变，隔离真正的安装文件升级。
    agents = (repo / 'AGENTS.md').read_text()
    block = agents[agents.index('<!-- MDF:BEGIN -->'):agents.index('<!-- MDF:END -->') + len('<!-- MDF:END -->')]
    (upstream / 'skills/mdf/assets/templates/agents-managed-block.md').write_text(block)
    git(upstream, 'add', '--all')
    git(upstream, 'commit', '-m', 'test: 更新上游 MDF')
    upgraded = payload(mdf(python_exe, 'upgrade', '--repo', str(repo), '--source', str(upstream),
                           '--expected-commit', source_head(upstream)))
    assert upgraded['commit']['action'] == 'created'
    assert upgraded['agents']['action'] == 'unchanged'
    assert (repo / 'AGENTS.md').read_text() == agents
    assert (installed / 'tool.py').read_text() == 'VALUE = 2\n'
    assert source_head(repo) != base

    def audit():
        extra = ['--base', base] if scope == 'branch' else []
        if scope == 'paths':
            extra = ['--implementation-path', '.codex/skills/mdf/tool.py', '--document-path', document]
        result = mdf(python_exe, 'fact-audit', '--repo', str(repo), '--scope', scope, *extra)
        assert result.returncode in {0, 2}
        return json.loads(result.stdout)

    data = audit()
    assert not any(p.startswith('.codex/skills/mdf/') for p in data['implementation_paths'])
    assert document in data['document_paths']
    assert any(m['document'] == document and '.codex/skills/mdf/tool.py' in m['evidence'] for m in data['mappings'])
    assert any(f['code'] == 'evidence.stale' and f['path'] == document for f in data['findings'])
    assert any(row['path'] == '.codex/skills/mdf/tool.py' and row['reason'] == 'MDF 安装目录'
               for row in data['ignored'])

    if scope == 'branch':
        # 模拟 upgrade 后的项目改动：新代码与项目事实页仍须审阅。
        (repo / 'src/project.py').write_text('VALUE = 1\n')
        doc.write_text(doc.read_text().replace('evidence:\n', 'evidence:\n  - path: src/project.py\n')
                       + '\n项目代码与 MDF 接入事实。\n')
        git(repo, 'add', '--all')
        git(repo, 'commit', '-m', 'test: 更新项目事实')
        data = audit()
        assert 'src/project.py' in data['implementation_paths']
        assert document in data['document_paths']
        assert not any(p.startswith('.codex/skills/mdf/') for p in data['implementation_paths'])
        assert any(m['document'] == document and 'src/project.py' in m['evidence'] for m in data['mappings'])
