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


# ---- 看门狗模式 ----

_WATCHDOG_ENV_VAR = "DSV4CC_WATCHDOG_CHILD"
_WATCHDOG_DEFAULT_MAX_RESTARTS = 5
_WATCHDOG_DEFAULT_RESTART_DELAY = 2
_WATCHDOG_DEFAULT_POLL_INTERVAL = 0.5


def _get_watchdog_config() -> tuple[int, int, float]:
    """从环境变量读取看门狗配置。"""
    max_restarts = int(os.getenv("PROXY_WATCHDOG_MAX_RESTARTS", str(_WATCHDOG_DEFAULT_MAX_RESTARTS)))
    restart_delay = int(os.getenv("PROXY_WATCHDOG_RESTART_DELAY", str(_WATCHDOG_DEFAULT_RESTART_DELAY)))
    poll_interval = float(os.getenv("PROXY_WATCHDOG_POLL_INTERVAL", str(_WATCHDOG_DEFAULT_POLL_INTERVAL)))
    return max_restarts, restart_delay, poll_interval


def _terminate_process(proc: subprocess.Popen) -> None:
    """跨平台安全的进程终止 (POSIX: SIGTERM; Windows: TerminateProcess)。"""
    try:
        proc.terminate()
    except ProcessLookupError:
        pass


def _kill_process(proc: subprocess.Popen) -> None:
    """跨平台安全的强制杀进程 (POSIX: SIGKILL; Windows: TerminateProcess)。"""
    try:
        proc.kill()
    except ProcessLookupError:
        pass


def _cleanup(pidfile: str, expected_pid: int | None = None) -> None:
    """清理 PID 文件。若提供 expected_pid，则校验文件内容匹配后才删除。"""
    try:
        if expected_pid is not None:
            with open(pidfile) as f:
                current = int(f.read().strip())
            if current != expected_pid:
                logger.warning(
                    "PID file changed, not removing: expected %d got %d",
                    expected_pid, current,
                )
                return
        os.unlink(pidfile)
    except FileNotFoundError:
        pass
    except (ValueError, OSError):
        logger.warning("PID file corrupted, removing anyway: %s", pidfile)
        try:
            os.unlink(pidfile)
        except FileNotFoundError:
            pass


def _reader_thread(proc: subprocess.Popen, shutdown_flag: dict) -> None:
    """后台消费子进程 stdout，防止管道缓冲区填满导致子进程阻塞。"""
    try:
        for line in proc.stdout:
            if shutdown_flag.get("shutdown"):
                break
            logger.debug("[child] %s", line.rstrip().decode("utf-8", errors="replace"))
    except Exception:
        pass  # 管道关闭时静默退出


def _graceful_shutdown_child(proc: subprocess.Popen) -> None:
    """优雅关闭子进程: terminate → 等待 5s → kill。"""
    _terminate_process(proc)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("Child did not exit, force killing...")
        _kill_process(proc)
        proc.wait(timeout=2)


def _watchdog_main(args):
    """看门狗父进程——生成子进程并监控崩溃重启。"""
    pidfile = args.pidfile
    max_restarts, restart_delay, poll_interval = _get_watchdog_config()

    # 保留原有实例检查逻辑 (防止 PID 冲突)
    if os.path.exists(pidfile):
        try:
            with open(pidfile) as f:
                existing_pid = int(f.read().strip())
            if os.name == "nt":
                # Windows: os.kill(pid, 0) 会直接抛异常，无法用 SIG_0 探活。
                # 使用 WaitForSingleObject 成本较高，此处做保守处理——
                # 若 PID 文件存在则假定实例存活，防止重复启动。
                logger.warning(
                    "PID file exists (PID %d) on Windows — assuming instance alive, exiting.",
                    existing_pid,
                )
                sys.exit(1)
            os.kill(existing_pid, 0)  # Unix 探活
            logger.warning("Proxy already running (PID %d), use --stop first", existing_pid)
            sys.exit(1)
        except (OSError, ValueError):
            os.unlink(pidfile)

    # 写入看门狗 PID
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))

    # 注册信号处理
    shutdown_flag = {"shutdown": False}

    def _on_signal(signum, frame):
        shutdown_flag["shutdown"] = True
        logger.info("Watchdog received signal %s, initiating shutdown...", signum)

    # 跨平台信号注册: Windows 不支持 SIGTERM
    signal.signal(signal.SIGINT, _on_signal)
    try:
        signal.signal(signal.SIGTERM, _on_signal)
    except AttributeError:
        pass  # Windows: SIGTERM 不存在，SIGINT 已覆盖 Ctrl+C

    # 子进程环境与命令行. 子进程通过 DSV4CC_WATCHDOG_CHILD=1 识别身份.
    child_env = os.environ.copy()
    child_env[_WATCHDOG_ENV_VAR] = "1"
    child_cmd = [sys.executable, "-m", "dsv4_cc_proxy", "--pidfile", pidfile]

    restart_count = 0
    max_attempts = max_restarts + 1  # 初始启动 + N 次重启
    while not shutdown_flag["shutdown"] and restart_count < max_attempts:
        logger.info("Starting proxy child (attempt %d/%d)", restart_count + 1, max_attempts)

        proc = subprocess.Popen(
            child_cmd, env=child_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )

        # 启动后台线程消费子进程输出，防止管道阻塞
        reader = threading.Thread(target=_reader_thread, args=(proc, shutdown_flag), daemon=True)
        reader.start()

        # 轮询子进程存活
        while not shutdown_flag["shutdown"]:
            if proc.poll() is not None:
                break  # 子进程退出
            time.sleep(poll_interval)

        reader.join(timeout=1)  # 等待 reader 线程自然退出

        if shutdown_flag["shutdown"]:
            _graceful_shutdown_child(proc)
            break

        # 子进程意外退出
        restart_count += 1
        if restart_count >= max_restarts:
            logger.critical("Watchdog: child crashed %d times (max %d), giving up.",
                            restart_count, max_restarts)
            sys.stderr.write(
                f"[FATAL] Proxy crashed {restart_count} times (max {max_restarts}). Exiting.\n"
            )
            break

        logger.warning("Watchdog: child exited (code %d), restarting in %ds...",
                       proc.returncode, restart_delay)
        time.sleep(restart_delay)

    _cleanup(pidfile)


