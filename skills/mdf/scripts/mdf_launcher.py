#!/usr/bin/env python3
"""项目内 MDF 入口。root 校验版本目录；upgrade 安装该 commit。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import mdf_home  # noqa: E402


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def fail(exc: mdf_home.HomeError) -> int:
    body = {"ok": False, "error": exc.code, "message": exc.message}
    if exc.details is not None:
        body["details"] = exc.details
    print(exc.message, file=sys.stderr)
    print(json.dumps(body, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 1


def command_root() -> int:
    print(str(mdf_home.core_of_launcher(Path(__file__))), flush=True)
    return 0


def command_install(args: argparse.Namespace) -> int:
    emit(mdf_home.install_payload(
        Path(args.repo), args.revision, Path(args.payload), args.source,
        from_entry=args.from_entry,
    ))
    return 0


def command_upgrade(args: argparse.Namespace) -> int:
    emit(mdf_home.upgrade(
        args.repo, args.source, dry_run=args.dry_run, expected=args.expected_commit,
    ))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="项目内 MDF 入口")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("root")
    install = sub.add_parser("install-payload")
    install.add_argument("--revision", required=True)
    install.add_argument("--payload", required=True)
    install.add_argument("--repo", required=True)
    install.add_argument("--source", required=True)
    install.add_argument("--from-entry", action="store_true")
    handoff = sub.add_parser("complete-upgrade")
    handoff.add_argument("--repo", required=True)
    handoff.add_argument("--payload", required=True)
    handoff.add_argument("--revision", required=True)
    handoff.add_argument("--source", required=True)
    upgrade = sub.add_parser("upgrade")
    upgrade.add_argument("--source", default=mdf_home.DEFAULT_SOURCE)
    upgrade.add_argument("--dry-run", action="store_true")
    upgrade.add_argument("--expected-commit")
    upgrade.add_argument("--repo")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = build_parser().parse_args(argv)
        if args.command == "root":
            return command_root()
        if args.command == "install-payload":
            return command_install(args)
        if args.command == "complete-upgrade":
            from mdf_install_handoff import handoff

            emit(handoff(args.repo, Path(args.payload), args.revision, args.source))
            return 0
        return command_upgrade(args)
    except mdf_home.HomeError as exc:
        return fail(exc)


if __name__ == "__main__":
    raise SystemExit(main())
