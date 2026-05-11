# dsv4-cc-proxy CLI 入口


import argparse
import os
import signal
import sys
import time

import uvicorn

from dsv4_cc_proxy._version import VERSION
from dsv4_cc_proxy.proxy import DUMP_DIR, HOST, LOG_LEVEL, PORT

PIDFILE_DEFAULT = "/tmp/dsv4-cc-proxy.pid"


def _stop(pidfile: str):
    """停止代理：读取 PID 文件 → SIGTERM → 等待 → SIGKILL（超时则强制杀）。"""
    if not os.path.exists(pidfile):
        print(f"Proxy not running (PID file not found: {pidfile})")
        sys.exit(1)

    with open(pidfile) as f:
        pid = int(f.read().strip())

    print(f"Stopping dsv4-cc-proxy (PID {pid})...")

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("Process not found, cleaning up PID file")
        os.unlink(pidfile)
        return

    for _ in range(10):
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            print("Proxy stopped gracefully")
            try:
                os.unlink(pidfile)
            except FileNotFoundError:
                pass
            return

    print("Graceful shutdown timed out, sending SIGKILL...")
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        os.unlink(pidfile)
    except FileNotFoundError:
        pass
    print("Proxy stopped (forced)")


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

    # 检查是否已有实例在运行
    if os.path.exists(pidfile):
        with open(pidfile) as f:
            try:
                pid = int(f.read().strip())
                os.kill(pid, 0)
                print(f"Proxy already running (PID {pid}), use --stop first")
                sys.exit(1)
            except (OSError, ValueError):
                os.unlink(pidfile)

    # 写入 PID 文件
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))

    print(f"DeepSeek Thinking Proxy v{VERSION} → {HOST}:{PORT} (PID {os.getpid()})")
    if DUMP_DIR:
        print(f"⚠ DUMP mode: {DUMP_DIR}")
    try:
        uvicorn.run(
            "dsv4_cc_proxy.proxy:create_app",
            host=HOST,
            port=PORT,
            log_level=LOG_LEVEL,
            factory=True,
        )
    finally:
        try:
            os.unlink(pidfile)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
