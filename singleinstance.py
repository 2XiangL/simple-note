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
