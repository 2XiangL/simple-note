# 单实例应用 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 再次启动 Simple Note 时不多开，而是激活已运行窗口（含从托盘/最小化恢复）并置前，第二进程静默退出。

**Architecture:** Win32 命名互斥体做原子检测（`main.py` 最前面，早于一切 Tk 创建）；第二实例广播 `RegisterWindowMessage` 注册消息后退出；第一实例由复刻 `_HotkeyListener` 模式的守护线程（隐藏**顶层**窗口 + GetMessageW 泵）接收广播，经 `TrayController` 队列封送 `tray.show()` 恢复窗口。仅 Windows，任何 Win32 失败 fail-open 放行启动。

**Tech Stack:** Python 3.14 + ctypes（Win32，无新依赖）、pytest（全部测试无显示器可跑，除一个 `tk_root` 用例）。

**Spec:** `docs/superpowers/specs/2026-08-03-single-instance-design.md`

**通用约定（每个任务都适用）：**

- 测试命令一律 `uv run pytest <路径> -v`（仓库用 uv 管理，pythonpath=["."]，根目录模块直接 import）
- UI 字符串/注释/docstring 用**简体中文**（仓库惯例）
- 新增代码不加无关注释；注释只解释"为什么"（对齐 tray.py 风格）
- 提交信息风格对齐 `git log`：`feat(app):` / `test(singleinstance):` 等中文描述
- 测试用唯一互斥体/消息名（含 `os.getpid()`），避免与开发者机器上正在运行的真实 Simple Note 实例互相干扰（真实实例持有同名互斥体/监听同名广播）

---

### Task 1: `singleinstance.acquire` / `release`（互斥体检测）

**Files:**
- Create: `singleinstance.py`
- Test: `tests/test_singleinstance.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_singleinstance.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_singleinstance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'singleinstance'`

- [ ] **Step 3: 最小实现**

创建 `singleinstance.py`：

```python
"""单实例守卫：Win32 命名互斥体 + 广播消息激活已有实例。

第二实例 acquire() 返回 None -> activate_existing() 广播激活消息后退出；
第一实例由 SingleInstanceListener 在隐藏顶层窗口上泵消息，收到注册消息后
经调用方封送（enqueue）回 Tk 主线程恢复窗口。非 Windows 或 Win32 失败一律
fail-open（放行启动），绝不阻断应用启动。
"""

import sys
import threading  # noqa: F401  （Task 3 的 SingleInstanceListener 用）

MUTEX_NAME = "SimpleNote.SingleInstance"
ACTIVATE_MSG_NAME = "SimpleNote.Activate"
WINDOW_CLASS = "SimpleNoteSingleInstanceWnd"

_ERROR_ALREADY_EXISTS = 183
_WM_QUIT = 0x0012
_HWND_BROADCAST = 0xFFFF
_SMTO_NORMAL = 0x0000

PASS = "pass"  # 非 Windows / Win32 异常时的哨兵返回值：放行启动，无句柄需持有


def acquire(name=MUTEX_NAME):
    """尝试占用命名互斥体。

    首实例返回互斥体句柄（调用方须持有至进程退出，OS 在退出/崩溃时自动释放）；
    已被占用返回 None；非 Windows 或 API 异常返回 PASS 放行（fail-open）。
    """
    if sys.platform != "win32":
        return PASS
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        h = kernel32.CreateMutexW(None, False, name)
        err = ctypes.get_last_error()
        if err == _ERROR_ALREADY_EXISTS:
            # 互斥体已存在：CreateMutexW 仍返回指向它的有效句柄，须关闭再报 None
            if h:
                kernel32.CloseHandle(h)
            return None
        if not h:
            raise OSError("CreateMutexW 失败（GetLastError=%d）" % err)
        return h
    except Exception as exc:
        print("warning: 单实例检查不可用，继续启动：%s" % exc, file=sys.stderr)
        return PASS


def release(handle):
    """释放互斥体句柄；None/PASS 为 no-op。"""
    if sys.platform != "win32" or handle in (None, PASS):
        return
    try:
        import ctypes
        ctypes.WinDLL("kernel32").CloseHandle(handle)
    except Exception:
        pass
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_singleinstance.py -v`
Expected: PASS（非 Windows 平台 win32 用例 skipped）

