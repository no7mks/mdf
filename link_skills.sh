#!/bin/sh
# 把本仓库 skills/ 下的每个 skill 软链到各类 AI Agent 的 skills 目录。
#
# 用法示例：
#   /path/to/link_skills.sh                # 链接到当前所在的本地仓库
#   /path/to/link_skills.sh cursor claude  # 只链接指定 agent
#   /path/to/link_skills.sh 龙虾            # 支持中文别名
#   ./link_skills.sh --global              # 链接到所有已知 agent（全局 ~/.xxx/skills）
#   ./link_skills.sh cursor --project DIR  # 链到指定项目的 .<agent>/skills
#   ./link_skills.sh --dry-run             # 只预览，不实际操作
#   ./link_skills.sh --unlink              # 移除本仓库创建的软链
#   ./link_skills.sh --list                # 列出已知 agent 与目标目录
#
# 兼容 POSIX sh（无需 Python、无需 bash 关联数组）。

set -eu

# 仓库根目录 & skills 源目录（取脚本所在目录的绝对路径）
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SKILLS_SRC="$SCRIPT_DIR/skills"
CURRENT_DIR=$(pwd -P)

# 已知 agent 列表；调整/新增 agent 时改这两处：ALL_AGENTS 和 agent_dir()
ALL_AGENTS="claude cursor kiro codex openclaw"

# agent -> 相对 home（或 --project）的 skills 目录
agent_dir() {
    case "$1" in
        claude)   echo ".claude/skills" ;;    # Claude Code / Claude Desktop
        cursor)   echo ".cursor/skills" ;;    # Cursor（个人级，跨项目）
        kiro)     echo ".kiro/skills" ;;      # Kiro
        codex)    echo ".codex/skills" ;;     # OpenAI Codex CLI
        openclaw) echo ".openclaw/skills" ;;  # OpenClaw（龙虾）全局共享
        *)        return 1 ;;
    esac
}

# 中文别名 -> 规范名
resolve_alias() {
    case "$1" in
        龙虾) echo "openclaw" ;;
        *)    echo "$1" ;;
    esac
}

# ---- 参数解析 ----
DRY_RUN=0
UNLINK=0
LIST=0
GLOBAL=0
PROJECT=""
SELECTED=""

die() { echo "$1" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --unlink)  UNLINK=1 ;;
        --list)    LIST=1 ;;
        --global)  GLOBAL=1 ;;
        --project)
            shift
            [ $# -gt 0 ] || die "--project 需要一个目录参数"
            PROJECT=$(cd "$1" 2>/dev/null && pwd) || die "找不到项目目录: $1"
            ;;
        -h|--help)
            sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        -*) die "未知选项: $1" ;;
        *)
            key=$(resolve_alias "$1")
            if ! agent_dir "$key" >/dev/null 2>&1; then
                die "未知 agent: $1（可用: $ALL_AGENTS；别名: 龙虾=openclaw）"
            fi
            SELECTED="$SELECTED $key"
            ;;
    esac
    shift
done

# --global 与 --project 指向不同安装范围，不能同时使用
[ "$GLOBAL" -eq 0 ] || [ -z "$PROJECT" ] || die "--global 与 --project 不能同时使用"

# 默认安装到命令执行目录，但不能把 skill 源仓库安装回自身
if [ "$GLOBAL" -eq 0 ] && [ -z "$PROJECT" ] && [ "$CURRENT_DIR" = "$SCRIPT_DIR" ]; then
    die "不能把 skill 安装回源仓库自身。请切换到目标仓库后执行 $SCRIPT_DIR/link_skills.sh，或使用 --project DIR / --global"
fi

# 目标基目录：默认命令执行目录；--project 指定其他仓库；--global 使用 home
target_base() {
    if [ "$GLOBAL" -eq 1 ]; then
        echo "$HOME"
    elif [ -n "$PROJECT" ]; then
        echo "$PROJECT"
    else
        echo "$CURRENT_DIR"
    fi
}

# ---- --list ----
if [ "$LIST" -eq 1 ]; then
    echo "已知 agent 及目标 skills 目录："
    base=$(target_base)
    for a in $ALL_AGENTS; do
        printf '  %-10s -> %s/%s\n' "$a" "$base" "$(agent_dir "$a")"
    done
    echo "别名：龙虾=openclaw"
    exit 0
fi

# 未指定则全部
[ -n "$SELECTED" ] || SELECTED="$ALL_AGENTS"

# ---- 收集 skills（含 SKILL.md 的子目录）----
[ -d "$SKILLS_SRC" ] || die "找不到 skills 源目录: $SKILLS_SRC"
SKILLS=""
for d in "$SKILLS_SRC"/*/; do
    [ -f "${d}SKILL.md" ] || continue
    name=$(basename "$d")
    SKILLS="$SKILLS $name"
done
[ -n "$SKILLS" ] || die "$SKILLS_SRC 下没有发现任何含 SKILL.md 的技能"

# ---- 提示 ----
if [ "$UNLINK" -eq 1 ]; then verb="移除软链"; else verb="创建软链"; fi
if [ "$GLOBAL" -eq 1 ]; then
    scope="全局 (home)"
elif [ -n "$PROJECT" ]; then
    scope="项目 $PROJECT"
else
    scope="本地仓库 $CURRENT_DIR"
fi
if [ "$DRY_RUN" -eq 1 ]; then mode="预览模式"; else mode="执行"; fi
echo "$verb · 范围: $scope · $mode"
echo "发现 skill:$SKILLS"
echo

# ---- 处理单个 skill ----
link_one() {
    src="$1"; dst="$2"; name=$(basename "$src")

    if [ "$UNLINK" -eq 1 ]; then
        if [ -L "$dst" ]; then
            if [ "$(readlink "$dst")" = "$src" ]; then
                [ "$DRY_RUN" -eq 1 ] || rm "$dst"
                echo "  - 移除 $dst"
            else
                echo "  ~ 跳过 ${dst}（指向其他位置，非本仓库）"
            fi
        elif [ -e "$dst" ]; then
            echo "  ~ 跳过 ${dst}（是真实目录/文件，非软链）"
        else
            echo "  · 无软链 $name"
        fi
        return
    fi

    # 创建
    if [ -L "$dst" ]; then
        if [ "$(readlink "$dst")" = "$src" ]; then
            echo "  = 已存在 $name"
        else
            [ "$DRY_RUN" -eq 1 ] || { rm "$dst"; ln -s "$src" "$dst"; }
            echo "  ↻ 更新 $name"
        fi
    elif [ -e "$dst" ]; then
        echo "  ! 跳过 ${name}（$dst 已存在且不是软链，请手动处理）"
    else
        if [ "$DRY_RUN" -eq 0 ]; then
            mkdir -p "$(dirname "$dst")"
            ln -s "$src" "$dst"
        fi
        echo "  + 链接 $name -> $dst"
    fi
}

# ---- 主循环 ----
base=$(target_base)
for agent in $SELECTED; do
    tdir="$base/$(agent_dir "$agent")"
    echo "[$agent] $tdir"
    for name in $SKILLS; do
        link_one "$SKILLS_SRC/$name" "$tdir/$name"
    done
    echo
done

if [ "$DRY_RUN" -eq 1 ]; then
    echo "（预览模式，未做任何改动。去掉 --dry-run 即可执行。）"
fi
