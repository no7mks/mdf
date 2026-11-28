"""未共享线性尾段的 squash 边界与动作前检查；不决定语义分段。"""
import hashlib
import json
from pathlib import Path

from mdf_core.foundation.errors import MDFError
from mdf_core.workspace.gitutil import branch_details, current_branch, ensure_clean, worktree_map
from mdf_core.workspace.merge_policy import ancestor, configured, git, planning_only, sha


def common_dir(repo):
    return Path(git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').stdout.strip())


def receipt_path(repo, branch):
    key = hashlib.sha256(branch.encode()).hexdigest()
    return common_dir(repo) / 'mdf' / 'squash' / f'{key}.json'


def inspect(repo, branch=None, *, refresh=True):
    """仅最后一个保护边界之后的本人普通提交可改写。"""
    branch = branch or current_branch(repo)
    head = sha(repo, f'refs/heads/{branch}')
    if refresh:
        for remote in git(repo, 'remote').stdout.splitlines():
            # 显式获取所有分支，不依赖可能只覆盖一个分支的 fetch refspec。
            git(repo, 'fetch', remote, f'+refs/heads/*:refs/remotes/{remote}/*', '--tags')
    if branch == 'planning':
        from mdf_core.workspace.workflow_policy import trunk_branch
        target = f'refs/heads/{trunk_branch(repo)}'
        if (not git(repo, 'cat-file', '-e', f'{target}:.mdf/manifest.yaml', check=False).returncode
                and configured(repo, target)['mode'] == 'pr' and not planning_only(repo, target, head)):
            raise MDFError('planning 须先通过完整文档历史检查，不得用 squash 隐藏代码改动', code='pr_required')
    source = branch
    if branch_details(branch)['kind'] == 'pm':
        from mdf_core.workspace.pm import require_pm_diff, rework_source
        from mdf_core.workspace.changelog_sync import sync_version
        from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch
        from mdf_core.workspace.merge_policy import configured_delivery
        from mdf_core.workspace.reconcile_channel import is_reconcile
        if (not is_github_flow(repo) and not is_reconcile(branch)) or configured_delivery(repo, branch)['mode'] != 'pr':
            raise MDFError('pm 分支仅用于 github-flow 的 PR mode', code='invalid_closeout')
        if branch.startswith('pm/rework/'):
            source = rework_source(repo, branch)
            if source is None:
                raise MDFError('需要已登记的 pm 临时 worktree', code='invalid_worktree')
        elif branch in worktree_map(repo) and not sync_version(branch) and not is_reconcile(branch):
            raise MDFError('pm squash 须在临时 worktree 执行', code='invalid_worktree')
        require_pm_diff(repo, f'refs/remotes/origin/{trunk_branch(repo)}', head, source)
    refs = git(repo, 'for-each-ref', '--format=%(refname)', 'refs/heads', 'refs/remotes', 'refs/tags').stdout.splitlines()
    protected = set()
    for ref in refs:
        if ref in {f'refs/heads/{branch}', f'refs/heads/{source}'}:
            continue
        resolved = git(repo, 'rev-parse', '--verify', f'{ref}^{{commit}}', check=False)
        if resolved.returncode == 0:
            protected.add(resolved.stdout.strip())
        elif not ref.startswith('refs/tags/'):
            raise MDFError('无法解析共享引用', code='squash_boundary_unknown')
    for block in git(repo, 'worktree', 'list', '--porcelain').stdout.strip().split('\n\n'):
        rows = block.splitlines()
        if f'branch refs/heads/{branch}' not in rows:
            protected.update(row[5:] for row in rows if row.startswith('HEAD '))
    owner = branch
    from mdf_core.lifecycle.roster import parse_role_branch
    role = parse_role_branch(branch)
    if role:
        owner = role[0]
    if branch_details(branch)['kind'] == 'adhoc' and not role and not branch.startswith('codex/backmerge/'):
        from mdf_core.lifecycle.adhoc_context import material
        from mdf_core.foundation.yamlutil import read_frontmatter
        root, ledger = material(repo, branch)
        change = root / 'CHANGE.md'
        if not ledger and change.is_file():
            metadata, _ = read_frontmatter(change)
            evidence = metadata.get('evidence')
            fixed = evidence.get('range') if isinstance(evidence, dict) else None
            if fixed is not None:
                if not isinstance(fixed, dict) or not fixed.get('source_head'):
                    raise MDFError('Change 固定范围无效', code='squash_boundary_unknown')
                protected.add(sha(repo, fixed['source_head']))
    start = git(repo, 'config', '--get', f'branch.{owner}.mdf-start-commit', check=False)
    if start.returncode == 0:
        protected.add(sha(repo, start.stdout.strip()))
    elif start.returncode != 1:
        raise MDFError('无法读取交付起点', code='squash_boundary_unknown')
    from mdf_core.lifecycle.squash_state import protected_commits
    protected.update(protected_commits(repo, branch, head))
    shared = set(git(repo, 'rev-list', *sorted(protected)).stdout.splitlines()) if protected else set()
    email = git(repo, 'var', 'GIT_COMMITTER_IDENT').stdout.split('<', 1)[1].split('>', 1)[0]
    commits = []
    floor = head
    for row in git(repo, 'log', '--first-parent', '--format=%H%x09%P%x09%ae%x09%ce', head).stdout.splitlines():
        commit, parents, author, committer = row.split('\t')
        floor = commit
        if commit in shared or len(parents.split()) != 1 or author != email or committer != email:
            break
        commits.append(commit)
    return {'branch': branch, 'old_tip': head, 'floor': floor,
            'commits': list(reversed(commits)), 'noop': len(commits) < 2}


def record_analysis(repo, branch, head, *, reason, old_tip=None):
    path = receipt_path(repo, branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    if branch.startswith('pm/rework/'):
        from mdf_core.workspace.pm import rework_source
        source = rework_source(repo, branch)
        previous = analysis_receipt(repo, branch)
        origin = previous.get('old_tip')
        if (source and origin and ancestor(repo, f'refs/heads/{source}', origin)
                and ancestor(repo, previous['head'], old_tip or head)):
            old_tip = origin
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'branch': branch, 'head': head, 'reason': reason, 'old_tip': old_tip},
                                    ensure_ascii=False) + '\n')
    temporary.replace(path)