- [ ] **Step 5: 提交**

```bash
git add singleinstance.py tests/test_singleinstance.py
git commit -m "feat(singleinstance): 命名互斥体单实例检测 acquire/release"
```

---

### Task 2: `activate_existing`（第二实例广播激活消息）

**Files:**
- Modify: `singleinstance.py`
- Test: `tests/test_singleinstance.py`

说明：`msg_name` 开放为可选参数是**测试缝隙**——默认值仍为 spec 定义的 `ACTIVATE_MSG_NAME`，集成测试用唯一消息名避免惊动开发机上真实运行的 Simple Note。`SendMessageTimeoutW` 的结果参数是 `DWORD_PTR`（指针宽度），必须用 `ctypes.c_size_t`，用 `wintypes.DWORD` 在 64 位上会写越界。

- [ ] **Step 1: 写失败测试**

向 `tests/test_singleinstance.py` 追加：

```python
def test_activate_existing_false_on_non_windows(monkeypatch):
    monkeypatch.setattr(singleinstance.sys, "platform", "linux")
    assert singleinstance.activate_existing() is False


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 广播仅 Windows")
def test_activate_existing_smoke():
    # 无监听者时广播也"成功"（尽力而为语义）；真实收发闭环见 test_broadcast_reaches_listener
    name = _unique_name("SimpleNote.Test.Activate.Smoke")
    assert singleinstance.activate_existing(timeout_ms=500, msg_name=name) is True
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_singleinstance.py -v -k activate`
Expected: FAIL — `AttributeError: module 'singleinstance' has no attribute 'activate_existing'`

- [ ] **Step 3: 最小实现**

向 `singleinstance.py` 追加（`release` 之后）：

```python
def activate_existing(timeout_ms=2000, msg_name=ACTIVATE_MSG_NAME):
    """向第一实例广播激活消息；尽力而为，任何失败静默返回 False。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
        user32.RegisterWindowMessageW.restype = wintypes.UINT
        # 结果参数为 DWORD_PTR（指针宽度）：64 位上必须用 c_size_t，DWORD 会写越界
        user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
            wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
        ]
        user32.SendMessageTimeoutW.restype = wintypes.LPARAM
        msg = user32.RegisterWindowMessageW(msg_name)
        if not msg:
            return False
        result = ctypes.c_size_t(0)
        user32.SendMessageTimeoutW(
            _HWND_BROADCAST, msg, 0, 0, _SMTO_NORMAL, timeout_ms, ctypes.byref(result))
        return True
    except Exception:
        return False
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_singleinstance.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add singleinstance.py tests/test_singleinstance.py
git commit -m "feat(singleinstance): activate_existing 广播激活消息"
```

---

### Task 3: `SingleInstanceListener`（第一实例监听线程）

**Files:**
- Modify: `singleinstance.py`
- Test: `tests/test_singleinstance.py`

关键点（实现时逐条对照）：

1. 监听窗口必须是**普通隐藏顶层窗口**——message-only 窗口（HWND_MESSAGE）收不到 `HWND_BROADCAST` 广播
2. wndproc 的 `WINFUNCTYPE` 回调对象必须保存在实例属性上（`_wndproc_ref`），否则被 GC 后窗口收到消息即崩溃
3. `GetModuleHandleW` 必须设 `restype = wintypes.HMODULE`（默认 c_int 在 64 位上截断句柄）
4. `DestroyWindow`/`UnregisterClassW` 在 `finally` 里执行（仍在创建窗口的监听线程内，合法）
5. 回调异常必须吞掉并告警，绝不让消息泵线程裸死

- [ ] **Step 1: 写失败测试**

