import os
import sys
import time

import pytest

import singleinstance


def _unique_name(prefix):
    # 带 pid 的唯一名称：避免与开发机上正在运行的真实 Simple Note 实例互扰
    return "%s.%d" % (prefix, os.getpid())


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 互斥体仅 Windows")
def test_acquire_blocks_second_and_release_allows_reacquire():
    name = _unique_name("SimpleNote.Test.Mutex")
    h1 = singleinstance.acquire(name)
    assert h1 not in (None, singleinstance.PASS)
    assert singleinstance.acquire(name) is None      # 已被占用 -> None
    singleinstance.release(h1)
    h2 = singleinstance.acquire(name)
    assert h2 not in (None, singleinstance.PASS)
    singleinstance.release(h2)


def test_acquire_pass_on_non_windows(monkeypatch):
    monkeypatch.setattr(singleinstance.sys, "platform", "linux")
    assert singleinstance.acquire() is singleinstance.PASS
    singleinstance.release(singleinstance.PASS)      # no-op，不得抛


def test_acquire_fail_open_on_win32_error(monkeypatch, capsys):
    # Win32 调用异常 -> stderr 警告 + PASS 放行（绝不阻断启动）
    import ctypes as real_ctypes

    class _FailingCreateMutexW:
        # 伪 ctypes 函数对象：可挂 argtypes/restype，调用即抛以模拟 Win32 失败
        def __call__(self, *args, **kwargs):
            raise OSError("模拟 Win32 调用失败")

    class _FakeKernel32:
        def __init__(self):
            self.CreateMutexW = _FailingCreateMutexW()

    monkeypatch.setattr(singleinstance.sys, "platform", "win32")
    monkeypatch.setattr(real_ctypes, "WinDLL", lambda *a, **k: _FakeKernel32())
    assert singleinstance.acquire() is singleinstance.PASS
    assert "warning" in capsys.readouterr().err


def test_release_none_is_noop():
    singleinstance.release(None)                     # 不得抛


def test_activate_existing_false_on_non_windows(monkeypatch):
    monkeypatch.setattr(singleinstance.sys, "platform", "linux")
    assert singleinstance.activate_existing() is False


def test_activate_existing_fail_open_on_win32_error(monkeypatch):
    # Win32 调用异常 -> 静默返回 False（fail-open，绝不阻断启动）
    import ctypes as real_ctypes

    class _FailingRegisterWindowMessageW:
        # 伪 ctypes 函数对象：可挂 argtypes/restype，调用即抛以模拟 Win32 失败
        def __call__(self, *args, **kwargs):
            raise OSError("模拟 Win32 调用失败")

    class _FakeUser32:
        def __init__(self):
            self.RegisterWindowMessageW = _FailingRegisterWindowMessageW()
            self.SendMessageTimeoutW = object()   # 仅需可挂 argtypes/restype

    monkeypatch.setattr(singleinstance.sys, "platform", "win32")
    monkeypatch.setattr(real_ctypes, "WinDLL", lambda *a, **k: _FakeUser32())
    assert singleinstance.activate_existing() is False


def test_activate_existing_fail_open_when_msg_zero(monkeypatch):
    # RegisterWindowMessageW 返回 0（注册失败）-> 静默返回 False
    import ctypes as real_ctypes

    class _ZeroRegisterWindowMessageW:
        def __call__(self, *args, **kwargs):
            return 0

    class _FakeUser32:
        def __init__(self):
            self.RegisterWindowMessageW = _ZeroRegisterWindowMessageW()
            self.SendMessageTimeoutW = object()   # 仅需可挂 argtypes/restype

    monkeypatch.setattr(singleinstance.sys, "platform", "win32")
    monkeypatch.setattr(real_ctypes, "WinDLL", lambda *a, **k: _FakeUser32())
    assert singleinstance.activate_existing() is False


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 广播仅 Windows")
def test_activate_existing_smoke():
    # 无监听者时广播也"成功"（尽力而为语义）；真实收发闭环见 test_broadcast_reaches_listener
    name = _unique_name("SimpleNote.Test.Activate.Smoke")
    assert singleinstance.activate_existing(timeout_ms=500, msg_name=name) is True


def test_handle_message_only_fires_on_registered_id():
    calls = []
    li = singleinstance.SingleInstanceListener(on_activate=lambda: calls.append(1))
    li._msg_id = 12345
    li._handle_message(12345)
    assert calls == [1]
    li._handle_message(999)
    li._handle_message(0)
    assert calls == [1]


def test_handle_message_swallows_callback_error():
    def boom():
        raise RuntimeError("x")

    li = singleinstance.SingleInstanceListener(on_activate=boom)
    li._msg_id = 7
    li._handle_message(7)          # 不得向外抛


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 广播/监听仅 Windows")
def test_broadcast_reaches_listener():
    # 闭环集成：真实监听线程 + 真实广播，不碰 Tk，无显示器可跑
    calls = []
    name = _unique_name("SimpleNote.Test.Activate")
    li = singleinstance.SingleInstanceListener(lambda: calls.append(1), msg_name=name)
    li.start()
    try:
        assert li._ready.wait(timeout=5), "监听线程未在 5s 内就绪"
        assert singleinstance.activate_existing(msg_name=name) is True
        deadline = time.time() + 5
        while not calls and time.time() < deadline:
            time.sleep(0.05)
        assert calls == [1]
    finally:
        li.stop()
