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


def test_release_none_is_noop():
    singleinstance.release(None)                     # 不得抛
