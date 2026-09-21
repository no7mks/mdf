"""Run project verification commands with live stderr progress."""
from __future__ import annotations

import codecs
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from .errors import MDFError

VERIFY_COMMAND_TIMEOUT = 600
TAIL_CHARS = 2000
HEARTBEAT_SECONDS = 30
LABEL_MAX = 80
_TERM_GRACE_SECONDS = 5
_STDERR_LOCK = threading.Lock()


def _progress_label(value: str) -> str:
    line = value.splitlines()[0] if value else ""
    return line[:LABEL_MAX]


def _timeout_value(timeout: float) -> float | int:
    as_int = int(timeout)
    return as_int if timeout == as_int else timeout


def _write_stderr(text: str) -> None:
    with _STDERR_LOCK:
        sys.stderr.write(text)
        sys.stderr.flush()


def _write_progress(index: int, total: int, body: str) -> None:
    _write_stderr(f"[{index}/{total}] {body}\n")


class _StreamTee:
    """Forward bytes as UTF-8 and keep a bounded decoded tail."""

    def __init__(self, last_output: list[float]) -> None:
        self.tail = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._ends_newline = True
        self._last_output = last_output

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        text = self._decoder.decode(chunk)
        if not text:
            return
        self.tail = (self.tail + text)[-TAIL_CHARS:]
        self._ends_newline = text.endswith("\n")
        self._last_output[0] = time.monotonic()
        _write_stderr(text)

    def finish(self) -> None:
        text = self._decoder.decode(b"", final=True)
        if text:
            self.tail = (self.tail + text)[-TAIL_CHARS:]
            self._ends_newline = text.endswith("\n")
            _write_stderr(text)
        if not self._ends_newline:
            _write_stderr("\n")
            self._ends_newline = True


def _drain(pipe: Any, tee: _StreamTee) -> None:
    if pipe is None:
        return
    try:
        fd = pipe.fileno()
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            tee.feed(chunk)
    except OSError:
        return


def _signal_group(proc: subprocess.Popen[bytes], *, force: bool) -> None:
    if proc.pid is None:
        return
    try:
        if hasattr(os, "killpg") and hasattr(signal, "SIGKILL"):
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.killpg(os.getpgid(proc.pid), sig)
        elif force:
            proc.kill()
        else:
            proc.terminate()
    except (ProcessLookupError, OSError):
        return


def _stop_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    _signal_group(proc, force=False)
    try:
        proc.wait(timeout=_TERM_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    _signal_group(proc, force=True)
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        return


def _join_readers(
    proc: subprocess.Popen[bytes],
    threads: list[threading.Thread],
    tees: tuple[_StreamTee, _StreamTee],
) -> None:
    for thread in threads:
        thread.join(timeout=5)
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    for thread in threads:
        thread.join(timeout=1)
    if all(not thread.is_alive() for thread in threads):
        for tee in tees:
            tee.finish()


def _wait_with_heartbeat(
    proc: subprocess.Popen[bytes],
    last_output: list[float],
    started: float,
    timeout: float,
    index: int,
    total: int,
    display: str,
) -> bool:
    deadline = started + timeout
    next_heartbeat = started + HEARTBEAT_SECONDS
    while True:
        now = time.monotonic()
        remaining = deadline - now
        if remaining <= 0:
            return True
        wait_for = min(remaining, max(next_heartbeat - now, 0.0))
        try:
            proc.wait(timeout=wait_for if wait_for > 0 else 0.05)
            return False
        except subprocess.TimeoutExpired:
            now = time.monotonic()
            if now >= deadline:
                return True
            next_heartbeat = last_output[0] + HEARTBEAT_SECONDS
            if now >= next_heartbeat:
                elapsed = now - started
                _write_progress(
                    index, total, f"running {display} ({elapsed:.0f}s)"
                )
                next_heartbeat = now + HEARTBEAT_SECONDS


def run_verify_command(
    repo: Path,
    command: str,
    *,
    label: str | None = None,
    index: int = 1,
    total: int = 1,
    timeout: float = VERIFY_COMMAND_TIMEOUT,
) -> dict[str, Any]:
    display = _progress_label(label if label is not None else command)
    _write_progress(index, total, f"start {display}")
    last_output = [time.monotonic()]
    stdout_tee = _StreamTee(last_output)
    stderr_tee = _StreamTee(last_output)
    started = time.monotonic()
    timed_out = False
    proc: subprocess.Popen[bytes] | None = None
    threads: list[threading.Thread] = []
    try:
        proc = subprocess.Popen(
            command,
            cwd=repo,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
        )
        threads = [
            threading.Thread(
                target=_drain, args=(proc.stdout, stdout_tee), daemon=True
            ),
            threading.Thread(
                target=_drain, args=(proc.stderr, stderr_tee), daemon=True
            ),
        ]
        for thread in threads:
            thread.start()
        timed_out = _wait_with_heartbeat(
            proc, last_output, started, timeout, index, total, display
        )
    finally:
        if proc is not None:
            if timed_out or proc.poll() is None:
                _stop_process(proc)
            _join_readers(proc, threads, (stdout_tee, stderr_tee))
    elapsed = time.monotonic() - started
    exit_code = -1 if proc is None or proc.returncode is None else proc.returncode
    _write_progress(
        index, total, f"done exit={exit_code} ({elapsed:.0f}s)"
    )
    entry = {"command": command, "exit_code": exit_code}
    limit = _timeout_value(timeout)
    if timed_out:
        raise MDFError(
            f"verification command 超时（{limit} 秒）: {command}",
            code="verify_command_failed",
            details={
                "command": command,
                "timeout_seconds": limit,
                "stdout_tail": stdout_tee.tail[-TAIL_CHARS:],
                "stderr_tail": stderr_tee.tail[-TAIL_CHARS:],
            },
        )
    if exit_code != 0:
        raise MDFError(
            f"verification command 失败: {command}",
            code="verify_command_failed",
            details={
                "command": command,
                "exit_code": exit_code,
                "stdout_tail": stdout_tee.tail[-TAIL_CHARS:],
                "stderr_tail": stderr_tee.tail[-TAIL_CHARS:],
            },
        )
    return entry


def run_verify_commands(
    repo: Path,
    commands: list[str],
    *,
    labels: list[str] | None = None,
    timeout: float = VERIFY_COMMAND_TIMEOUT,
) -> list[dict[str, Any]]:
    names = (
        labels if labels is not None and len(labels) == len(commands) else None
    )
    results: list[dict[str, Any]] = []
    total = len(commands)
    for offset, command in enumerate(commands):
        label = names[offset] if names is not None else command
        try:
            entry = run_verify_command(
                repo,
                command,
                label=label,
                index=offset + 1,
                total=total,
                timeout=timeout,
            )
        except MDFError as exc:
            details = dict(exc.details) if isinstance(exc.details, dict) else {}
            if "exit_code" in details:
                results.append(
                    {"command": command, "exit_code": details["exit_code"]}
                )
            details["results"] = results
            raise MDFError(str(exc), code=exc.code, details=details) from exc
        results.append(entry)
    return results
