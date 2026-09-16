import argparse
import json
import sys

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
from .commands_release import command_release_closeout
from .errors import MDFError
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

    init = subparsers.add_parser("init")
    init.add_argument("--repo", required=True)
    init.add_argument("--latest-release", required=True)
    init.add_argument("--baseline", action="append", default=[], required=True)
    init.add_argument(
        "--verification-item",
        action="append",
        default=[],
        required=True,
    )
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
    audit.add_argument("--scope", choices=("full", "paths"), default="full")
    audit.add_argument("--implementation-path", action="append", default=[])
    audit.add_argument("--document-path", action="append", default=[])
    audit.set_defaults(func=command_audit)

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
    start.set_defaults(func=command_start)

    from .list_objects import command_list
    from .next_view import command_next
    from .prp_split import command_split
    from .delivery import command_delivery
    from .delivery_state import STAGES

    next_parser = subparsers.add_parser("next")
    next_parser.add_argument("--repo", required=True)
    next_parser.add_argument("--depth", type=int, default=3)
    next_parser.set_defaults(func=command_next)

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
        choices=("status", "check", "record", "verify", "integrate"),
    )
    delivery.add_argument("--repo", required=True)
    delivery.add_argument("--stage", choices=(*STAGES, "finish"))
    delivery.add_argument("--summary")
    delivery.add_argument("--policy-file")
    delivery.add_argument("--test-approval")
    delivery.add_argument("--item", action="append", default=[])
    delivery.set_defaults(func=command_delivery)

    from .planning import command_planning
    planning = subparsers.add_parser("planning")
    planning.add_argument("action", choices=("ensure", "land"))
    planning.add_argument("--repo", required=True)
    planning.set_defaults(func=command_planning)

    from .codewiki_runtime import command_codewiki_runtime
    runtime = subparsers.add_parser("codewiki-runtime")
    runtime.add_argument("--directory", default="~/.local/share/codewiki")
    runtime.set_defaults(func=command_codewiki_runtime)

    from .worktree_check import command_worktree_check
    worktree = subparsers.add_parser("worktree-check")
    worktree.add_argument("--repo", required=True)
    worktree.add_argument("--owner", required=True)
    worktree.add_argument("--role", choices=("owner", "qa", "dev"), required=True)
    worktree.add_argument("--design-commit")
    worktree.add_argument("--expected-head")
    worktree.add_argument("--handoff", action="store_true")
    worktree.set_defaults(func=command_worktree_check)

    from .project_verify import command_project_verify
    verification = subparsers.add_parser("project-verify")
    verification.add_argument("action", choices=("run", "check"))
    verification.add_argument("--repo", required=True)
    verification.set_defaults(func=command_project_verify)

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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except MDFError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    except (OSError, UnicodeError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "operation_failed",
                    "message": str(exc),
                    "details": None,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "internal_error",
                    "message": str(exc),
                    "details": None,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
