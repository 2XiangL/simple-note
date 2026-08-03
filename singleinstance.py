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
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
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
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(handle)
    except Exception:
        pass


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
        sent = user32.SendMessageTimeoutW(
            _HWND_BROADCAST, msg, 0, 0, _SMTO_NORMAL, timeout_ms, ctypes.byref(result))
        return bool(sent)
    except Exception:
        return False


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
            wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

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
        user32.DefWindowProcW.restype = wintypes.LPARAM
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HMODULE]
        user32.UnregisterClassW.restype = wintypes.BOOL

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
                ("hIconSm", wintypes.HANDLE),
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
