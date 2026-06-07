"""dsv4-cc-proxy CLI 入口单元测试。

覆盖: stop/normal startup/already running/stale pidfile/error handling。
遵循纯函数 AAA 模式: Arrange → Act → Assert。

运行: python3 -m pytest tests/test_main.py -v
"""

import signal
from unittest.mock import patch

import pytest


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

    assert len(kill_calls) == 1
    assert kill_calls[0] == (99999, signal.SIGTERM)
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

    # 1 x SIGTERM + 10 x SIG_0 + 1 x SIGKILL = 12 os.kill calls
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
    monkeypatch.setattr("os.unlink", lambda p: None)

    from dsv4_cc_proxy.__main__ import main

    # 不应崩溃
    main()


def test_version_importable():
    """VERSION 可导入。"""
    from dsv4_cc_proxy._version import VERSION

    assert VERSION == "1.8.0"


def test_stop_pidfile_corrupted(monkeypatch, tmp_path):
    """--stop 时 PID 文件内容不是整数 -> 合理错误退出。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    pidfile.write_text("not_a_number")

    monkeypatch.setattr("sys.argv", ["proxy.py", "--stop", "--pidfile", str(pidfile)])

    from dsv4_cc_proxy.__main__ import main

    # PID 文件内容非法时 _stop 中 int() 抛出 ValueError
    with pytest.raises(ValueError, match="invalid literal for int()"):
        main()
