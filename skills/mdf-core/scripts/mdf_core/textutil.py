import datetime as dt
import re
import secrets
import unicodedata
from typing import Any

from .constants import STABLE_SEMVER_RE
from .errors import MDFError


def stable_semver(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = STABLE_SEMVER_RE.fullmatch(value)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def slugify(value: str) -> str:
    normalized = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .strip()
        .lower()
    )
    normalized = normalized.replace("/", "-")
    normalized = normalized.replace("_", "-").replace(".", "-")
    normalized = re.sub(r"[^a-z0-9-]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    if not normalized:
        raise MDFError(
            "Slug becomes empty after normalization", code="empty_slug"
        )
    return normalized


def new_ulid() -> str:
    alphabet = "0123456789abcdefghjkmnpqrstvwxyz"
    milliseconds = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    value = (milliseconds << 80) | secrets.randbits(80)
    chars = ["0"] * 26
    for index in range(25, -1, -1):
        chars[index] = alphabet[value & 31]
        value >>= 5
    return "".join(chars)
