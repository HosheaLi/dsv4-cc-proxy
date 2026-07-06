#!/bin/bash
# dsv4-cc-proxy macOS LaunchAgent 安装脚本
#
# 用法:
#   bash scripts/install_macos.sh                # 自动检测 Python
#   bash scripts/install_macos.sh /path/to/python # 手动指定 Python 路径
#
# 要求: Python 3.11+, dsv4-cc-proxy 已安装 (pip install dsv4-cc-proxy)

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

PYTHON=""
LOG_DIR="$HOME/.claude/proxy"

# ---- 检测 Python 路径 ----
if [ $# -ge 1 ]; then
    PYTHON="$1"
else
    PYTHON=$(which python3 2>/dev/null || echo "")
fi

if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    echo -e "${RED}[ERROR] Python 3 not found.${NC}"
    echo "Install Python 3.11+ from https://www.python.org/downloads/"
    echo "Or specify manually: bash $0 /path/to/python3"
    exit 1
fi

PY_VER=$("$PYTHON" --version 2>&1)
echo -e "${GREEN}[OK] Found $PY_VER at $PYTHON${NC}"

# ---- 验证 dsv4-cc-proxy 可用 ----
if ! "$PYTHON" -m dsv4_cc_proxy --help >/dev/null 2>&1; then
    echo -e "${YELLOW}[INFO] dsv4-cc-proxy not found, installing...${NC}"
    # 检测是否需要 --user (系统 Python 受 SIP 保护)
    PIP_INSTALL="pip install"
    if [[ "$PYTHON" == /usr/bin/python3 ]] || [[ "$PYTHON" == /usr/bin/python ]]; then
        PIP_INSTALL="$PIP_INSTALL --user"
    fi
    "$PYTHON" -m $PIP_INSTALL dsv4-cc-proxy || {
        echo -e "${RED}[ERROR] Failed to install dsv4-cc-proxy.${NC}"
        echo "Try manually: $PYTHON -m pip install dsv4-cc-proxy"
        exit 1
    }
    echo -e "${GREEN}[OK] dsv4-cc-proxy installed${NC}"
fi

# ---- 创建日志目录 ----
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR" || {
        echo -e "${RED}[ERROR] Cannot create log directory: $LOG_DIR${NC}"
        exit 1
    }
    echo -e "${GREEN}[OK] Created log directory: $LOG_DIR${NC}"
fi

# ---- 生成 plist ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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
    echo -e "${GREEN}[OK] Proxy is running! Health endpoint responds.${NC}"
    curl -s http://localhost:16889/health | python3 -m json.tool 2>/dev/null || true
else
    echo -e "${YELLOW}[WARN] Health check failed. Check logs: tail -f $LOG_DIR/proxy.log${NC}"
    echo -e "${YELLOW}       Or: launchctl list | grep deepseek${NC}"
fi

echo ""
echo -e "${CYAN}=== Installation complete ===${NC}"
echo -e "  Service:  ${CYAN}launchctl list com.deepseek.thinking-proxy${NC}"
echo -e "  Logs:     ${CYAN}tail -f $LOG_DIR/proxy.log${NC}"
echo -e "  Stop:     ${CYAN}launchctl unload $PLIST_DEST${NC}"
echo -e "  Configure: ${CYAN}Set ANTHROPIC_BASE_URL=http://localhost:16889 in Claude Code${NC}"
