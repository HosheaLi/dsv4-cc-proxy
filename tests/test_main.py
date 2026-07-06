"""dsv4-cc-proxy CLI 入口单元测试。

覆盖: stop/normal startup/already running/stale pidfile/error handling/
       watchdog mode/windows portability。

遵循纯函数 AAA 模式: Arrange → Act → Assert。

运行: python3 -m pytest tests/test_main.py -v
"""

import signal
import subprocess
from unittest.mock import MagicMock

import pytest


# ============== Phase 1: helper functions ==============


def test_default_pidfile_windows(monkeypatch):
    """Windows 上默认 PID 文件路径使用 %TEMP%。"""
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setenv("TEMP", "C:\\Users\\test\\AppData\\Local\\Temp")

    from dsv4_cc_proxy.__main__ import _default_pidfile

    path = _default_pidfile()
    assert "dsv4-cc-proxy.pid" in path
    assert "AppData" in path


def test_default_pidfile_windows_no_env(monkeypatch):
    """Windows 上 TEMP/TMP 均不存在时 fallback 到用户主目录。"""
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    from dsv4_cc_proxy.__main__ import _default_pidfile

    path = _default_pidfile()
    assert "dsv4-cc-proxy.pid" in path
    assert path != "."  # 不应该 fallback 到当前目录


def test_default_pidfile_unix(monkeypatch):
    """Unix 上默认 PID 文件路径使用 /tmp/。"""
    monkeypatch.setattr("os.name", "posix")

    from dsv4_cc_proxy.__main__ import _default_pidfile

    path = _default_pidfile()
    assert path == "/tmp/dsv4-cc-proxy.pid"


def test_port_available(monkeypatch):
    """_check_port_available 对可用端口返回 True。"""
    from dsv4_cc_proxy.__main__ import _check_port_available
    import socket

    # 找一个可用端口
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    assert _check_port_available("127.0.0.1", port) is True


def test_windows_event_log_non_windows(monkeypatch):
    """非 Windows 上 _log_windows_event 为空操作。"""
    monkeypatch.setattr("os.name", "posix")

    from dsv4_cc_proxy.__main__ import _log_windows_event

    _log_windows_event("test")  # 不应该崩溃


def test_windows_event_log_sanitizes_quotes(monkeypatch):
    """验证 PowerShell 单引号被转义。"""
    monkeypatch.setattr("os.name", "nt")
    run_calls = []

    def mock_run(*args, **kwargs):
        run_calls.append(args[0])

    monkeypatch.setattr("subprocess.run", mock_run)

    from dsv4_cc_proxy.__main__ import _log_windows_event

    _log_windows_event("Error: can't connect")
    assert len(run_calls) == 1
    cmd = " ".join(run_calls[0])
    assert "can''t" in cmd  # 单引号被转义为 ''


def test_stop_pidfile_not_found(monkeypatch):
    """--stop 时 PID 文件不存在 -> sys.exit(1)。"""
    pidfile = "/tmp/nonexistent-dsv4-cc-proxy.pid"
    monkeypatch.setattr("sys.argv", ["proxy.py", "--stop", "--pidfile", pidfile])

    from dsv4_cc_proxy.__main__ import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_stop_normal_sigterm(monkeypatch, tmp_path):
    """--stop 正常流程 -> SIGTERM 发送 -> PID 文件清理。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    pidfile.write_text("99999")

    kill_calls = []

    def mock_kill(pid, sig):
        kill_calls.append((pid, sig))
        if len(kill_calls) == 1:
            return  # SIGTERM 成功
        raise ProcessLookupError()  # 探活发现进程已死

    monkeypatch.setattr("os.kill", mock_kill)
    monkeypatch.setattr("os.unlink", lambda p: None)

    from dsv4_cc_proxy.__main__ import _stop

    _stop(str(pidfile))

    assert len(kill_calls) == 2
    assert kill_calls[0] == (99999, signal.SIGTERM)
    assert kill_calls[1] == (99999, 0)  # SIG_0 探活


def test_stop_already_dead(monkeypatch, tmp_path):
    """--stop 时进程已不存在 -> 清理 PID 文件后返回。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    pidfile.write_text("99999")

    kill_calls = []
    unlink_called = []

    def mock_kill(pid, sig):
        kill_calls.append((pid, sig))
        raise ProcessLookupError()

    def mock_unlink(path):
        unlink_called.append(path)

    monkeypatch.setattr("os.kill", mock_kill)
    monkeypatch.setattr("os.unlink", mock_unlink)

    from dsv4_cc_proxy.__main__ import _stop

    _stop(str(pidfile))

    # 新流程: SIGTERM → SIG_0 (探活: 进程已退出) → 清理
    assert len(kill_calls) == 2
    assert kill_calls[0] == (99999, signal.SIGTERM)
    assert kill_calls[1] == (99999, 0)  # _is_process_alive → 已退出
    assert len(unlink_called) == 1


