import os
import sys

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
