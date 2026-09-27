"""项目验证入口：lint、build 与 quick/smoke/full 三个全局 suite；失败标准由项目命令负责。"""
import re

from .errors import MDFError

STEPS = ("lint", "build")
SUITES = ("quick", "smoke", "full")
ENTRIES = (*STEPS, *SUITES)
DEFAULT_BUDGETS = {"quick": 30, "smoke": 300}
NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MIGRATE_HINT = "；用 $mdf migrate 收敛到当前契约"


class Verification:
    """manifest.verification 的已校验视图：commands 为入口名 -> 命令，budgets 为 suite -> 秒数。"""

    def __init__(self, commands, budgets):
        self.commands = commands
        self.budgets = budgets

    def budget(self, name):
        return self.budgets.get(name, DEFAULT_BUDGETS.get(name))

    def plan(self, suite):
        names = [*STEPS, "quick"] + ([suite] if suite != "quick" else [])
        return [{"id": name, "command": self.commands[name], "budget": self.budget(name)}
                for name in names]

    def config(self):
        return {"commands": self.commands, "budgets": self.budgets}


def required_suite(kind):
    if kind in {"release", "hotfix"}:
        return "full"
    if kind in {"feature", "bugfix"}:
        return "smoke"
    raise MDFError("验证 suite 需要 Gitflow 交付分支", code="unsupported_branch")


def required_suites(kind):
    return ["quick", required_suite(kind)]


def recorded_suites(record):
    raw = record.get("suites")
    if not isinstance(raw, list) or any(not isinstance(name, str) for name in raw):
        return []
    return raw


def suites_cover(recorded, required):
    return set(recorded) >= set(required)


def parse_suite_names(raw):
    if not isinstance(raw, list) or not raw:
        raise MDFError("named suite 必须为非空名称列表", code="invalid_delivery_suite")
    seen = []
    for name in raw:
        if (not isinstance(name, str) or not NAME_RE.fullmatch(name)
                or name in ENTRIES or name in seen):
            raise MDFError(
                "named suite 名称无效、重复或占用 lint/build/quick/smoke/full",
                code="invalid_delivery_suite",
            )
        seen.append(name)
    return seen


def validate_verification(raw):
    if not isinstance(raw, dict) or set(raw) - {*ENTRIES, "budgets"} or set(ENTRIES) - set(raw):
        raise MDFError(
            "verification 必须且只能声明 lint、build、quick、smoke、full 与可选 budgets"
            + MIGRATE_HINT,
            code="invalid_verification",
        )
    commands = {}
    for name in ENTRIES:
        value = raw[name]
        if not isinstance(value, str) or not value.strip():
            raise MDFError(f"verification.{name} 必须为非空命令", code="invalid_verification")
        commands[name] = value
    budgets = raw.get("budgets", {})
    if (not isinstance(budgets, dict) or set(budgets) - set(SUITES)
            or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
                   for value in budgets.values())):
        raise MDFError(
            "verification.budgets 只接受 quick、smoke、full 的正整数秒数",
            code="invalid_verification",
        )
    return Verification(commands, dict(budgets))


def manifest_verification(manifest):
    return validate_verification(manifest.get("verification"))


def parse_budgets(raw):
    budgets = {}
    for value in raw:
        name, sep, seconds = value.partition("=")
        if not sep or name in budgets or not seconds.isdigit():
            raise MDFError("--budget 必须为 <suite>=<秒数>", code="invalid_verification")
        budgets[name] = int(seconds)
    return budgets
