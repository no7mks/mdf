"""基线 blob 批量读取保留任意二进制内容、mode 和路径安全检查。"""
import subprocess
import sys
import tracemalloc

import pytest

from mdf_test_support import git, init_git
from mdf_core.foundation.errors import MDFError
from mdf_core.reviewing import worktree


def test_snapshot_reads_all_blobs_in_one_batch(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    contents = {'empty': b'', 'binary': b'\x00\xff\nblob\n\x00', 'duplicate': b'\x00\xff\nblob\n\x00',
                '含 空格\n文件': b'no final newline', 'executable': b'#!/bin/sh\nexit 0\n'}
    for name, data in contents.items():
        (repo / name).write_bytes(data)
    (repo / 'executable').chmod(0o755)
    init_git(repo)
    base = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    batches = []
    popen = subprocess.Popen

    def record(args, **kwargs):
        if args[-2:] == ['cat-file', '--batch']:
            batches.append(args)
        return popen(args, **kwargs)

    monkeypatch.setattr(worktree.subprocess, 'Popen', record)
    destination = tmp_path / 'snapshot'
    worktree.snapshot(repo, base, destination)
    assert batches == [['git', '--no-replace-objects', 'cat-file', '--batch']]
    for name, data in contents.items():
        assert (destination / name).read_bytes() == data
        assert bool((destination / name).stat().st_mode & 0o111) == (name == 'executable')


@pytest.mark.parametrize('response', ['missing', 'wrong-type', 'truncated', 'extra', 'failed', 'streaming-error'])
def test_snapshot_rejects_invalid_batch_response(tmp_path, monkeypatch, response):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'file').write_bytes(b'content')
    init_git(repo)
    base = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    popen = subprocess.Popen
    children = []

    def corrupt(args, **kwargs):
        if args[-2:] != ['cat-file', '--batch']:
            return popen(args, **kwargs)
        script = (
            'import sys\n'
            'oid = sys.stdin.buffer.readline().strip()\n'
            'valid = oid + b" blob 7\\ncontent\\n"\n'
            f'response = {response!r}\n'
            'data = {"missing": oid + b" missing\\n", "wrong-type": oid + b" tree 0\\n\\n",\n'
            '        "truncated": oid + b" blob 7\\nshort", "extra": valid + b"extra", "failed": valid,\n'
            '        "streaming-error": oid + b" missing\\n"}[response]\n'
            'sys.stderr.buffer.write(b"batch diagnostic\\n" * 8192)\n'
            'sys.stderr.buffer.flush()\n'
            'sys.stdout.buffer.write(data)\n'
            'sys.stdout.buffer.flush()\n'
            'if response == "streaming-error":\n'
            '    while True:\n'
            '        sys.stdout.buffer.write(b"x" * 65536)\n'
            'sys.exit(1 if response == "failed" else 0)\n'
        )
        process = popen([sys.executable, '-c', script], **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(worktree.subprocess, 'Popen', corrupt)
    with pytest.raises(MDFError, match='batch diagnostic'):
        worktree.snapshot(repo, base, tmp_path / 'snapshot')
    assert len(children) == 1 and children[0].poll() is not None


@pytest.mark.parametrize('count,size_mib', [(16, 1), (1, 16)])
def test_snapshot_memory_is_bounded_by_stream_chunks(tmp_path, count, size_mib):
    repo = tmp_path / 'repo'
    repo.mkdir()
    data = b'x' * (size_mib * 1024 * 1024)
    for index in range(count):
        (repo / f'file-{index}').write_bytes(data)
    init_git(repo)
    base = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    tracemalloc.start()
    try:
        worktree.snapshot(repo, base, tmp_path / 'snapshot')
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    print(f'baseline {count}×{size_mib} MiB, peak Python allocation {peak / 1024 / 1024:.2f} MiB')
    assert peak < 8 * 1024 * 1024, f'baseline blob 不得全量缓存，peak={peak}'
    for index in range(count):
        assert (tmp_path / 'snapshot' / f'file-{index}').read_bytes() == data