向 `tests/test_singleinstance.py` 追加（顶部补 `import time`）：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_singleinstance.py -v`
Expected: FAIL — `AttributeError: module 'singleinstance' has no attribute 'SingleInstanceListener'`

- [ ] **Step 3: 实现**

向 `singleinstance.py` 追加（文件末尾）：

```python
class SingleInstanceListener(threading.Thread):
    """隐藏顶层窗口 + GetMessageW 泵：收到激活广播调用 on_activate。

    必须是顶层窗口（而非 HWND_MESSAGE）：message-only 窗口收不到
    HWND_BROADCAST 广播。on_activate 在本监听线程内执行——调用方须自行
    封送（enqueue）回主线程，绝不直接碰 Tk。
    """

    daemon = True

    def __init__(self, on_activate, msg_name=ACTIVATE_MSG_NAME):
        super().__init__()
        self._on_activate = on_activate
        self._msg_name = msg_name
        self._msg_id = 0
        self._thread_id = 0
        self._ready = threading.Event()
        self._wndproc_ref = None  # 保持 wndproc 回调引用防 GC

    def _handle_message(self, msg_id):
        """纯分派逻辑（可脱离 Win32 单测）：仅注册消息 id 触发回调。"""
        if msg_id and msg_id == self._msg_id:
            try:
                self._on_activate()
            except Exception as exc:
                print("warning: 单实例激活回调出错：%s" % exc, file=sys.stderr)

    def run(self):
        import ctypes
        from ctypes import wintypes

        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except (AttributeError, OSError) as exc:
            print("warning: 单实例监听不可用：%s" % exc, file=sys.stderr)
            self._ready.set()
            return

        WNDPROC = ctypes.WINFUNCTYPE(
            wintypes.LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        def wndproc(hwnd, msg, wparam, lparam):
            self._handle_message(msg)
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc_ref = WNDPROC(wndproc)

        user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
        user32.RegisterWindowMessageW.restype = wintypes.UINT
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                       wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = wintypes.LRESULT
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        self._msg_id = user32.RegisterWindowMessageW(self._msg_name)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HANDLE),
                ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = WINDOW_CLASS

        user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
        user32.RegisterClassExW.restype = wintypes.ATOM
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            print("warning: 单实例窗口类注册失败（GetLastError=%d）"
                  % ctypes.get_last_error(), file=sys.stderr)
            self._ready.set()
            return

        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HANDLE, wintypes.HANDLE, wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        hwnd = user32.CreateWindowExW(0, WINDOW_CLASS, WINDOW_CLASS, 0, 0, 0, 0, 0,
                                      None, None, wc.hInstance, None)
        if not hwnd:
            user32.UnregisterClassW(WINDOW_CLASS, wc.hInstance)
            print("warning: 单实例监听窗口创建失败（GetLastError=%d）"
                  % ctypes.get_last_error(), file=sys.stderr)
            self._ready.set()
            return

        self._thread_id = kernel32.GetCurrentThreadId()
        self._ready.set()

        msg = wintypes.MSG()
        try:
            while True:
                # GetMessageW：0 = WM_QUIT，-1 = 出错，均退出泵
                if user32.GetMessageW(ctypes.byref(msg), None, 0, 0) <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(WINDOW_CLASS, wc.hInstance)

    def stop(self):
        """唤醒泵线程退出（PostThreadMessage WM_QUIT 打断 GetMessage）。"""
        if not self._ready.wait(timeout=2):
            return
        if not self._thread_id:
            return
        try:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
        except Exception:
            pass
        self.join(timeout=2)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_singleinstance.py -v`
Expected: PASS（含集成用例；非 Windows 平台 win32 用例 skipped）

- [ ] **Step 5: 提交**

```bash
git add singleinstance.py tests/test_singleinstance.py
git commit -m "feat(singleinstance): 隐藏顶层窗口监听线程接收激活广播"
```

---

### Task 4: `TrayController.enqueue`（公开入队口）

**Files:**
- Modify: `tray.py:193-195`（`_marshal` 旁）
- Test: `tests/test_tray.py`

- [ ] **Step 1: 写失败测试**

向 `tests/test_tray.py` 追加：

```python
def test_tray_enqueue_runs_on_drain():
    # enqueue 是外部线程的公开入队口：只入队不执行，主线程 _drain 才消费
    root = _FakeRoot()
    tc = tray.TrayController(root, on_quit=lambda: None, on_hide=lambda: None)
    calls = []
    tc.enqueue(lambda: calls.append(1))
    assert calls == []
    tc._drain()
    assert calls == [1]
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_tray.py::test_tray_enqueue_runs_on_drain -v`
Expected: FAIL — `AttributeError: 'TrayController' object has no attribute 'enqueue'`

- [ ] **Step 3: 最小实现**

`tray.py` 在 `_marshal` 方法（约 line 194）后追加：

```python
    def enqueue(self, fn):
        """供外部线程入队的公开入口（内部 _marshal 的别名）。"""
        self._calls.put(fn)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_tray.py -v`
Expected: PASS（全部既有 tray 用例不回归）

- [ ] **Step 5: 提交**

```bash
git add tray.py tests/test_tray.py
git commit -m "feat(tray): enqueue 公开入队口供单实例监听线程封送"
```

---

### Task 5: `main.py` 入口守卫 + 监听线程提前启动（消除竞态）

> 代码审查发现原设计存在启动竞态：互斥体在 main.py 最前面获取，但监听窗口要等 NoteApp.__init__ 尾部才创建——首实例启动窗口（约 0.5-2s）内二次启动会静默退出但窗口不激活。用户已确认：**监听线程提前到 main.py，acquire 成功后立即启动（早于 Tk）**。激活经模块级回调注册接线，NoteApp 不持有监听线程。

**Files:**
- Modify: `singleinstance.py`（加 `set_activation_handler`/`_dispatch_activation`；监听器 `on_activate` 改为可选）
- Modify: `main.py`
- Test: `tests/test_main.py`（新建）
- Test: `tests/test_singleinstance.py`

- [ ] **Step 1: 写失败测试（singleinstance 部分）**

向 `tests/test_singleinstance.py` 追加：

```python
def test_activation_handler_dispatch(monkeypatch):
    # 监听器省略 on_activate 时：默认分派到 set_activation_handler 注册的模块级回调
    calls = []
    monkeypatch.setattr(singleinstance, "_activation_handler", None)
    singleinstance.set_activation_handler(lambda: calls.append(1))
    li = singleinstance.SingleInstanceListener()      # 不传 on_activate
    li._msg_id = 42
    li._handle_message(42)
    assert calls == [1]
    singleinstance.set_activation_handler(None)       # 清理，防测试间污染