def test_stop_graceful_timeout(monkeypatch, tmp_path):
    """--stop 时 SIGTERM 超时(5s 未退出) -> SIGKILL 强制杀。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    pidfile.write_text("99999")

    kill_calls = []

    def mock_kill(pid, sig):
        kill_calls.append((pid, sig))

    monkeypatch.setattr("os.kill", mock_kill)
    monkeypatch.setattr("os.unlink", lambda p: None)
    monkeypatch.setattr("time.sleep", lambda s: None)

    from dsv4_cc_proxy.__main__ import _stop

    _stop(str(pidfile))

    # 新流程: SIGTERM → SIG_0×10 (探活: 仍存活) → SIGKILL
    assert len(kill_calls) == 12
    assert kill_calls[0] == (99999, signal.SIGTERM)
    assert kill_calls[-1] == (99999, signal.SIGKILL)
    # 中间 10 次是 SIG_0
    assert all(k == (99999, 0) for k in kill_calls[1:-1])


def test_main_already_running(monkeypatch, tmp_path):
    """启动时 PID 文件存在且进程存活 -> sys.exit(1)。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    pidfile.write_text("99999")

    monkeypatch.setattr("sys.argv", ["proxy.py", "--pidfile", str(pidfile)])
    monkeypatch.setattr("os.kill", lambda pid, sig: None)  # 探活成功

    from dsv4_cc_proxy.__main__ import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_main_stale_pidfile(monkeypatch, tmp_path):
    """启动时 PID 文件存在但进程已死 -> 清理后继续启动。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    pidfile.write_text("99999")

    monkeypatch.setattr("sys.argv", ["proxy.py", "--pidfile", str(pidfile)])
    def mock_kill_oserror(pid, sig):
        raise ProcessLookupError()
    monkeypatch.setattr("os.kill", mock_kill_oserror)
    monkeypatch.setattr("uvicorn.run", lambda *a, **kw: None)
    monkeypatch.setattr("dsv4_cc_proxy.__main__._check_port_available", lambda h, p: True)

    unlink_calls = []

    def mock_unlink(path):
        unlink_calls.append(path)

    monkeypatch.setattr("os.unlink", mock_unlink)

    from dsv4_cc_proxy.__main__ import main

    main()

    # PID 文件被清理（os.unlink 被调用）
    assert len(unlink_calls) >= 1


def test_main_startup(monkeypatch, tmp_path):
    """正常启动 -> uvicorn.run 被正确调用。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"

    monkeypatch.setattr("sys.argv", ["proxy.py", "--pidfile", str(pidfile)])
    monkeypatch.setattr("uvicorn.run", lambda *a, **kw: None)
    monkeypatch.setattr("dsv4_cc_proxy.__main__._check_port_available", lambda h, p: True)

    # 补丁 os.unlink 防止 finally 子句删除 PID 文件
    unlink_calls = []

    def mock_unlink(path):
        unlink_calls.append(path)

    monkeypatch.setattr("os.unlink", mock_unlink)

    from dsv4_cc_proxy.__main__ import main

    main()

    # PID 文件应在运行时存在（finally 中通过 os.unlink 删除）
    # 由于 os.unlink 被补丁，文件应仍然存在
    # 验证 PID 文件中写入了一个整数 PID
    assert pidfile.exists()
    content = pidfile.read_text().strip()
    assert content.isdigit()


