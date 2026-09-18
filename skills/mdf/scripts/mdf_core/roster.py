"""交付 roster：人数冻结、角色分支名、可见身份。"""
import json
import re

from .errors import MDFError
from .gitutil import branch_details, run

DEFAULTS = {
    "feature": (1, 1, 3),
    "bugfix": (0, 0, 3),
    "release": (0, 0, 3),
    "hotfix": (0, 0, 3),
}

_ROLE = re.compile(
    r"^(?P<role>qa|dev)(?:/(?P<index>[1-9]\d*))?/"
    r"(?P<owner>(?:feature|bugfix|release|hotfix)/.+)$"
)


def _counts(qa, dev, reviewers, *, coerce):
    for name, value in (("qa", qa), ("dev", dev), ("reviewers", reviewers)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise MDFError(f"roster.{name} 必须是整数", code="invalid_roster")
    if qa < 0 or dev < 0:
        raise MDFError("roster.qa 与 roster.dev 不能为负", code="invalid_roster")
    if reviewers < 1:
        raise MDFError("roster.reviewers 至少为 1", code="invalid_roster")
    if (qa == 0) != (dev == 0):
        if not coerce:
            raise MDFError("qa 与 dev 只能同时为 0 或都 ≥1",
                           code="invalid_roster")
        qa = qa or 1
        dev = dev or 1
    return {"dev": dev, "qa": qa, "reviewers": reviewers}


def freeze_roster(kind, qa=None, dev=None, reviewers=None):
    if kind not in DEFAULTS:
        raise MDFError("未知交付 kind", code="unsupported_branch")
    default_qa, default_dev, default_reviewers = DEFAULTS[kind]
    qa = default_qa if qa is None else qa
    dev = default_dev if dev is None else dev
    reviewers = default_reviewers if reviewers is None else reviewers
    return _counts(qa, dev, reviewers, coerce=True)


def require_roster(value):
    if not isinstance(value, dict) or set(value) != {"qa", "dev", "reviewers"}:
        raise MDFError("roster 必须含 qa、dev、reviewers", code="invalid_roster")
    return _counts(value["qa"], value["dev"], value["reviewers"], coerce=False)


def role_branch(role, owner, index):
    if role not in {"qa", "dev"} or index < 1:
        raise MDFError("非法角色分支", code="invalid_roster")
    if index == 1:
        return f"{role}/{owner}"
    return f"{role}/{index}/{owner}"


def role_branches(owner, roster):
    roster = require_roster(roster)
    names = []
    for role in ("qa", "dev"):
        for index in range(1, roster[role] + 1):
            names.append(role_branch(role, owner, index))
    return names


def start_branches(owner, roster):
    return [owner, *role_branches(owner, roster)]


def parse_role_branch(branch):
    match = _ROLE.fullmatch(branch)
    if match is None or match.group("index") == "1":
        return None
    index = 1 if match.group("index") is None else int(match.group("index"))
    return match.group("owner"), match.group("role"), index


def owner_branch(branch):
    parsed = parse_role_branch(branch)
    if parsed is not None:
        return parsed[0]
    if branch_details(branch)["supported"]:
        return branch
    raise MDFError("阶段操作需要交付或 qa/dev 角色分支",
                   code="unsupported_branch")


def roster_config_key(owner):
    return f"branch.{owner}.mdf-roster"


def write_roster_config(repo, owner, roster):
    payload = json.dumps(require_roster(roster), ensure_ascii=False,
                         sort_keys=True)
    run(["git", "config", "--local", roster_config_key(owner), payload],
        cwd=repo)


def read_roster_config(repo, owner):
    result = run(
        ["git", "config", "--local", "--get", roster_config_key(owner)],
        cwd=repo, check=False,
    )
    if result.returncode:
        raise MDFError("roster 未冻结", code="invalid_roster")
    try:
        value = json.loads(result.stdout.strip())
    except ValueError as exc:
        raise MDFError("roster 配置损坏", code="invalid_roster") from exc
    return require_roster(value)


def resolve_roster(repo, owner, kind):
    try:
        return read_roster_config(repo, owner)
    except MDFError:
        return freeze_roster(kind)


def winner_branch(role, owner, roster, specified):
    roster = require_roster(roster)
    count = roster[role]
    expected = [role_branch(role, owner, index)
                for index in range(1, count + 1)]
    if count == 0:
        if specified:
            raise MDFError(f"{role} roster 为 0，不要传 winner",
                           code="unexpected_winner")
        return None
    if specified is None:
        if count == 1:
            return expected[0]
        raise MDFError(f"{role} 人数 ≥2 时必须指定 winner 分支",
                       code="missing_winner")
    if specified not in expected:
        raise MDFError(f"{role} winner 不属于本次 roster",
                       code="invalid_winner")
    return specified