def test_explicit_on_activate_beats_global_handler(monkeypatch):
    # 显式传入 on_activate 优先于模块级回调
    global_calls = []
    local_calls = []
    monkeypatch.setattr(singleinstance, "_activation_handler", None)
    singleinstance.set_activation_handler(lambda: global_calls.append(1))
    li = singleinstance.SingleInstanceListener(on_activate=lambda: local_calls.append(1))
    li._msg_id = 7
    li._handle_message(7)
    assert local_calls == [1]
    assert global_calls == []
    singleinstance.set_activation_handler(None)


def test_activation_handler_unset_is_noop(monkeypatch):
    # 未注册 handler 时收到广播是 no-op（启动窗口内广播不炸）
    monkeypatch.setattr(singleinstance, "_activation_handler", None)
    li = singleinstance.SingleInstanceListener()
    li._msg_id = 5
    li._handle_message(5)                              # 不得抛
```

- [ ] **Step 2: 写失败测试（main 部分）**

创建 `tests/test_main.py`：

```python
import main


def test_main_second_instance_activates_and_exits(monkeypatch):
    # 已有实例：广播激活后静默退出，绝不创建 Tk
    calls = []
    monkeypatch.setattr(main.singleinstance, "acquire", lambda: None)
    monkeypatch.setattr(main.singleinstance, "activate_existing", lambda: calls.append(1))

    def _boom(*a, **k):
        raise AssertionError("第二实例不得创建 Tk")

    monkeypatch.setattr(main.tk, "Tk", _boom)
    main.main()
    assert calls == [1]
    assert main._GUARD is None


