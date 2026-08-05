import re
from pathlib import Path

from .constants import JOT_ID_RE
from .errors import Finding, add_finding


ENTRY_RE = re.compile(
    r"<!-- jot: (?P<id>jot-[0-9a-hjkmnp-tv-z]{26}) -->\n"
    r"## (?P<title>[^\n]+)\n"
    r"(?P<body>.*?)"
    r"<!-- /jot -->\n?",
    re.DOTALL,
)


def validate_jots(repo: Path, findings: list[Finding]) -> None:
    path = repo / "JOTS.md"
    relative = "JOTS.md"
    if not path.exists() and not path.is_symlink():
        add_finding(findings, "jot.missing", "Missing JOTS.md", relative)
        return
    if not path.is_file() or path.is_symlink():
        add_finding(
            findings,
            "jot.path",
            "JOTS.md must be a regular repository file",
            relative,
        )
        return
    text = path.read_text(encoding="utf-8")
    if not text.startswith("# Jots\n"):
        add_finding(
            findings,
            "jot.heading",
            "JOTS.md must begin with '# Jots'",
            relative,
        )
        return
    _validate_entries(text[len("# Jots\n") :], findings, relative)


def _validate_entries(
    text: str,
    findings: list[Finding],
    relative: str,
) -> None:
    previous_end = 0
    identifiers: set[str] = set()
    for entry in ENTRY_RE.finditer(text):
        if text[previous_end : entry.start()].strip():
            add_finding(
                findings,
                "jot.format",
                "Jot content must be inside a marked entry",
                relative,
            )
            return
        identifier = entry.group("id")
        if not JOT_ID_RE.fullmatch(identifier):
            add_finding(
                findings,
                "jot.id",
                f"Invalid Jot ID: {identifier}",
                relative,
            )
        elif identifier in identifiers:
            add_finding(
                findings,
                "jot.id_duplicate",
                f"Duplicate Jot ID: {identifier}",
                relative,
            )
        identifiers.add(identifier)
        if not entry.group("body").strip():
            add_finding(
                findings,
                "jot.empty",
                f"Jot must have content: {identifier}",
                relative,
            )
        previous_end = entry.end()
    if text[previous_end:].strip():
        add_finding(
            findings,
            "jot.format",
            "Jot content must be inside a marked entry",
            relative,
        )
