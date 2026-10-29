"""仓外只读审阅快照：固定 against 与完整当前工作区，不修改原仓库对象或 index。"""
import hashlib
import subprocess
from pathlib import Path, PurePosixPath
from tempfile import TemporaryFile

from mdf_core.foundation.errors import MDFError
from mdf_core.workspace.merge_policy import git as repository_git


def git(repo, *args, check=True):
    """审阅固定真实 object，不解释原仓库或宿主指定的 replacement refs。"""
    return repository_git(repo, '--no-replace-objects', *args, check=check)


def sha(repo, ref):
    return git(repo, 'rev-parse', '--verify', f'{ref}^{{commit}}').stdout.strip()


def initialize(repo, ref, destination):
    """独立 index/HEAD + 只读共享对象；不用 checkout/archive，不触发 hooks 或 filters。"""
    destination.mkdir()
    object_format = git(repo, 'rev-parse', '--show-object-format').stdout.strip()
    git(destination, 'init', '--quiet', '--template=', '--object-format=' + object_format)
    git(destination, 'config', 'core.fsmonitor', 'false')
    git(destination, 'config', 'core.hooksPath', '/dev/null')
    info = destination / '.git/info'
    info.mkdir(exist_ok=True)
    (info / 'attributes').write_text('* -filter !diff -text -ident -working-tree-encoding\n')
    objects = git(repo, 'rev-parse', '--git-path', 'objects').stdout.strip()
    objects = (repo / objects).resolve()
    (destination / '.git/objects/info/alternates').write_text(str(objects) + '\n')
    shallow = repo / git(repo, 'rev-parse', '--git-path', 'shallow').stdout.strip()
    if shallow.is_file():
        (destination / '.git/shallow').write_bytes(shallow.read_bytes())
    git(destination, 'update-ref', '--no-deref', 'HEAD', ref)
    git(destination, 'read-tree', ref)


def snapshot(repo, ref, destination):
    initialize(repo, ref, destination)
    entries = git(repo, 'ls-tree', '-rz', ref).stdout.split('\0')
    selected = []
    for entry in filter(None, entries):
        metadata, name = entry.split('\t', 1)
        mode, kind, oid = metadata.split()
        if (mode not in {'100644', '100755'} or kind != 'blob'
                or any(part.lower() in {'.git', '..'} for part in PurePosixPath(name).parts)
                or PurePosixPath(name).is_absolute()):
            raise MDFError(f'snapshot 不支持非普通文件或不安全路径：{name}', code='invalid_fact_snapshot')
        selected.append((mode, oid, name))
    if not selected:
        return
    # stdin/stderr 使用临时文件，避免写满任一 pipe 后与 stdout 互等。
    with TemporaryFile() as requests, TemporaryFile() as errors:
        for _, oid, _ in selected:
            requests.write((oid + '\n').encode('ascii'))
        requests.seek(0)
        with subprocess.Popen(['git', '--no-replace-objects', 'cat-file', '--batch'], cwd=repo,
                              stdin=requests, stdout=subprocess.PIPE, stderr=errors) as process:
            try:
                write_blobs(process.stdout, selected, destination)
                if process.wait():
                    raise MDFError('git cat-file --batch 执行失败', code='invalid_fact_snapshot')
            except MDFError as exc:
                if process.poll() is None:
                    process.kill()
                process.wait()
                errors.seek(0)
                diagnostic = errors.read().decode('utf-8', errors='replace').strip()
                raise MDFError(f'{exc}\n{diagnostic}'.strip(), code='invalid_fact_snapshot') from exc
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()


def write_blobs(stream, selected, destination):
    for mode, oid, name in selected:
        header = stream.readline(256).split()
        if len(header) != 3 or header[:2] != [oid.encode('ascii'), b'blob'] or not header[2].isdigit():
            raise MDFError(f'snapshot blob 响应无效：{name}', code='invalid_fact_snapshot')
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        remaining = int(header[2])
        with path.open('wb') as output:
            while remaining:
                data = stream.read(min(remaining, 1024 * 1024))
                if not data:
                    raise MDFError(f'snapshot blob 响应截断：{name}', code='invalid_fact_snapshot')
                output.write(data)
                remaining -= len(data)
        if stream.read(1) != b'\n':
            raise MDFError(f'snapshot blob 响应截断：{name}', code='invalid_fact_snapshot')
        path.chmod(0o755 if mode == '100755' else 0o644)
    if stream.read(1):
        raise MDFError('snapshot blob 响应有多余内容', code='invalid_fact_snapshot')


def worktree_files(repo):
    tracked = {entry.split('\t', 1)[1]: entry.split(' ', 1)[0]
               for entry in git(repo, 'ls-tree', '-rz', 'HEAD').stdout.split('\0') if entry}
    present = git(repo, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').stdout.split('\0')
    files = {}
    for name in sorted((set(tracked) | set(present)) - {''}):
        parts = PurePosixPath(name).parts
        if PurePosixPath(name).is_absolute() or any(p.lower() in {'.git', '..'} for p in parts):
            raise MDFError(f'工作区路径不安全：{name}', code='invalid_review_snapshot')
        path = repo / name
        if any(repo.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts) + 1)):
            raise MDFError(f'工作区不支持 symlink：{name}', code='invalid_review_snapshot')
        if not path.exists():
            continue
        if path.is_dir() and tracked.get(name) in {'100644', '100755'}:
            continue  # 已跟踪文件被目录替换；其新文件由 untracked 清单收集。
        if not path.is_file():
            raise MDFError(f'工作区不支持非普通文件：{name}', code='invalid_review_snapshot')
        data = path.read_bytes()
        mode = '100755' if path.stat().st_mode & 0o111 else '100644'
        files[name] = (mode, data)
    return files


def working_snapshot(repo, destination):
    initialize(repo, sha(repo, 'HEAD'), destination)
    files = worktree_files(repo)
    for name, (mode, data) in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o755 if mode == '100755' else 0o644)
    # 仅写临时仓库的 index/objects；info attributes 禁用工作区 filters。
    git(destination, '-c', 'core.autocrlf=false', 'add', '--force', '--all')
    return file_manifest(files)


def file_manifest(files):
    return {name: {'mode': mode, 'sha256': hashlib.sha256(data).hexdigest()}
            for name, (mode, data) in files.items()}