def test_main_first_instance_proceeds(monkeypatch):
    # 首实例：持有守卫句柄并照常进入启动流程
    monkeypatch.setattr(main.singleinstance, "acquire", lambda: "guard-handle")
    monkeypatch.setattr(main.singleinstance, "SingleInstanceListener", _FakeListener())
    roots = []
    loops = []

    class _FakeRoot:
        def mainloop(self):
            loops.append(1)

    def _fake_tk():
        r = _FakeRoot()
        roots.append(r)
        return r

    monkeypatch.setattr(main.tk, "Tk", _fake_tk)
    import app as appmod
    monkeypatch.setattr(appmod, "NoteApp", lambda root: None)
    main.main()
    assert len(roots) == 1
    assert loops == [1]
    assert main._GUARD == "guard-handle"


def test_main_fail_open_pass_sentinel_proceeds(monkeypatch):
    # acquire 返回 PASS（非 Windows/Win32 失败）：放行启动，不当作第二实例
    monkeypatch.setattr(main.singleinstance, "acquire", lambda: main.singleinstance.PASS)
    monkeypatch.setattr(main.singleinstance, "SingleInstanceListener", _FakeListener())
    roots = []

    class _FakeRoot:
        def mainloop(self):
            pass

    monkeypatch.setattr(main.tk, "Tk", lambda: roots.append(1) or _FakeRoot())
    import app as appmod
    monkeypatch.setattr(appmod, "NoteApp", lambda root: None)
    main.main()
    assert len(roots) == 1
    assert main._GUARD is main.singleinstance.PASS


def test_main_first_instance_starts_listener_before_tk_and_stops_after(monkeypatch):
    # 首实例：监听线程在 acquire 后、Tk 创建前启动；mainloop 返回后停止
    monkeypatch.setattr(main.singleinstance, "acquire", lambda: "guard")
    events = []

    class _FakeListener:
        def start(self):
            events.append("listener-start")

        def stop(self):
            events.append("listener-stop")

    monkeypatch.setattr(main.singleinstance, "SingleInstanceListener",
                        lambda: _FakeListener())

    class _FakeRoot:
        def mainloop(self):
            events.append("mainloop")

    monkeypatch.setattr(main.tk, "Tk", lambda: _FakeRoot())
    import app as appmod
    monkeypatch.setattr(appmod, "NoteApp", lambda root: events.append("noteapp"))
    main.main()
    assert events == ["listener-start", "noteapp", "mainloop", "listener-stop"]
```

注：`_FakeListener` 类定义放文件顶部（`import main` 之后），供前三个用例复用的写法：

```python
class _FakeListener:
    def __init__(self, on_activate=None):
        self.on_activate = on_activate
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
```

（`test_main_first_instance_proceeds` 等三个用例里 `monkeypatch.setattr(main.singleinstance, "SingleInstanceListener", _FakeListener)` 传类本身；第四个用例里传返回记录事件的 lambda——按上面两个代码块实际形态灵活合并，保持每个用例断言行为即可。）

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/test_singleinstance.py tests/test_main.py -v`
Expected: FAIL — `AttributeError: module 'singleinstance' has no attribute 'set_activation_handler'`；`AttributeError: module 'main' has no attribute 'singleinstance'`

- [ ] **Step 4: 实现（singleinstance.py）**

`singleinstance.py` 在模块 docstring 之后、`MUTEX_NAME` 之前插入模块级回调与注册函数：

```python
_activation_handler = None  # 模块级窗口激活回调：NoteApp 就绪后经 set_activation_handler 注册


def set_activation_handler(fn):
    """注册窗口激活回调（传 None 可重置）；由 NoteApp 就绪时调用。

    监听线程触发时经 _dispatch_activation 分派到此回调（仅入队，不碰 Tk）。
    """
    global _activation_handler
    _activation_handler = fn


def _dispatch_activation():
    # 监听线程收到广播时的默认分派：handler 未注册（启动窗口内）为 no-op
    if _activation_handler is not None:
        _activation_handler()
```

`SingleInstanceListener.__init__` 的 `on_activate` 改为可选（默认分派到模块级回调）：

```python
    def __init__(self, on_activate=None, msg_name=ACTIVATE_MSG_NAME):
        super().__init__()
        self._on_activate = on_activate or _dispatch_activation
        ...
```

