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
    command_move_change,
    command_semver,
    command_validate,
)
from .commands_release import command_release_closeout
from .errors import MDFError
from .gitflow import command_finish_gitflow, command_start


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
    init.set_defaults(func=command_init)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--repo", required=True)
    validate.add_argument(
        "--scope", choices=("targeted", "full"), default="targeted"
    )
    validate.set_defaults(func=command_validate)

    make_id = subparsers.add_parser("make-id")
    make_id.add_argument(
        "--type", choices=("requirement", "bug"), required=True
    )
    make_id.add_argument("--slug", required=True)
    make_id.set_defaults(func=command_make_id)

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

    move = subparsers.add_parser("move-change")
    move.add_argument("--repo", required=True)
    move.add_argument("--source")
    move.add_argument("--branch-slug", required=True)
    move.add_argument("--dry-run", action="store_true")
    move.set_defaults(func=command_move_change)

    closeout = subparsers.add_parser("release-closeout")
    closeout.add_argument("--repo", required=True)
    closeout.add_argument("--release-date")
    closeout.add_argument("--closures-json")
    closeout.add_argument("--deferred-acceptance-json")
    closeout.add_argument("--hotfix-change-json")
    closeout.add_argument("--semantic-attestation-json")
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
    start.add_argument("--version")
    start.set_defaults(func=command_start)

    finish = subparsers.add_parser("finish-gitflow")
    finish.add_argument("--repo", required=True)
    finish.set_defaults(func=command_finish_gitflow)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
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
