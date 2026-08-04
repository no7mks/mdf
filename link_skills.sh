#!/bin/sh
# 把本仓库 skills/ 下的当前 MDF skill set 深拷贝到各类 AI Agent 的 skills 目录。
# 每次安装前清除目标目录中的旧 mdf-* Skill 和 mdf；不触碰目标仓库的 .mdf/ 或 docs/。
#
# 用法示例：
#   /path/to/link_skills.sh                # 安装到当前所在的本地仓库
#   /path/to/link_skills.sh cursor claude  # 只安装到指定 agent
#   /path/to/link_skills.sh 龙虾            # 支持中文别名
#   ./link_skills.sh --global              # 安装到所有已知 agent（全局 ~/.xxx/skills）
#   ./link_skills.sh cursor --project DIR  # 安装到指定项目的 .<agent>/skills
#   ./link_skills.sh --dry-run             # 只预览，不实际操作
#   ./link_skills.sh --unlink              # 移除目标范围内全部 MDF Skill
#   ./link_skills.sh --list                # 列出已知 agent 与目标目录
#
# 兼容 POSIX sh（无需 Python、无需 bash 关联数组）。

set -eu

# 仓库根目录 & skills 源目录（取脚本所在目录的绝对路径）
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SKILLS_SRC="$SCRIPT_DIR/skills"
CURRENT_DIR=$(pwd -P)

# 已知 agent 列表；调整/新增 agent 时改这两处：ALL_AGENTS 和 agent_dir()
ALL_AGENTS="claude cursor kiro codex kimi openclaw"

# agent -> 相对 home（或 --project）的 skills 目录
agent_dir() {
    case "$1" in
        claude)   echo ".claude/skills" ;;    # Claude Code / Claude Desktop
        cursor)   echo ".cursor/skills" ;;    # Cursor（个人级，跨项目）
        kiro)     echo ".kiro/skills" ;;      # Kiro
        codex)    echo ".codex/skills" ;;     # OpenAI Codex CLI
        kimi)     echo ".agents/skills" ;; # Kimi Code
        openclaw) echo ".openclaw/skills" ;;  # OpenClaw（龙虾）全局共享
        *)        return 1 ;;
    esac
}

# 中文别名 -> 规范名
resolve_alias() {
    case "$1" in
        龙虾) echo "openclaw" ;;
        kimi-code) echo "kimi" ;;
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
                die "未知 agent: $1（可用: $ALL_AGENTS；别名: 龙虾、kimi-code）"
            fi
            SELECTED="$SELECTED $key"
            ;;
    esac
    shift
done

# --global 与 --project 指向不同安装范围，不能同时使用
[ "$GLOBAL" -eq 0 ] || [ -z "$PROJECT" ] || die "--global 与 --project 不能同时使用"

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
    echo "别名：龙虾=openclaw，kimi-code=kimi"
    exit 0
fi

# 默认安装到命令执行目录，但不能把 skill 源仓库安装回自身。
if [ "$GLOBAL" -eq 0 ] && [ -z "$PROJECT" ] && \
    [ "$CURRENT_DIR" = "$SCRIPT_DIR" ]; then
    die "不能把 skill 安装回源仓库自身。请切换到目标仓库后执行 \
$SCRIPT_DIR/link_skills.sh，或使用 --project DIR / --global"
fi

# 未指定则全部
[ -n "$SELECTED" ] || SELECTED="$ALL_AGENTS"

# ---- 收集唯一 MDF Skill ----
[ -d "$SKILLS_SRC" ] || die "找不到 skills 源目录: $SKILLS_SRC"
SKILLS="mdf"
[ -f "$SKILLS_SRC/$SKILLS/SKILL.md" ] || \
    die "$SKILLS_SRC/$SKILLS 下没有发现 SKILL.md"

# ---- 提示 ----
if [ "$UNLINK" -eq 1 ]; then verb="移除 MDF Skill"; else verb="深拷贝 MDF Skill"; fi
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

purge_mdf_skills() {
    target_dir="$1"
    [ -d "$target_dir" ] || return 0
    found=0
    for installed in "$target_dir"/mdf-* "$target_dir"/mdf; do
        [ -e "$installed" ] || [ -L "$installed" ] || continue
        found=1
        if [ "$DRY_RUN" -eq 1 ]; then
            echo "  - 将卸载 $installed"
        else
            rm -rf "$installed"
            echo "  - 已卸载 $installed"
        fi
    done
    [ "$found" -eq 1 ] || echo "  · 未发现已安装的 MDF Skill"
}

# ---- 安装单个 skill ----
copy_one() {
    src="$1"; dst="$2"; name=$(basename "$src")

    if [ "$DRY_RUN" -eq 0 ]; then
        mkdir -p "$(dirname "$dst")"
        cp -R "$src" "$dst"
    fi
    echo "  + 复制 $name -> $dst"
}

# ---- 主循环 ----
base=$(target_base)
for agent in $SELECTED; do
    tdir="$base/$(agent_dir "$agent")"
    echo "[$agent] $tdir"
    if [ "$UNLINK" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
        mkdir -p "$tdir"
    fi
    purge_mdf_skills "$tdir"
    [ "$UNLINK" -eq 0 ] || continue
    for name in $SKILLS; do
        copy_one "$SKILLS_SRC/$name" "$tdir/$name"
    done
    echo
done

if [ "$DRY_RUN" -eq 1 ]; then
    echo "（预览模式，未做任何改动。去掉 --dry-run 即可执行。）"
fi
