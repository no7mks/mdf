from .errors import MDFError


def bump_kind(
    previous: tuple[int, int, int], candidate: tuple[int, int, int]
) -> str:
    if candidate <= previous:
        raise MDFError(
            "Candidate version must be greater than previous",
            code="not_increasing",
        )
    if candidate[0] != previous[0]:
        return "major"
    if candidate[1] != previous[1]:
        return "minor"
    return "patch"


def required_bump(
    previous: tuple[int, int, int], categories: set[str], breaking: bool
) -> str:
    if breaking or "Removed" in categories:
        return "major" if previous[0] >= 1 else "minor"
    if categories & {"Added", "Changed", "Deprecated"}:
        return "minor"
    return "patch"
