#!/bin/sh
# 将当前 HEAD 的 MDF 安装到本机版本目录。
#
# 用法：
#   ./mdf-deploy.sh install [--home DIR]

set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
ACTION=""
HOME_DIR=""
HOME_SET=0
TEMP_ROOT=""

die() {
    echo "错误：$1" >&2
    exit 1
}

cleanup() {
    [ -z "$TEMP_ROOT" ] || rm -rf "$TEMP_ROOT"
}

trap cleanup 0 HUP INT TERM

usage() {
    sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'
}

parse_arguments() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --home)
                shift
                [ $# -gt 0 ] || die "--home 需要一个目录参数"
                HOME_SET=1
                HOME_DIR="$1"
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

[ $# -gt 0 ] || die "需要指定 install"
ACTION="$1"
shift

case "$ACTION" in
    install) parse_arguments "$@" ;;
    -h|--help)
        usage
        exit 0
        ;;
    *) die "未知动作: $ACTION" ;;
esac

git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1 || \
    die "脚本必须在 MDF Git 仓库中运行"
git -C "$SCRIPT_DIR" cat-file -e "HEAD:skills/mdf" 2>/dev/null || \
    die "当前 commit 中没有 skills/mdf"

source_status=$(git -C "$SCRIPT_DIR" status --porcelain)
[ -z "$source_status" ] || die "MDF 源仓库工作区不干净，无法安装"
SOURCE_COMMIT=$(git -C "$SCRIPT_DIR" rev-parse HEAD)

TEMP_ROOT=$(mktemp -d)
mkdir "$TEMP_ROOT/skill"
git -C "$SCRIPT_DIR" archive --format=tar "$SOURCE_COMMIT:skills/mdf" | \
    tar -x -C "$TEMP_ROOT/skill"

PYTHON=${MDF_PYTHON:-python3}

set -- "$PYTHON" -B "$TEMP_ROOT/skill/scripts/mdf_launcher.py" install-payload \
    --revision "$SOURCE_COMMIT" --payload "$TEMP_ROOT/skill"
if [ "$HOME_SET" -eq 1 ]; then
    set -- "$@" --home "$HOME_DIR"
fi
"$@"
