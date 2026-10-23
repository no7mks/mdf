"""PR 配置与 provider 归一化。"""
from types import SimpleNamespace

import pytest

from mdf_core.foundation.errors import MDFError
from mdf_core.integrations.forge import Forge, origin
from mdf_core.workspace.init_repo import render_manifest
from mdf_core.workspace.merge_policy import config


@pytest.mark.parametrize('value', [None, {}, {'mode': 'remote'}, {'mode': []}, {'mode': 'pr'},
                                 {'mode': 'pr', 'provider': []}, {'mode': 'pr', 'provider': 'other'}])
def test_invalid_closeout_is_rejected(value):
    with pytest.raises(MDFError, match='closeout'):
        config({'closeout': value})


def test_default_and_init_preserve_closeout():
    assert config({}) == {'mode': 'local'}
    from mdf_core.foundation.constants import BASELINES
    baselines = {name: {'status': 'not_applicable', 'reason': 'fixture'} for name in BASELINES}
    text = render_manifest(baselines, None, ['src'], closeout={'mode': 'pr', 'provider': 'gitlab'})
    assert 'closeout:\n  mode: pr\n  provider: gitlab' in text


@pytest.mark.parametrize('provider,url,project', [
    ('github', 'git@github.internal:team/repo.git', 'team/repo'),
    ('gitlab', 'ssh://git@gitlab.internal/team/sub/repo.git', 'team/sub/repo'),
    ('gitlab', 'ssh://git@gitlab.internal:2222/team/repo.git', 'team/repo'),
    ('gitlab', 'https://gitlab.internal/team/repo.git', 'team/repo'),
])
def test_origin_hosts_and_nested_gitlab(monkeypatch, tmp_path, provider, url, project):
    import mdf_core.integrations.forge as module
    monkeypatch.setattr(module, 'git', lambda *_: SimpleNamespace(stdout=url + '\n'))
    assert origin(tmp_path, provider)['project'] == project
    assert origin(tmp_path, provider)['host'] in {'github.internal', 'gitlab.internal'}


@pytest.mark.parametrize('provider', ['github', 'gitlab'])
def test_provider_normalizes_and_rejects_forks(tmp_path, provider):
    forge = Forge(tmp_path, {'provider': provider, 'host': 'internal', 'project': 'team/repo'})
    if provider == 'github':
        raw = {'number': 1, 'html_url': 'https://internal/team/repo/pull/1', 'state': 'closed',
               'merged_at': 'today', 'merge_commit_sha': 'merge',
               'head': {'ref': 'feature/x', 'sha': 'head', 'repo': {'full_name': 'team/repo'}},
               'base': {'ref': 'develop', 'repo': {'full_name': 'team/repo'}}}
        assert forge.normalize(raw)['state'] == 'merged'
        raw['head']['repo']['full_name'] = 'fork/repo'
    else:
        raw = {'iid': 1, 'web_url': 'https://internal/team/repo/-/merge_requests/1', 'state': 'merged',
               'source_branch': 'feature/x', 'target_branch': 'develop', 'sha': 'head',
               'merge_commit_sha': 'merge', 'source_project_id': 1, 'target_project_id': 1}
        assert forge.normalize(raw)['state'] == 'merged'
        raw['source_project_id'] = 2
    with pytest.raises(MDFError, match='同仓'):
        forge.normalize(raw)


@pytest.mark.parametrize('provider,executable', [('github', 'gh'), ('gitlab', 'glab')])
def test_provider_uses_stdin_json_and_explicit_hostname(monkeypatch, tmp_path, provider, executable):
    import json
    import mdf_core.integrations.forge as module
    calls = []
    def call(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"id":1}', stderr='')
    monkeypatch.setattr(module.subprocess, 'run', call)
    forge = Forge(tmp_path, {'provider': provider, 'host': 'internal.example', 'project': 'team/repo'})
    assert forge.api(forge.endpoint, 'POST', {'title': '含 `字面量` 的标题'}) == {'id': 1}
    command, arguments = calls[0]
    assert command[0] == executable
    assert command[command.index('--hostname') + 1] == 'internal.example'
    assert command[-2:] == ['--input', '-']
    assert json.loads(arguments['input'])['title'] == '含 `字面量` 的标题'


@pytest.mark.parametrize("patterns", [None, "docs/*", [1], [""]])
def test_invalid_trivial_patterns(patterns):
    with pytest.raises(MDFError, match="trivial_paths"):
        config({"closeout": {"mode": "local", "trivial_paths": patterns}})


def test_trivial_override_survives_manifest_render():
    from mdf_core.foundation.constants import BASELINES
    from mdf_core.foundation.yamlutil import parse_yaml
    baselines = {name: {"status": "not_applicable", "reason": "fixture"} for name in BASELINES}
    policy = {"mode": "pr", "provider": "github", "trivial_paths": ["docs/*", "AGENTS.md"]}
    assert config(parse_yaml(render_manifest(baselines, None, ["src"], closeout=policy))) == policy
