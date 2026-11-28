"""reconcile 四个 CLI 子命令的参数与锁边界。"""
from mdf_core.foundation.errors import emit
from mdf_core.foundation.paths import ensure_safe_managed_paths
from mdf_core.lifecycle.pull_finish import finish_lock
from mdf_core.reconciliation.context import inspect
from mdf_core.workspace.gitutil import repo_path, require_git_root


def register(subparsers):
    parser = subparsers.add_parser("reconcile")
    parser.add_argument("action", choices=("inspect", "prepare", "apply", "finish"))
    parser.add_argument("--repo", required=True)
    for name in ("version", "tag", "commit", "support", "source", "release-date", "record-file", "evidence-file"):
        parser.add_argument(f"--{name}")
    parser.add_argument("--record-only", action="store_true")
    parser.add_argument("--yolo", action="store_true")
    parser.set_defaults(func=command_reconcile)


def command_reconcile(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_safe_managed_paths(repo)
    if args.action == "inspect":
        result = inspect(repo, args)
    else:
        from mdf_core.reconciliation.prepare import prepare
        from mdf_core.reconciliation.records import apply
        from mdf_core.reconciliation.finish import finish
        with finish_lock(repo):
            result = {"prepare": prepare, "apply": apply, "finish": finish}[args.action](repo, args)
    emit({"ok": True, "operation": "reconcile-" + args.action, "result": result})
