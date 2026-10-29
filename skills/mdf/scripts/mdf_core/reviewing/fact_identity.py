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


def input_identity(repo):
    root = Path(__file__).resolve().parents[3]
    shallow = repo / git(repo, 'rev-parse', '--git-path', 'shallow').stdout.strip()
    return {'head': sha(repo, 'HEAD'),
            'shallow_sha256': hashlib.sha256(shallow.read_bytes()).hexdigest() if shallow.is_file() else None,
            'tool_sha256': fingerprint(tool_manifest(root))}


def check_fact_inputs(repo, context):
    require(sha(repo, context['against']) == context['against'], 'against 必须为固定完整 SHA')
    require(context.get('input_identity') == input_identity(repo),
            '审阅输入身份已变化（HEAD、shallow 或 MDF 文件），须重新生成 context 并审阅')
    require(context['worktree_sha256'] == fingerprint(file_manifest(worktree_files(repo))),
            '工作区文件已变化，须重新生成 context 并审阅')
