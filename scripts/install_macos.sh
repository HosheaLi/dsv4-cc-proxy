#!/bin/bash
# dsv4-cc-proxy macOS LaunchAgent 安装脚本
#
# 用法:
#   bash scripts/install_macos.sh                # 自动检测 Python (优先项目 venv)
#   bash scripts/install_macos.sh /path/to/python # 手动指定 Python 路径
#
# 检测顺序:
#   1. 命令行参数指定
#   2. 项目 .venv/bin/python3 (推荐)
#   3. 系统 PATH 中的 python3 (可能被 Homebrew 外部管理限制)

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

PYTHON=""
LOG_DIR="$HOME/.claude/proxy"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python3"

# ---- 检测 Python 路径 ----
find_python() {
    # 1. 命令行指定
    if [ $# -ge 1 ]; then
        PYTHON="$1"
        return
    fi

    # 2. 项目 venv (最优先，不受 Homebrew 外部管理限制)
    if [ -x "$VENV_PYTHON" ]; then
        PYTHON="$VENV_PYTHON"
        return
    fi

    # 3. PATH 中的 python3
    local path_python
    path_python=$(which python3 2>/dev/null || echo "")
    if [ -n "$path_python" ]; then
        PYTHON="$path_python"
        return
    fi

    PYTHON=""
}

find_python "$@"

if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    echo -e "${RED}[ERROR] Python 3 not found.${NC}"
    echo "Options:"
    echo "  1. Create a venv:      python3 -m venv $PROJECT_DIR/.venv"
    echo "  2. Specify manually:    bash $0 /path/to/python3"
    echo "  3. Install Python 3.11+ from https://www.python.org/downloads/"
    exit 1
fi

PY_VER=$("$PYTHON" --version 2>&1)
echo -e "${GREEN}[OK] Using $PY_VER at $PYTHON${NC}"

# ---- 检测是否为 Homebrew 管理的外部 Python ----
is_homebrew_external() {
    local py="$1"
    # Homebrew Python 位于 /opt/homebrew 或 /usr/local/opt，且标记为 externally-managed
    if [[ "$py" == /opt/homebrew/* ]] || [[ "$py" == /usr/local/opt/* ]]; then
        if "$py" -m pip install --dry-run does-not-exist 2>&1 | grep -qi "externally-managed"; then
            return 0
        fi
    fi
    return 1
}

# ---- 验证 dsv4-cc-proxy 可用 ----
ensure_installed() {
    local py="$1"

    if "$py" -m dsv4_cc_proxy --help >/dev/null 2>&1; then
        return 0
    fi

    echo -e "${YELLOW}[INFO] dsv4-cc-proxy not found for $py, installing...${NC}"

    # 尝试 install
    if "$py" -m pip install dsv4-cc-proxy 2>/dev/null; then
        echo -e "${GREEN}[OK] dsv4-cc-proxy installed${NC}"
        return 0
    fi

    # 安装失败: 检测原因
    if is_homebrew_external "$py"; then
        echo -e "${YELLOW}[WARN] $py is Homebrew-managed (externally-managed), cannot pip install${NC}"

        # 回退到项目 venv: 如果不存在则创建
        if [ ! -x "$VENV_PYTHON" ]; then
            echo -e "${CYAN}[INFO] Creating project venv at $PROJECT_DIR/.venv ...${NC}"
            "$py" -m venv "$PROJECT_DIR/.venv" || {
                echo -e "${RED}[ERROR] Failed to create venv${NC}"
                exit 1
            }
        fi

        echo -e "${CYAN}[INFO] Installing dsv4-cc-proxy into project venv...${NC}"
        "$VENV_PYTHON" -m pip install dsv4-cc-proxy || {
            echo -e "${RED}[ERROR] Failed to install into venv${NC}"
            echo "Try manually: $VENV_PYTHON -m pip install dsv4-cc-proxy"
            exit 1
        }

        PYTHON="$VENV_PYTHON"
        echo -e "${GREEN}[OK] Switched to venv Python: $PYTHON${NC}"
        return 0
    fi

    echo -e "${RED}[ERROR] Failed to install dsv4-cc-proxy.${NC}"
    echo "Possible causes:"
    echo "  - pip not available: $py -m pip install dsv4-cc-proxy"
    echo "  - externa-management: create a venv and run again"
    exit 1
}

ensure_installed "$PYTHON"

# ---- 创建日志目录 ----
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR" || {
        echo -e "${RED}[ERROR] Cannot create log directory: $LOG_DIR${NC}"
        exit 1
    }
    echo -e "${GREEN}[OK] Created log directory: $LOG_DIR${NC}"
fi

# ---- 生成 plist ----
TEMPLATE="$SCRIPT_DIR/com.deepseek.thinking-proxy.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.deepseek.thinking-proxy.plist"

if [ ! -f "$TEMPLATE" ]; then
    echo -e "${RED}[ERROR] plist template not found: $TEMPLATE${NC}"
    exit 1
fi

sed -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__LOG_DIR__|$LOG_DIR|g" \
    "$TEMPLATE" > "$PLIST_DEST"

echo -e "${GREEN}[OK] plist installed: $PLIST_DEST${NC}"

# ---- 卸载旧版本 (如果存在) ----
launchctl unload "$PLIST_DEST" 2>/dev/null || true

# ---- 加载 ----
launchctl load "$PLIST_DEST"
echo -e "${GREEN}[OK] LaunchAgent loaded${NC}"

# ---- 验证 ----
sleep 2
if curl -sf http://localhost:16889/health >/dev/null 2>&1; then
    echo -e "${GREEN}[OK] Proxy is running!${NC}"
    echo ""
    echo "  Health response:"
    curl -s http://localhost:16889/health | "$PYTHON" -m json.tool 2>/dev/null || true
else
    echo -e "${YELLOW}[WARN] Health check failed.${NC}"
    echo "  Check logs:  tail -f $LOG_DIR/proxy.log"
    echo "  Service:     launchctl list | grep deepseek"
    echo "  Test:        curl http://localhost:16889/health"
fi

echo ""
echo -e "${CYAN}=== Installation complete ===${NC}"
echo -e "  Python:   ${CYAN}$PYTHON${NC}"
echo -e "  Logs:     ${CYAN}tail -f $LOG_DIR/proxy.log${NC}"
echo -e "  Stop:     ${CYAN}launchctl unload $PLIST_DEST${NC}"
echo -e "  Restart:  ${CYAN}launchctl unload $PLIST_DEST && launchctl load $PLIST_DEST${NC}"
echo -e "  Configure: ${CYAN}ANTHROPIC_BASE_URL=http://localhost:16889${NC}"
