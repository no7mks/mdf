import re
import secrets
import unicodedata
from typing import Any

from .constants import OBJECT_ID_SLUG_RE, STABLE_SEMVER_RE
from .errors import MDFError


def stable_semver(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = STABLE_SEMVER_RE.fullmatch(value)
    if not match:
        return None
    return tuple(  # type: ignore[return-value]
        int(part) for part in match.groups()
    )


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


def is_object_id_slug(value: str) -> bool:
    return OBJECT_ID_SLUG_RE.fullmatch(value) is not None


def new_short_id() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(4))
