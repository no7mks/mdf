"""module ignore 与 sourceset 边界，跨入口复用相同匹配。"""
from pathlib import Path

import pytest

from mdf_core.execution.modules import parse_modules
from mdf_core.foundation.errors import MDFError
from mdf_core.inspection.code_size import code_size_measurements


def module(sourceset, ignore=()):
    return {'sourceset': sourceset, 'ignore': list(ignore), 'lint': 'lint', 'build': 'build',
            **{name: {'command': 'test', 'tests': ['tests/**']} for name in ('quick', 'smoke', 'release')}}


def test_module_ignore_applies_to_all_owners_and_measurements():
    rule = [{'pattern': 'vendor/**', 'reason': '第三方依赖'}]
    config = parse_modules({'modules': {'app': module(['**'], rule), 'tools': module(['vendor/**'], rule)}})
    assert config.is_ignored('vendor/tool.py')
    assert config.modules_for_paths(Path('.'), ['vendor/tool.py']) == []
    assert code_size_measurements({'vendor/tool.py': 2000}, ['vendor/tool.py'], config) == {
        'files': [], 'packages': []}


def test_module_ignore_cannot_exclude_another_modules_sources():
    config = parse_modules({'modules': {
        'app': module(['app/**'], [{'pattern': '**', 'reason': '生成文件'}]),
        'tools': module(['tools/**'])}})
    assert config.is_ignored('app/generated.py')
    assert not config.is_ignored('tools/main.py')
    assert not config.is_ignored('docs/manual.md')
    assert config.modules_for_paths(Path('.'), ['app/generated.py', 'tools/main.py']) == ['tools']
    measured = code_size_measurements({'tools/main.py': 2000}, ['tools/main.py'], config)
    assert measured['files'][0]['path'] == 'tools/main.py'


def test_shared_sources_keep_the_non_ignoring_modules_checks():
    config = parse_modules({'modules': {
        'app': module(['shared/**'], [{'pattern': '**', 'reason': '本 module 不维护'}]),
        'tools': module(['shared/**'])}})
    assert not config.is_ignored('shared/main.py')
    assert config.modules_for_paths(Path('.'), ['shared/main.py']) == ['tools']
    assert [name for name, _ in config.size_policies(['shared/main.py'])] == ['tools']


def test_shared_package_counts_respect_each_modules_ignore():
    config = parse_modules({'modules': {
        'app': module(['shared/**'], [{'pattern': 'shared/generated.py', 'reason': '生成文件'}]),
        'tools': module(['shared/**'])}})
    paths = ['shared/main.py', 'shared/generated.py']
    measured = code_size_measurements({p: 1 for p in paths}, paths, config)
    assert {(p['module'], p['value']) for p in measured['packages']} == {('app', 1), ('tools', 2)}


@pytest.mark.parametrize('raw', ['vendor/**', [{}], [{'pattern': '**'}],
                               [{'pattern': '', 'reason': '依赖'}], [{'pattern': '**', 'reason': ''}]])
def test_module_ignore_requires_pattern_and_reason(raw):
    with pytest.raises(MDFError, match='module app.ignore'):
        parse_modules({'modules': {'app': {**module(['src/**']), 'ignore': raw}}})


def test_unknown_top_level_key_is_rejected():
    with pytest.raises(MDFError, match='未知键'):
        parse_modules({'ignore': [], 'modules': {'app': module(['src/**'])}})