def analysis_receipt(repo, branch):
    path = receipt_path(repo, branch)
    if path.exists():
        try:
            receipt = json.loads(path.read_text())
        except ValueError as exc:
            raise MDFError('squash 检查记录损坏', code='squash_required') from exc
        if receipt.get('branch') == branch:
            return receipt
    return {}


def analysis_reason(repo, branch, head):
    receipt = analysis_receipt(repo, branch)
    return receipt.get('reason') if receipt.get('head') == head else None


def verified_squash(repo, branch, old, new):
    receipt = analysis_receipt(repo, branch)
    return (receipt.get('old_tip') and ancestor(repo, old, receipt['old_tip'])
            and ancestor(repo, receipt['head'], new))


def require_ready(repo, branch=None):
    """每次动作重新核边界；多笔尾段必须先由 Agent 分析并执行计划。"""
    from mdf_core.lifecycle.roster import parse_role_branch
    branch = branch or current_branch(repo)
    if branch != 'planning' and configured(repo)['mode'] != 'pr':
        return
    if not (branch == 'planning'
            or branch_details(branch)['kind'] == 'pm'
            or branch_details(branch)['supported']
            or parse_role_branch(branch)):
        return
    plan = inspect(repo, branch)
    if plan['noop']:
        return plan
    if analysis_reason(repo, plan['branch'], plan['old_tip']) is not None:
        return plan
    raise MDFError('动作前须分析未共享提交并执行 squash 计划；完成后重试',
                   code='squash_required', details=plan)


def check(repo):
    ensure_clean(repo)
    return inspect(repo)