def test_main_startup_with_dump(monkeypatch, tmp_path):
    """DUMP_DIR 启用时启动 -> 不崩溃。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"

    monkeypatch.setattr("sys.argv", ["proxy.py", "--pidfile", str(pidfile)])
    monkeypatch.setattr("uvicorn.run", lambda *a, **kw: None)
    monkeypatch.setattr("dsv4_cc_proxy.__main__.DUMP_DIR", "/tmp/dump")
    monkeypatch.setattr("dsv4_cc_proxy.__main__._check_port_available", lambda h, p: True)
    monkeypatch.setattr("os.unlink", lambda p: None)

    from dsv4_cc_proxy.__main__ import main

    # 不应崩溃
    main()


def test_version_importable():
    """VERSION 可导入且为合法 semver 字符串。"""
    import re

    from dsv4_cc_proxy._version import VERSION

    assert isinstance(VERSION, str)
    assert re.match(r"^\d+\.\d+\.\d+", VERSION), f"Invalid semver: {VERSION}"


def test_stop_pidfile_corrupted(monkeypatch, tmp_path):
    """--stop 时 PID 文件内容不是整数 -> 合理错误退出。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    pidfile.write_text("not_a_number")

    monkeypatch.setattr("sys.argv", ["proxy.py", "--stop", "--pidfile", str(pidfile)])

    from dsv4_cc_proxy.__main__ import main

    # _stop 中 int() 失败后显式调用 sys.exit(1)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


# ============== Phase 3: watchdog ==============