- [ ] **Step 5: 实现（main.py）**

`main.py` 改为（原守卫基础上增加监听线程提前启动/收尾）：

```python
"""Simple Note 入口。"""

import sys
import tkinter as tk
from tkinter import messagebox

import singleinstance

_GUARD = None    # 单实例互斥体句柄：须持有至进程退出（OS 退出时自动释放）
_LISTENER = None  # 单实例监听线程（早于 Tk 创建，消除启动竞态）


def _start_single_instance_listener():
    """acquire 成功后立即启动监听线程（早于任何 Tk 创建）。

    不传 on_activate：默认分派到 set_activation_handler 注册的模块级回调，
    由 NoteApp 就绪时接线。
    """
    global _LISTENER
    _LISTENER = singleinstance.SingleInstanceListener()
    _LISTENER.start()


def stop_single_instance_listener():
    """mainloop 退出后停掉监听线程（进程即将结束，清理窗口类/消息泵）。"""
    if _LISTENER is not None:
        _LISTENER.stop()


def main():
    global _GUARD
    _GUARD = singleinstance.acquire()
    if _GUARD is None:
        # 已有实例在运行：尽力激活其窗口，本进程静默退出（不创建任何 Tk 对象）
        singleinstance.activate_existing()
        return
    _start_single_instance_listener()

    try:
        from PIL import Image  # noqa: F401
    except Exception:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("Simple Note", "未检测到 Pillow，图片粘贴/缩放功能将不可用。")
        root.destroy()
        # 缺少 Pillow 时 app→tray 顶层 import PIL 必然 ImportError，探测后直接退出，
        # 不让用户看到带病启动后的裸异常栈。
        sys.exit(1)

    root = tk.Tk()
    from app import NoteApp
    NoteApp(root)
    root.mainloop()
    stop_single_instance_listener()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 运行确认通过**

Run: `uv run pytest tests/test_singleinstance.py tests/test_main.py -v`
Expected: PASS（全部既有用例不回归）

- [ ] **Step 7: 提交**

```bash
git add singleinstance.py main.py tests/test_singleinstance.py tests/test_main.py
git commit -m "feat(main): 监听线程提前到 main.py 消除启动竞态，激活经模块级回调接线"
```

---

### Task 6: `app.NoteApp` 注册激活回调（tray 队列封送）

**Files:**
- Modify: `app.py`（imports、`__init__` 中 `tray.start()` 后）
- Test: `tests/test_app.py`

说明：监听线程已在 main.py 启动（Task 5）。NoteApp 只负责**注册激活回调**；`_real_quit` 不再涉及监听线程（停止已移至 main.py 的 mainloop 退出路径）。

- [ ] **Step 1: 写失败测试**

向 `tests/test_app.py` 追加（文件已有 `from types import SimpleNamespace`、`import pytest`）：

```python
def test_real_quit_without_listener_cleanup(monkeypatch):
    # 监听线程停止已移至 main.py（mainloop 退出路径）；_real_quit 只管 tray -> root
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    stopped = []
    app.docs = []
    app._reminder_dlg = None
    app._persist = lambda: None
    app.tray = SimpleNamespace(stop=lambda: stopped.append("tray"))
    app.root = SimpleNamespace(destroy=lambda: stopped.append("root"))
    app._real_quit()
    assert stopped == ["tray", "root"]


