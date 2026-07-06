# dsv4-cc-proxy CLI 入口
#
# 环境变量:
#   PROXY_WATCHDOG_MAX_RESTARTS  看门狗放弃前最大重启次数 (默认 5)
#   PROXY_WATCHDOG_RESTART_DELAY  重启间隔秒数 (默认 2)
#   PROXY_WATCHDOG_POLL_INTERVAL  子进程存活轮询间隔秒数 (默认 0.5)
#
# 已知限制:
#   - Windows 上 --stop 不支持 (需用 Ctrl+C 或 taskkill)
#   - Windows 上 terminate() = TerminateProcess，非优雅关闭


import argparse
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback

import uvicorn

from dsv4_cc_proxy._version import VERSION
from dsv4_cc_proxy.proxy import DUMP_DIR, HOST, LOG_LEVEL, _get_port

logger = logging.getLogger("deepseek-proxy")


def _default_pidfile() -> str:
    """返回当前平台默认的 PID 文件路径。"""
    if os.name == "nt":
        temp_dir = os.environ.get("TEMP") or os.environ.get("TMP")
        if not temp_dir:
            temp_dir = os.path.expanduser("~")
        return os.path.join(temp_dir, "dsv4-cc-proxy.pid")
    return "/tmp/dsv4-cc-proxy.pid"


PIDFILE_DEFAULT = _default_pidfile()


def _check_port_available(host: str, port: int) -> bool:
    """尝试绑定端口以检测可用性。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def _log_windows_event(message: str) -> None:
    """尽力写入 Windows Event Log (仅 Windows 平台)。"""
    if os.name != "nt":
        return
    try:
        safe_msg = message.replace("'", "''")     # PowerShell 单引号转义
        safe_msg = safe_msg.replace("\n", " ")     # 去除换行
        safe_msg = safe_msg[:1000]                 # 截断过长消息
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Write-EventLog -LogName Application -Source 'dsv4-cc-proxy' "
             f"-EntryType Error -EventId 1000 -Message '{safe_msg}'"],
            capture_output=True, timeout=5, check=False,
        )
    except Exception:
        pass  # best-effort: Event Source 可能不存在, 静默忽略


def _stop(pidfile: str):
    """停止代理：读取 PID 文件 → SIGTERM → 等待 → SIGKILL（超时则强制杀）。"""
    if not os.path.exists(pidfile):
        logger.warning("Proxy not running (PID file not found: %s)", pidfile)
        sys.exit(1)

    try:
        with open(pidfile) as f:
            pid = int(f.read().strip())
    except (ValueError, IOError):
        logger.error("PID file corrupted: %s", pidfile)
        sys.exit(1)

    logger.info("Stopping dsv4-cc-proxy (PID %d)...", pid)

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        logger.info("Process not found, cleaning up PID file")
        os.unlink(pidfile)
        return

    for _ in range(10):
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            logger.info("Proxy stopped gracefully")
            try:
                os.unlink(pidfile)
            except FileNotFoundError:
                pass
            return

    logger.warning("Graceful shutdown timed out, sending SIGKILL...")
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        os.unlink(pidfile)
    except FileNotFoundError:
        pass
    logger.info("Proxy stopped (forced)")


def main():
    parser = argparse.ArgumentParser(description="DeepSeek Thinking Proxy")
    parser.add_argument(
        "--stop", action="store_true", help="Stop running proxy"
    )
    parser.add_argument(
        "--pidfile", default=PIDFILE_DEFAULT,
        help=f"PID file path (default: {PIDFILE_DEFAULT})",
    )
    args = parser.parse_args()

    if args.stop:
        _stop(args.pidfile)
        return

    pidfile = args.pidfile
    port = _get_port()

    # 端口冲突提前检测 (避免看门狗重启循环)
    if not _check_port_available(HOST, port):
        logger.critical("Port %d is already in use.", port)
        sys.stderr.write(f"[FATAL] Port {port} already in use. Stop the other process first.\n")
        sys.stderr.flush()
        sys.exit(1)

    # 检查是否已有实例在运行
    if os.path.exists(pidfile):
        with open(pidfile) as f:
            try:
                pid = int(f.read().strip())
                os.kill(pid, 0)
                logger.warning("Proxy already running (PID %d), use --stop first", pid)
                sys.exit(1)
            except (OSError, ValueError):
                os.unlink(pidfile)

    # 写入 PID 文件
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))

    logger.info("DeepSeek Thinking Proxy v%s → %s:%d (PID %d)", VERSION, HOST, port, os.getpid())
    if DUMP_DIR:
        logger.warning("⚠ DUMP mode: %s", DUMP_DIR)
    try:
        uvicorn.run(
            "dsv4_cc_proxy.proxy:create_app",
            host=HOST,
            port=port,
            log_level=LOG_LEVEL,
            factory=True,
        )
    except SystemExit:
        raise
    except Exception:
        logger.critical("Proxy startup failed", exc_info=True)
        msg = traceback.format_exc()
        sys.stderr.write(f"[FATAL] {msg}\n")
        sys.stderr.flush()
        if os.name == "nt":
            _log_windows_event(str(sys.exc_info()[1]))
        raise
    finally:
        try:
            os.unlink(pidfile)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