class TestWatchdog:
    """dsv4-cc-proxy --watchdog 看门狗模式测试。"""

    def test_terminate_process_calls_terminate(self):
        """_terminate_process 调用 Popen.terminate()。"""
        from dsv4_cc_proxy.__main__ import _terminate_process

        mock_proc = MagicMock(spec=subprocess.Popen)
        _terminate_process(mock_proc)
        mock_proc.terminate.assert_called_once()

    def test_kill_process_calls_kill(self):
        """_kill_process 调用 Popen.kill()。"""
        from dsv4_cc_proxy.__main__ import _kill_process

        mock_proc = MagicMock(spec=subprocess.Popen)
        _kill_process(mock_proc)
        mock_proc.kill.assert_called_once()

    def test_cleanup_removes_pidfile(self, tmp_path):
        """_cleanup 删除 PID 文件。"""
        from dsv4_cc_proxy.__main__ import _cleanup

        pidfile = tmp_path / "test.pid"
        pidfile.write_text("12345")
        _cleanup(str(pidfile))
        assert not pidfile.exists()

    def test_cleanup_missing_pidfile_no_error(self, tmp_path):
        """_cleanup 对不存在的 PID 文件不报错。"""
        from dsv4_cc_proxy.__main__ import _cleanup

        _cleanup(str(tmp_path / "nonexistent.pid"))  # 不应崩溃

    def test_graceful_shutdown_timeout_triggers_kill(self):
        """优雅关闭超时后触发 proc.kill()。"""
        from dsv4_cc_proxy.__main__ import _graceful_shutdown_child

        mock_proc = MagicMock(spec=subprocess.Popen)
        # 第一次 wait(timeout=5) 超时, 第二次 wait(timeout=2) 正常返回
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="test", timeout=5),
            None,
        ]

        _graceful_shutdown_child(mock_proc)
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()

    def test_get_watchdog_config_defaults(self, monkeypatch):
        """默认看门狗配置预设值正确。"""
        from dsv4_cc_proxy.__main__ import _get_watchdog_config

        monkeypatch.delenv("PROXY_WATCHDOG_MAX_RESTARTS", raising=False)
        monkeypatch.delenv("PROXY_WATCHDOG_RESTART_DELAY", raising=False)
        monkeypatch.delenv("PROXY_WATCHDOG_POLL_INTERVAL", raising=False)

        max_restarts, restart_delay, poll_interval = _get_watchdog_config()
        assert max_restarts == 5
        assert restart_delay == 2
        assert poll_interval == 0.5

    def test_watchdog_spawns_child(self, monkeypatch, tmp_path):
        """Watchdog 通过 subprocess.Popen 生成子进程。"""
        popen_calls = []

        class _FakeProc:
            def __init__(self, *a, **kw):
                self.pid = 12345
                popen_calls.append(kw)
            def poll(self):
                return 0
            def wait(self, **kw):
                pass
            @property
            def returncode(self):
                return 0

        pidfile = tmp_path / "watchdog.pid"

        monkeypatch.setattr("sys.argv", ["proxy.py", "--watchdog", "--pidfile", str(pidfile)])
        monkeypatch.setattr("subprocess.Popen", _FakeProc)
        monkeypatch.setattr("threading.Thread", lambda *a, **kw: MagicMock())
        monkeypatch.setattr("time.sleep", lambda s: None)

        from dsv4_cc_proxy.__main__ import main

        main()
        assert len(popen_calls) >= 1
        assert popen_calls[0]["env"]["DSV4CC_WATCHDOG_CHILD"] == "1"

    def test_watchdog_max_restarts_exceeded(self, monkeypatch, tmp_path):
        """看门狗达到最大重启次数后放弃并退出。"""
        class _CrashingProc:
            def __init__(self, *a, **kw):
                pass
            def poll(self):
                return 1
            def wait(self, **kw):
                pass
            @property
            def returncode(self):
                return 1

        pidfile = tmp_path / "watchdog.pid"

        monkeypatch.setattr("sys.argv", ["proxy.py", "--watchdog", "--pidfile", str(pidfile)])
        monkeypatch.setattr("subprocess.Popen", _CrashingProc)
        monkeypatch.setattr("threading.Thread", lambda *a, **kw: MagicMock())
        monkeypatch.setattr("time.sleep", lambda s: None)
        monkeypatch.setattr("dsv4_cc_proxy.__main__._get_watchdog_config",
                            lambda: (2, 1, 0.1))

        from dsv4_cc_proxy.__main__ import main

        main()  # 不应崩溃，应正常退出

    def test_watchdog_child_skips_pidfile(self, monkeypatch, tmp_path):
        """看门狗子进程 (DSV4CC_WATCHDOG_CHILD=1) 跳过 PID 文件管理。"""
        pidfile = tmp_path / "child.pid"

        monkeypatch.setattr("sys.argv", ["proxy.py", "--pidfile", str(pidfile)])
        monkeypatch.setenv("DSV4CC_WATCHDOG_CHILD", "1")
        monkeypatch.setattr("uvicorn.run", lambda *a, **kw: None)
        monkeypatch.setattr("dsv4_cc_proxy.__main__._check_port_available", lambda h, p: True)
        monkeypatch.setattr("os.unlink", lambda p: None)

        from dsv4_cc_proxy.__main__ import main

        main()
        # 子进程不应写入 PID 文件
        assert not pidfile.exists()

    def test_watchdog_checks_existing_instance(self, monkeypatch, tmp_path):
        """看门狗启动时若 PID 文件存在且有活跃进程则拒绝启动。"""
        pidfile = tmp_path / "watchdog.pid"
        pidfile.write_text("99999")

        monkeypatch.setattr("sys.argv", ["proxy.py", "--watchdog", "--pidfile", str(pidfile)])
        monkeypatch.setattr("os.kill", lambda pid, sig: None)  # 探活成功

        from dsv4_cc_proxy.__main__ import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