def test_noteapp_registers_activation_handler(tk_root, monkeypatch):
    # NoteApp 就绪后注册激活回调：触发时经 tray.enqueue 封送，主线程消费后调 tray.show
    import singleinstance
    import app as appmod

    class _FakeTray:
        def __init__(self, root, on_quit, on_hide):
            self.enqueued = []
            self.shown = 0

        def start(self):
            pass

        def stop(self):
            pass

        def enqueue(self, fn):
            self.enqueued.append(fn)

        def show(self):
            self.shown += 1

        def hide(self):
            pass

        def is_running(self):
            return True

    monkeypatch.setattr(appmod, "TrayController", _FakeTray)
    monkeypatch.setattr(appmod.settings, "save_settings", lambda *a, **k: None)
    monkeypatch.setattr(singleinstance, "_activation_handler", None)  # 防污染
    app = appmod.NoteApp(tk_root)
    try:
        assert singleinstance._activation_handler is not None
        singleinstance._activation_handler()          # 模拟监听线程默认分派（只入队）
        assert len(app.tray.enqueued) == 1
        assert app.tray.shown == 0
        app.tray.enqueued[0]()                        # 模拟主线程 _drain 消费
        assert app.tray.shown == 1
    finally:
        app._real_quit()                              # 清理：停 tray、销毁 root
        singleinstance.set_activation_handler(None)   # 清理模块级回调
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_app.py -v -k "activation_handler or real_quit_without_listener"`
Expected: FAIL — `AttributeError: module 'app' has no attribute 'SingleInstanceListener'`（若 import 尚存）或断言失败（handler 未注册）

- [ ] **Step 3: 实现**

`app.py` 两处修改：

imports（line 16，`from tray import TrayController` 后）：

```python
import singleinstance
```

`__init__` 中 `self.tray.start()`（line 86）之后插入：

```python
        singleinstance.set_activation_handler(lambda: self.tray.enqueue(self.tray.show))
```

`_real_quit` **不改动**（无监听线程可停；`tray.stop()` + `root.destroy()` 原样）。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_app.py -v`
Expected: PASS（全部既有 app 用例不回归；`tk_root` 用例在无显示器环境 skipped 属正常）

- [ ] **Step 5: 提交**

```bash
git add app.py tests/test_app.py
git commit -m "feat(app): NoteApp 注册激活回调，经 tray 队列恢复窗口"
```

---

### Task 7: 文档同步 + 全量验证

**Files:**
- Modify: `AGENTS.md`（Architecture 一节，`tray.py` 条目之后）

- [ ] **Step 1: 更新 AGENTS.md**

在 Architecture 的 `tray.py` 条目后追加一条：

```markdown
- `singleinstance.py` — 单实例守卫（仅 Windows，fail-open）：`acquire()` 占用命名互斥体（已占用返回 None = 第二实例）；`activate_existing()` 广播 `SimpleNote.Activate` 注册消息；`SingleInstanceListener` 是隐藏**顶层**窗口（message-only 窗口收不到广播）+ GetMessageW 泵的守护线程，`on_activate` 可省略（默认分派到 `set_activation_handler` 注册的模块级回调）。`main.py` 在**任何 Tk 创建之前**分流第二实例（广播后静默退出），且 acquire 成功后**立即启动监听线程**（消除启动竞态）；`NoteApp.__init__` 用 `singleinstance.set_activation_handler(lambda: self.tray.enqueue(self.tray.show))` 接线，激活广播经 tray 队列封送恢复并置前窗口；`mainloop()` 返回后 `stop_single_instance_listener()`。监听线程绝不碰 Tk、只入队（同 tray 热键规则）。测试用带 pid 的唯一互斥体/消息名，避免与开发机上运行中的真实实例互扰。
```

- [ ] **Step 2: 全量测试**

Run: `uv run pytest -q`
Expected: 全部通过；1–2 个 `tk_root` 用例 skipped 属已知现象（AGENTS.md「Environment gotchas」：tk.tcl 间歇性初始化失败，重跑受影响文件确认即可）

- [ ] **Step 3: 手工端到端验证（有显示器）**

1. `uv run python main.py` 启动第一个实例
2. 另开终端再跑 `uv run python main.py` → 第二进程立即退出，第一个实例窗口被置前
3. 第一实例隐藏到托盘（关闭按钮或 Ctrl+Alt+N）→ 再跑一次 `uv run python main.py` → 窗口从托盘恢复并置前
4. 最小化窗口 → 再跑一次 → 窗口恢复并置前
5. 关闭第一实例 → 再跑 → 正常全新启动（互斥体已被 OS 释放）

- [ ] **Step 4: 提交**

```bash
git add AGENTS.md
git commit -m "docs(agents): 同步单实例守卫架构说明"
```
