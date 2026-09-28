import argparse
import json
import sys
import traceback

from .commands_misc import (
    command_archive,
    command_branch,
    command_doctor,
    command_info,
    command_init,
    command_make_id,
    command_make_jot_id,
    command_semver,
    command_validate,
)
from .audit import command_audit
from .doc_size import command_prose_check
from .commands_release import command_release_closeout
from .errors import MDFError
from .run_logs import RunLog
from .gitflow import command_finish_gitflow, command_start
from .upgrade import DEFAULT_SKILL_SOURCE, command_upgrade


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mars Development Flow deterministic core"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info")
    info.set_defaults(func=command_info)

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--repo", required=True)
    doctor.set_defaults(func=command_doctor)

    from .git_ops import command_merge_no_ff, command_prepare_git

    prepare_git = subparsers.add_parser("prepare-git")
    prepare_git.add_argument("--repo", required=True)
    prepare_git.set_defaults(func=command_prepare_git)

    merge = subparsers.add_parser("merge-no-ff")
    merge.add_argument("--repo", required=True)
    merge.add_argument("--commit", required=True)
    merge.set_defaults(func=command_merge_no_ff)

    init = subparsers.add_parser("init")
    init.add_argument("--repo", required=True)
    init.add_argument("--latest-release", required=True)
    init.add_argument("--baseline", action="append", default=[], required=True)
    for name in ("lint", "build", "quick", "smoke", "release"):
        init.add_argument(f"--{name}", required=True)
    init.add_argument("--budget", action="append", default=[])
    init.add_argument(
        "--implementation-root", action="append", default=[]
    )
    init.set_defaults(func=command_init)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--repo", required=True)
    validate.add_argument(
        "--scope", choices=("targeted", "full"), default="targeted"
    )
    validate.set_defaults(func=command_validate)

    audit = subparsers.add_parser("fact-audit")
    audit.add_argument("--repo", required=True)
    audit.add_argument(
        "--scope", choices=("full", "branch", "paths"), default="full"
    )
    audit.add_argument("--base")
    audit.add_argument("--implementation-path", action="append", default=[])
    audit.add_argument("--document-path", action="append", default=[])
    audit.set_defaults(func=command_audit)

    prose = subparsers.add_parser("prose-check")
    prose.add_argument("--repo", required=True)
    prose.add_argument("--path", action="append", default=[])
    prose.set_defaults(func=command_prose_check)

    make_id = subparsers.add_parser("make-id")
    make_id.add_argument(
        "--type", choices=("proposal", "bug"), required=True
    )
    make_id.add_argument("--slug", required=True, action="append")
    make_id.add_argument("--repo")
    make_id.set_defaults(func=command_make_id)

    make_jot_id = subparsers.add_parser("make-jot-id")
    make_jot_id.set_defaults(func=command_make_jot_id)

    branch = subparsers.add_parser("branch")
    branch.add_argument("--repo")
    branch.add_argument("--name")
    branch.set_defaults(func=command_branch)

    semver = subparsers.add_parser("semver-check")
    semver.add_argument("--previous", required=True)
    semver.add_argument("--candidate", required=True)
    semver.add_argument("--categories")
    semver.add_argument("--breaking", action="store_true")
    semver.set_defaults(func=command_semver)

    archive = subparsers.add_parser("archive")
    archive.add_argument("--repo", required=True)
    archive.add_argument("--epoch", required=True)
    archive.add_argument("--dry-run", action="store_true")
    archive.set_defaults(func=command_archive)

    closeout = subparsers.add_parser("release-closeout")
    closeout.add_argument("--repo", required=True)
    closeout.add_argument("--release-date")
    closeout.add_argument("--closures-json")
    closeout.add_argument("--deferred-acceptance-json")
    closeout.add_argument("--hotfix-change-json")
    closeout.add_argument("--dry-run", action="store_true")
    closeout.set_defaults(func=command_release_closeout)

    start = subparsers.add_parser("start")
    start.add_argument("--repo", required=True)
    start.add_argument(
        "--kind",
        choices=("feature", "bugfix", "release", "hotfix"),
        required=True,
    )
    start.add_argument("--name")
    start.add_argument("--proposal")
    start.add_argument("--bug")
    start.add_argument("--objectives-file")
    start.add_argument("--version")
    start.add_argument("--qa", type=int)
    start.add_argument("--dev", type=int)
    start.add_argument("--reviewers", type=int)
    from .roster import add_named_roster_argument, add_strategy_arguments
    add_named_roster_argument(start)
    add_strategy_arguments(start)
    start.set_defaults(func=command_start)

    from .list_objects import command_list
    from .tree_view import command_tree
    from .prp_split import command_split
    from .delivery import command_delivery
    from .delivery_state import STAGES

    tree_parser = subparsers.add_parser("tree")
    tree_parser.add_argument("--repo", required=True)
    tree_parser.add_argument("--depth", type=int, default=3)
    tree_parser.set_defaults(func=command_tree)

    listing = subparsers.add_parser("list")
    listing.add_argument("--repo", required=True)
    listing.add_argument("--type", choices=("proposal", "bug"))
    listing.add_argument("--status", action="append", default=[])
    listing.add_argument("--milestone")
    listing.add_argument("--severity")
    listing.set_defaults(func=command_list)

    split = subparsers.add_parser("prp-split")
    split.add_argument("--repo", required=True)
    split.add_argument("--spec-file", required=True)
    split.add_argument("--dry-run", action="store_true")
    split.set_defaults(func=command_split)

    delivery = subparsers.add_parser("delivery")
    delivery.add_argument(
        "action",
        choices=("status", "check", "record", "verify", "integrate", "roster"),
    )
    delivery.add_argument("--repo", required=True)
    delivery.add_argument("--stage", choices=(*STAGES, "finish"))
    delivery.add_argument("--summary")
    delivery.add_argument("--policy-file")
    delivery.add_argument("--test-approval")
    delivery.add_argument("--qa-branch")
    delivery.add_argument("--dev-branch")
    add_strategy_arguments(delivery)
    delivery.set_defaults(func=command_delivery)

    from .planning import command_planning
    planning = subparsers.add_parser("planning")
    planning.add_argument("action", choices=("ensure", "land"))
    planning.add_argument("--repo", required=True)
    planning.set_defaults(func=command_planning)

    from .to_target import command_to
    to_cmd = subparsers.add_parser("to")
    to_cmd.add_argument("--repo", required=True)
    to_cmd.add_argument("--target", required=True)
    to_cmd.set_defaults(func=command_to)

    from .codewiki_runtime import command_codewiki_runtime
    runtime = subparsers.add_parser("codewiki-runtime")
    runtime.add_argument("--directory", default="~/.local/share/codewiki")
    runtime.set_defaults(func=command_codewiki_runtime)

    from .worktree_check import command_worktree_check
    worktree = subparsers.add_parser("worktree-check")
    worktree.add_argument("--repo", required=True)
    worktree.add_argument("--owner", required=True)
    worktree.add_argument("--role", choices=("owner", "qa", "dev"), required=True)
    worktree.add_argument("--index", type=int, default=1)
    worktree.add_argument("--design-commit")
    worktree.add_argument("--expected-head")
    worktree.add_argument("--handoff", action="store_true")
    worktree.set_defaults(func=command_worktree_check)

    from .project_verify import command_project_verify, command_quick_run, command_suite_run
    verification = subparsers.add_parser("project-verify")
    verification.add_argument("action", choices=("run", "check"))
    verification.add_argument("--repo", required=True)
    verification.set_defaults(func=command_project_verify)

    quick_run = subparsers.add_parser("quick-run")
    quick_run.add_argument("--repo", required=True)
    quick_run.set_defaults(func=command_quick_run)

    suite_run = subparsers.add_parser("suite-run")
    suite_run.add_argument("--repo", required=True)
    suite_run.add_argument("--name", required=True)
    suite_run.add_argument("--command", required=True)
    suite_run.set_defaults(func=command_suite_run)

    finish = subparsers.add_parser("finish-gitflow")
    finish.add_argument("--repo", required=True)
    finish.add_argument("--source")
    finish.set_defaults(func=command_finish_gitflow)

    upgrade = subparsers.add_parser("upgrade")
    upgrade.add_argument("--repo", required=True)
    upgrade.add_argument("--source", default=DEFAULT_SKILL_SOURCE)
    upgrade.add_argument("--dry-run", action="store_true")
    upgrade.add_argument("--expected-commit")
    upgrade.set_defaults(func=command_upgrade)

    from .integrate import command_integrate

    integrate = subparsers.add_parser("integrate")
    integrate.add_argument(
        "action",
        choices=("init", "peer", "send", "poll", "listen", "status"),
    )
    integrate.add_argument("--repo", required=True)
    integrate.add_argument("--name")
    integrate.add_argument("--target")
    integrate.add_argument("--token")
    integrate.add_argument("--to")
    integrate.add_argument(
        "--kind", choices=("ping", "send", "bug-request", "end")
    )
    integrate.add_argument("--reply-to")
    integrate.add_argument("--body")
    integrate.add_argument("--observed")
    integrate.add_argument("--expected")
    integrate.add_argument("--repro")
    integrate.add_argument("--impact")
    integrate.add_argument("--timeout", type=float)
    integrate.add_argument("--bind", default="127.0.0.1:8765")
    integrate.set_defaults(func=command_integrate)
    return parser


def _failure(code: str, message: str, details, log: RunLog) -> int:
    print(
        json.dumps(
            {
                "ok": False,
                "error": code,
                "message": message,
                "details": details,
                "log": str(log.path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return 1


def _run(argv: list[str], log: RunLog) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
        return 0
    except MDFError as exc:
        return _failure(exc.code, str(exc), exc.details, log)
    except (OSError, UnicodeError) as exc:
        traceback.print_exc(file=sys.stderr)
        return _failure("operation_failed", str(exc), None, log)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        traceback.print_exc(file=sys.stderr)
        return _failure("internal_error", str(exc), None, log)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    log = RunLog(argv)
    code = 1
    with log:
        try:
            code = _run(argv, log)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else int(exc.code is not None)
            raise
        finally:
            log.finish(code)
    return code
