#!/bin/sh
# 比较、安装或卸载当前 MDF Skill。
#
# 用法：
#   ./mdf-deploy.sh diff --target /path/to/project
#   ./mdf-deploy.sh install --target /path/to/project
#   ./mdf-deploy.sh unistall --target /path/to/project

set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SOURCE_SKILL="$SCRIPT_DIR/skills/mdf"
ACTION=""
TARGET=""
TEMP_ROOT=""
KNOWN_SKILL_DIRS=".agents/skills .claude/skills .codex/skills .cursor/skills \
.kiro/skills .openclaw/skills"

die() {
    echo "错误：$1" >&2
    exit 1
}

cleanup() {
    [ -z "$TEMP_ROOT" ] || rm -rf "$TEMP_ROOT"
}

trap cleanup 0 HUP INT TERM

usage() {
    sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
}

parse_arguments() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --target)
                shift
                [ $# -gt 0 ] || die "--target 需要一个目录参数"
                TARGET="$1"
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *) die "未知参数: $1" ;;
        esac
        shift
    done
}

[ $# -gt 0 ] || die "需要指定 diff、install 或 unistall"
ACTION="$1"
shift

case "$ACTION" in
    diff|install|unistall) parse_arguments "$@" ;;
    -h|--help)
        usage
        exit 0
        ;;
    *) die "未知动作: $ACTION" ;;
esac

[ -n "$TARGET" ] || die "需要指定 --target"
[ -d "$TARGET" ] || die "找不到目标仓库: $TARGET"
TARGET=$(cd "$TARGET" && pwd)

git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1 || \
    die "脚本必须在 MDF Git 仓库中运行"
git -C "$TARGET" rev-parse --show-toplevel >/dev/null 2>&1 || \
    die "目标目录不是 Git 仓库"

if [ "$ACTION" != "unistall" ]; then
    [ -d "$SOURCE_SKILL" ] || die "找不到源 Skill: $SOURCE_SKILL"
fi

has_skill_dir=0
for directory in $KNOWN_SKILL_DIRS; do
    [ -d "$TARGET/$directory" ] || continue
    has_skill_dir=1
done
[ "$has_skill_dir" -eq 1 ] || die "未检测到受支持的 skills 目录"

prepare_baseline() {
    target_skill="$1"
    version_file="$target_skill/references/.version"
    [ -f "$version_file" ] || die "目标 mdf 缺少 references/.version：$target_skill"
    baseline_commit=$(sed -n '1p' "$version_file")
    [ -n "$baseline_commit" ] || die "目标 mdf 的 .version 为空：$target_skill"
    resolved_commit=$(git -C "$SCRIPT_DIR" rev-parse \
        --verify "$baseline_commit^{commit}" 2>/dev/null) || \
        die "本地没有基线 commit：$baseline_commit"
    [ "$resolved_commit" = "$baseline_commit" ] || \
        die "基线必须是完整 commit hash：$baseline_commit"
    git -C "$SCRIPT_DIR" cat-file -e \
        "$baseline_commit:skills/mdf" 2>/dev/null || \
        die "基线 commit 中没有 skills/mdf：$baseline_commit"

    [ -n "$TEMP_ROOT" ] || TEMP_ROOT=$(mktemp -d)
    local_base=$(mktemp -d "$TEMP_ROOT/local.XXXXXX")
    target_base=$(mktemp -d "$TEMP_ROOT/target.XXXXXX")
    git -C "$SCRIPT_DIR" archive --format=tar \
        "$baseline_commit:skills/mdf" | tar -x -C "$local_base"
    git -C "$SCRIPT_DIR" archive --format=tar \
        "$baseline_commit:skills/mdf" | tar -x -C "$target_base"
    printf '%s\n' "$baseline_commit" > "$target_base/references/.version"

    LOCAL_BASE="$local_base"
    TARGET_BASE="$target_base"
}

diff_skill() {
    target_dir="$1"
    target_skill="$target_dir/mdf"
    printf '## %s\n' "$target_dir"
    if [ ! -e "$target_skill" ] && [ ! -L "$target_skill" ]; then
        echo "目标未安装 mdf。"
        return
    fi
    [ -d "$target_skill" ] && [ ! -L "$target_skill" ] || \
        die "目标 mdf 不是目录：$target_skill"
    prepare_baseline "$target_skill"
    printf '### 本地相对基线 %s\n' "$baseline_commit"
    if diff -ru "$LOCAL_BASE" "$SOURCE_SKILL"; then
        echo "无改动。"
    fi
    printf '### 目标相对基线 %s\n' "$baseline_commit"
    if diff -ru "$TARGET_BASE" "$target_skill"; then
        echo "无改动。"
    fi
}

show_diff() {
    for directory in $KNOWN_SKILL_DIRS; do
        [ -d "$TARGET/$directory" ] || continue
        diff_skill "$TARGET/$directory"
    done
}

require_clean_source() {
    source_status=$(git -C "$SCRIPT_DIR" status --porcelain)
    [ -z "$source_status" ] || die "MDF 源仓库工作区不干净，无法安装"
    SOURCE_COMMIT=$(git -C "$SCRIPT_DIR" rev-parse HEAD)
    git -C "$SCRIPT_DIR" cat-file -e \
        "$SOURCE_COMMIT:skills/mdf" 2>/dev/null || \
        die "当前 commit 中没有 skills/mdf"
}

install_skill() {
    target_dir="$1"
    git -C "$SCRIPT_DIR" archive --format=tar \
        "$SOURCE_COMMIT:skills/mdf" | tar -x -C "$target_dir/mdf"
    printf '%s\n' "$SOURCE_COMMIT" > "$target_dir/mdf/references/.version"
    printf '已安装：%s/mdf（基线 %s）\n' "$target_dir" "$SOURCE_COMMIT"
}

install() {
    require_clean_source
    for directory in $KNOWN_SKILL_DIRS; do
        target_skill="$TARGET/$directory/mdf"
        [ -d "$TARGET/$directory" ] || continue
        if [ -e "$target_skill" ] || [ -L "$target_skill" ]; then
            die "目标已安装 mdf：$target_skill"
        fi
    done
    for directory in $KNOWN_SKILL_DIRS; do
        target_dir="$TARGET/$directory"
        [ -d "$target_dir" ] || continue
        mkdir "$target_dir/mdf"
        install_skill "$target_dir"
    done
}

unistall() {
    removed=0
    for directory in $KNOWN_SKILL_DIRS; do
        target_skill="$TARGET/$directory/mdf"
        [ -e "$target_skill" ] || [ -L "$target_skill" ] || continue
        rm -rf "$target_skill"
        printf '已卸载：%s\n' "$target_skill"
        removed=1
    done
    [ "$removed" -eq 1 ] || die "目标未安装 mdf"
}

case "$ACTION" in
    diff) show_diff ;;
    install) install ;;
    unistall) unistall ;;
esac