def _stop(pidfile: str):
    """停止代理：读取 PID 文件 → terminate → 等待 → kill（超时则强制杀）。

    跨平台兼容：
      - Unix: SIGTERM → 探活×10(共5s) → SIGKILL
      - Windows: 跳过 SIGTERM(无优雅关闭语义) → 直接 SIGKILL
    PID 清理前会校验 PID 文件内容，防止误删被回收重用的 PID 文件。
    """
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

    # 跨平台 terminate: Unix SIGTERM, Windows 跳过
    _try_terminate(pid)

    # 等待进程退出 (最多 5s)
    for _ in range(10):
        time.sleep(0.5)
        if not _is_process_alive(pid):
            logger.info("Proxy stopped gracefully")
            _cleanup(pidfile, expected_pid=pid)
            return

    logger.warning("Graceful shutdown timed out, force killing...")
    _try_kill(pid)
    _cleanup(pidfile, expected_pid=pid)
    logger.info("Proxy stopped (forced)")


def _is_process_alive(pid: int) -> bool:
    """跨平台进程存活检测。"""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _try_terminate(pid: int) -> None:
    """跨平台 terminate 进程 (POSIX: SIGTERM; Windows: 不支持优雅关闭)。"""
    if os.name == "nt":
        # Windows 无 SIGTERM 语义，os.kill(pid, signal.SIGTERM) 等价 SIGKILL，
        # 此处跳过以避免误导——由上层循环探活 + _try_kill 处理。
        logger.debug("Windows: no graceful shutdown support, skip SIGTERM for PID %d", pid)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass


def _try_kill(pid: int) -> None:
    """跨平台 kill 进程 (POSIX: SIGKILL; Windows: 见 _try_terminate)。"""
    try:
        os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError, AttributeError):
        pass


def main():
    parser = argparse.ArgumentParser(description="DeepSeek Thinking Proxy")
    parser.add_argument(
        "--stop", action="store_true", help="Stop running proxy"
    )
    parser.add_argument(
        "--watchdog", action="store_true",
        help="Enable watchdog mode: monitor child process and auto-restart on crash",
    )
    parser.add_argument(
        "--pidfile", default=PIDFILE_DEFAULT,
        help=f"PID file path (default: {PIDFILE_DEFAULT})",
    )
    args = parser.parse_args()

    if args.stop:
        _stop(args.pidfile)
        return

    if args.watchdog:
        _watchdog_main(args)
        return

    # 看门狗子进程: 跳过 PID 文件管理 (由父进程负责)
    is_watchdog_child = os.environ.get(_WATCHDOG_ENV_VAR) == "1"
    pidfile = args.pidfile
    port = _get_port()

    # 端口冲突提前检测 (避免看门狗重启循环)
    if not _check_port_available(HOST, port):
        logger.critical("Port %d is already in use.", port)
        sys.stderr.write(f"[FATAL] Port {port} already in use. Stop the other process first.\n")
        sys.stderr.flush()
        sys.exit(1)

    # 检查是否已有实例在运行 (看门狗子进程跳过)
    if not is_watchdog_child and os.path.exists(pidfile):
        with open(pidfile) as f:
            try:
                pid = int(f.read().strip())
                os.kill(pid, 0)
                logger.warning("Proxy already running (PID %d), use --stop first", pid)
                sys.exit(1)
            except (OSError, ValueError):
                os.unlink(pidfile)

    # 写入 PID 文件 (看门狗子进程跳过)
    if not is_watchdog_child:
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
        if not is_watchdog_child:
            try:
                os.unlink(pidfile)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
