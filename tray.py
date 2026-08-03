"""TrayController：系统托盘 + 全局热键 Ctrl+Alt+N。

全局热键通过 Win32 ``RegisterHotKey`` 以系统级方式注册（由 OS 直接投递
``WM_HOTKEY``），比低级键盘钩子（``SetWindowsHookEx``，``keyboard`` 库所用）
可靠得多——后者在受限会话或部分机器上会静默安装失败。热键监听在独立线程
中跑消息泵。

pystray 菜单与热键回调都跑在各自线程；Tkinter 非线程安全，这里采用
"队列 + 主线程轮询"：外部线程只往队列里塞任务，绝不直接调用 Tk；主线程
通过 ``root.after`` 周期性 ``_drain`` 队列并在自身上下文执行，彻底规避
跨线程访问 Tk 的隐患。
"""

import queue
import threading
from PIL import Image, ImageDraw, ImageFont

# Win32 热键相关常量
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012
_HOTKEY_ID = 1
_VK_N = 0x4E


def make_icon_image():
    """生成 64x64 圆角蓝底白色 N 的托盘图标（不引入二进制资源）。"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, 62, 62], radius=12, fill=(26, 115, 232, 255))
    try:
        font = ImageFont.load_default(size=40)
    except TypeError:                # 旧版 Pillow 不支持 size 参数
        font = ImageFont.load_default()
    d.text((32, 32), "N", fill="white", font=font, anchor="mm")
    return img


class _HotkeyListener(threading.Thread):
    """在独立线程注册系统级全局热键并泵取窗口消息。

    命中热键时调用 ``on_triggered``（仍在本监听线程内执行）。
    仅 Windows 可用；非 Windows 平台 ``run`` 会标记注册失败后退出。
    """

    daemon = True

    def __init__(self, modifiers, vk, on_triggered, on_status=None):
        super().__init__()
        self._modifiers = modifiers
        self._vk = vk
        self._on_triggered = on_triggered
        self._on_status = on_status
        self._thread_id = 0
        self._ready = threading.Event()
        self._registered = False
        self._error = 0

    def run(self):
        import ctypes
        from ctypes import wintypes

        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except (AttributeError, OSError):
            self._ready.set()
            return

        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                          wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG),
                                       wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int

        self._thread_id = kernel32.GetCurrentThreadId()
        ok = bool(user32.RegisterHotKey(None, _HOTKEY_ID, self._modifiers, self._vk))
        self._registered = ok
        self._error = ctypes.get_last_error() if not ok else 0
        self._ready.set()
        if self._on_status is not None:
            # 注册结果异步上报（仍在本监听线程），由 TrayController 封送回主线程
            self._on_status(self._registered, self._error)
        if not ok:
            return

        msg = wintypes.MSG()
        try:
            while True:
                # GetMessage 阻塞至有消息；返回 -1 出错、0 收到 WM_QUIT、正数为普通消息
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0:
                    break
                if ret < 0:
                    # 记录错误码并经 on_status 封送回主线程（监听线程只入队、
                    # 不打印/碰 Tk），由主线程更新 status() 并告警
                    self._error = ctypes.get_last_error()
                    if self._on_status is not None:
                        self._on_status(self._registered, self._error)
                    break
                if msg.message == _WM_HOTKEY:
                    self._on_triggered()
        finally:
            user32.UnregisterHotKey(None, _HOTKEY_ID)

    def stop(self):
        """唤醒监听线程使其退出（投递 WM_QUIT 打断 GetMessage）。"""
        if not self._ready.wait(timeout=2):
            return
        if not self._registered or self._thread_id == 0:
            return
        try:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id, _WM_QUIT, 0, 0)
        except Exception:
            pass
        self.join(timeout=2)


class TrayController:
    def __init__(self, root, on_quit, on_hide):
        self._root = root
        self._on_quit = on_quit
        self._on_hide = on_hide
        self._hidden = False
        self._icon = None
        self._hotkey = None
        self._hotkey_registered = None  # None=尚未上报；True/False=热键注册状态
        self._hotkey_error = 0
        self._calls = queue.Queue()
        self._polling = False

    def start(self):
        # 先启动主线程轮询，确保外部线程入队的任务能被消费
        self._polling = True
        self._root.after(50, self._poll)
        try:
            self._start_impl()
        except Exception as exc:     # 托盘不可用不应阻断应用
            print("warning: tray unavailable: %s" % exc)

    def is_running(self):
        return self._icon is not None

    def status(self):
        """返回 (托盘图标运行中, 热键注册状态, 热键错误码) 供诊断。

        热键注册状态由监听线程异步上报（None=尚未上报）。
        """
        return (self._icon is not None, self._hotkey_registered, self._hotkey_error)

    def _start_impl(self):
        import sys

        import pystray
        from pystray import MenuItem

        if sys.platform == "win32":
            self._hotkey = _HotkeyListener(
                _MOD_CONTROL | _MOD_ALT, _VK_N, self._on_hotkey,
                on_status=lambda reg, err: self._marshal(
                    lambda: self._on_hotkey_status(reg, err)),
            )
            self._hotkey.start()

        menu = pystray.Menu(
            MenuItem("显示/隐藏", self._on_menu_toggle),
            MenuItem("退出", self._on_menu_quit),
        )
        self._icon = pystray.Icon("simple-note", make_icon_image(), "Simple Note", menu)
        self._icon.run_detached()

    def stop(self):
        self._polling = False
        if self._hotkey is not None:
            try:
                self._hotkey.stop()
            except Exception:
                pass
            self._hotkey = None
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    # ---- 跨线程封送：外部线程只入队，主线程 _poll/_drain 消费 ----
    def enqueue(self, fn):
        """供外部线程入队的公开入口（内部 _marshal 的别名）。"""
        self._calls.put(fn)

    def _marshal(self, fn):
        self._calls.put(fn)

    def _drain(self):
        while True:
            try:
                fn = self._calls.get_nowait()
            except queue.Empty:
                return
            fn()

    def _poll(self):
        self._drain()
        if self._polling:
            self._root.after(50, self._poll)

    # ---- 外部线程入口（仅入队，绝不碰 Tk）----
    def _on_hotkey(self):
        self._marshal(self.toggle_visibility)

    def _on_hotkey_status(self, registered, error):
        # 主线程消费热键状态消息：替代原启动时最长 2s 的阻塞等待，
        # 注册结果（含失败原因）异步经队列回主线程记录/告警。
        # registered=True 且 error!=0 表示消息泵 GetMessageW 失败退出。
        self._hotkey_registered = registered
        self._hotkey_error = error
        if not registered:
            if error == 1409:     # ERROR_HOTKEY_ALREADY_REGISTERED
                print("warning: 全局热键 Ctrl+Alt+N 已被其他程序占用"
                      "（通常是上一个本程序实例仍驻留托盘，请从托盘菜单“退出”后再试）")
            else:
                print("warning: 全局热键 Ctrl+Alt+N 注册失败"
                      "（GetLastError=%d）" % error)
        elif error:
            print("warning: 热键消息泵 GetMessageW 失败"
                  "（GetLastError=%d），热键监听已退出" % error)

    def _on_menu_toggle(self, _icon=None, _item=None):
        self._marshal(self.toggle_visibility)

    def _on_menu_quit(self, _icon=None, _item=None):
        self._marshal(self._on_quit)

    # ---- 主线程状态机 ----
    def toggle_visibility(self):
        if self._hidden:
            self.show()
        else:
            self.hide()

    def hide(self):
        self._hidden = True
        if self._on_hide:
            self._on_hide()
        self._root.withdraw()

    def show(self):
        self._hidden = False
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()
