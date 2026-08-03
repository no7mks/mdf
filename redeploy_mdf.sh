#!/bin/sh
# 审查外部项目的 MDF 测试结果，并在确认后完整替换其已安装的 MDF Skill。
#
# 用法：
#   ./redeploy_mdf.sh report --target /path/to/project [--agent codex]
#   ./redeploy_mdf.sh deploy --target /path/to/project [--agent codex] [--yes]

set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SOURCE_SKILL="$SCRIPT_DIR/skills/mdf"
ACTION=""
TARGET=""
AGENT="codex"
YES=0

die() {
    echo "错误：$1" >&2
    exit 1
}

usage() {
    sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'
}

agent_dir() {
    case "$1" in
        claude) echo ".claude/skills" ;;
        cursor) echo ".cursor/skills" ;;
        kiro) echo ".kiro/skills" ;;
        codex) echo ".codex/skills" ;;
        kimi) echo ".kimi-code/skills" ;;
        openclaw) echo ".openclaw/skills" ;;
        *) die "未知 agent: $1" ;;
    esac
}

resolve_agent() {
    case "$1" in
        kimi-code) echo "kimi" ;;
        *) echo "$1" ;;
    esac
}

while [ $# -gt 0 ]; do
    case "$1" in
        report|deploy)
            [ -z "$ACTION" ] || die "只能指定一个动作"
            ACTION="$1"
            ;;
        --target)
            shift
            [ $# -gt 0 ] || die "--target 需要一个目录参数"
            TARGET="$1"
            ;;
        --agent)
            shift
            [ $# -gt 0 ] || die "--agent 需要一个名称参数"
            AGENT="$1"
            ;;
        --yes) YES=1 ;;
        -h|--help)
            usage
            exit 0
            ;;
        *) die "未知参数: $1" ;;
    esac
    shift
done

[ -n "$ACTION" ] || die "需要指定 report 或 deploy"
[ -n "$TARGET" ] || die "需要指定 --target"
[ -d "$SOURCE_SKILL" ] || die "找不到源 Skill: $SOURCE_SKILL"
[ -d "$TARGET" ] || die "找不到目标仓库: $TARGET"

TARGET=$(cd "$TARGET" && pwd)
AGENT=$(resolve_agent "$AGENT")
git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1 || \
    die "脚本必须在 MDF Git 仓库中运行"
git -C "$TARGET" rev-parse --show-toplevel >/dev/null 2>&1 || \
    die "目标目录不是 Git 仓库"

TARGET_SKILL="$TARGET/$(agent_dir "$AGENT")/mdf"

report_status() {
    label="$1"
    repo="$2"
    branch=$(git -C "$repo" branch --show-current)
    [ -n "$branch" ] || branch="(detached HEAD)"
    printf '%s 分支：%s\n' "$label" "$branch"
    status=$(git -C "$repo" status --short)
    if [ -n "$status" ]; then
        printf '%s 工作区改动：\n%s\n' "$label" "$status"
    else
        printf '%s 工作区改动：无\n' "$label"
    fi
}

report_source_skill_changes() {
    status=$(git -C "$SCRIPT_DIR" status --short -- skills/mdf)
    if [ -n "$status" ]; then
        printf '源 Skill 当前改动：\n%s\n' "$status"
    else
        echo "源 Skill 当前改动：无"
    fi
}

report_installed_skill() {
    echo "## 已安装 MDF 差异"
    if [ ! -e "$TARGET_SKILL" ] && [ ! -L "$TARGET_SKILL" ]; then
        echo "目标未安装 mdf；部署会安装当前源 Skill。"
        return
    fi
    if [ -L "$TARGET_SKILL" ]; then
        [ -d "$TARGET_SKILL" ] || {
            printf '目标 mdf 是失效软链：%s\n' "$TARGET_SKILL"
            return
        }
        installed=$(cd "$TARGET_SKILL" && pwd -P)
        source=$(cd "$SOURCE_SKILL" && pwd -P)
        if [ "$installed" = "$source" ]; then
            echo "目标 mdf 已链接到当前源 Skill，无安装目录差异。"
            return
        fi
        printf '目标 mdf 链接到其他位置：%s\n' "$installed"
    elif [ ! -d "$TARGET_SKILL" ]; then
        printf '目标 mdf 不是目录或软链：%s\n' "$TARGET_SKILL"
        return
    fi

    echo "以下目录差异需要判断："
    echo "- Only in 源目录：候选下发到目标。"
    echo "- Only in 目标目录：候选带回源仓库。"
    echo "- Files ... differ：按具体行为和证据判断。"
    if diff -qr "$SOURCE_SKILL" "$TARGET_SKILL"; then
        echo "两个 MDF 目录内容一致。"
    fi
}

report() {
    echo "# MDF redeploy 报告"
    printf '源仓库：%s\n目标仓库：%s\nAgent：%s\n' \
        "$SCRIPT_DIR" "$TARGET" "$AGENT"
    echo
    echo "## Git 状态"
    report_status "源仓库" "$SCRIPT_DIR"
    report_source_skill_changes
    report_status "目标仓库" "$TARGET"
    echo
    report_installed_skill
    echo
    cat <<'EOF'
## 回收与下发判断
- 目标仓库的业务代码、当前事实和实例化文档不能直接带回源 Skill。
- 可带回的候选必须是可复用的流程、模板或脚本行为，并补充源仓库测试。
- 源目录特有内容会在部署时下发；先确认它们适用于该目标项目。
- 部署始终以当前源仓库 skills/mdf 为唯一真相，并移除目标范围的 mdf-* 与 mdf。
EOF
}

deploy() {
    [ "$YES" -eq 1 ] || die "deploy 需要 --yes；仅在用户确认结论后传入"
    report
    echo
    sh "$SCRIPT_DIR/link_skills.sh" "$AGENT" --project "$TARGET"
    [ -L "$TARGET_SKILL" ] || die "部署后目标 mdf 不是软链"
    installed=$(cd "$TARGET_SKILL" && pwd -P)
    source=$(cd "$SOURCE_SKILL" && pwd -P)
    [ "$installed" = "$source" ] || die "部署后 mdf 未指向当前源 Skill"
    echo "部署完成：目标 mdf 已完整替换为当前源 Skill。"
}

case "$ACTION" in
    report) report ;;
    deploy) deploy ;;
esac
