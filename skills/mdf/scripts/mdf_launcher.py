#!/usr/bin/env python3
"""仓外 MDF 入口。启动时解析 current 并固定版本；升级与回滚不依赖 Core。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import mdf_home  # noqa: E402


OWNED = ("root", "upgrade", "restore", "install-payload")


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def fail(exc: mdf_home.HomeError) -> int:
    body = {"ok": False, "error": exc.code, "message": exc.message}
    if exc.details is not None:
        body["details"] = exc.details
    print(exc.message, file=sys.stderr)
    print(json.dumps(body, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 1


def handoff(argv: list[str]) -> int:
    try:
        root, code = mdf_home.select_root(None)
        version, _revision = mdf_home.resolve_version(root, code)
    except mdf_home.HomeError as exc:
        return fail(exc)
    script = version / "scripts" / "mdf.py"
    try:
        os.execv(sys.executable, [sys.executable, "-B", str(script), *argv])
    except OSError as exc:
        return fail(mdf_home.HomeError(str(exc), code))
    return 1


def command_root() -> int:
    root, code = mdf_home.select_root(None)
    version, _revision = mdf_home.resolve_version(root, code)
    print(str(version), flush=True)
    return 0


def command_install(args: argparse.Namespace) -> int:
    root, _code = mdf_home.select_root(args.home)
    emit(mdf_home.install_payload(root, args.revision, Path(args.payload)))
    return 0


def command_upgrade(args: argparse.Namespace) -> int:
    root, _code = mdf_home.select_root(args.home)
    emit(mdf_home.upgrade(
        root, args.source, dry_run=args.dry_run, expected=args.expected_commit,
        repo=args.repo,
    ))
    return 0


def command_restore(args: argparse.Namespace) -> int:
    root, _code = mdf_home.select_root(args.home)
    emit(mdf_home.restore(root, args.revision))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="仓外 MDF 入口")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("root")
    install = sub.add_parser("install-payload")
    install.add_argument("--revision", required=True)
    install.add_argument("--payload", required=True)
    install.add_argument("--home")
    upgrade = sub.add_parser("upgrade")
    upgrade.add_argument("--source", default=mdf_home.DEFAULT_SOURCE)
    upgrade.add_argument("--dry-run", action="store_true")
    upgrade.add_argument("--expected-commit")
    upgrade.add_argument("--repo")
    upgrade.add_argument("--home")
    restore = sub.add_parser("restore")
    restore.add_argument("--revision")
    restore.add_argument("--home")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in OWNED:
        return handoff(argv)
    try:
        args = build_parser().parse_args(argv)
        if args.command == "root":
            return command_root()
        if args.command == "install-payload":
            return command_install(args)
        if args.command == "upgrade":
            return command_upgrade(args)
        return command_restore(args)
    except mdf_home.HomeError as exc:
        return fail(exc)


if __name__ == "__main__":
    raise SystemExit(main())
