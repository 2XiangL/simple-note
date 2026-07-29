"""TrayController：系统托盘 + 全局热键 Ctrl+Alt+N。

pystray 菜单与 keyboard 热键回调跑在各自线程；Tkinter 非线程安全，
所有外部线程回调一律经 root.after(0, fn) 派发回主线程。
"""

from PIL import Image, ImageDraw, ImageFont


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


class TrayController:
    def __init__(self, root, on_quit, on_hide):
        self._root = root
        self._on_quit = on_quit
        self._on_hide = on_hide
        self._hidden = False
        self._icon = None
        self._hotkey_unreg = None

    def start(self):
        try:
            self._start_impl()
        except Exception as exc:     # 托盘不可用不应阻断应用
            print("warning: tray unavailable: %s" % exc)

    def _start_impl(self):
        import pystray
        from pystray import MenuItem

        try:
            import keyboard
            self._hotkey_unreg = keyboard.add_hotkey("ctrl+alt+n", self._on_hotkey)
        except Exception:
            self._hotkey_unreg = None

        menu = pystray.Menu(
            MenuItem("显示/隐藏", self._on_menu_toggle),
            MenuItem("退出", self._on_menu_quit),
        )
        self._icon = pystray.Icon("simple-note", make_icon_image(), "Simple Note", menu)
        self._icon.run_detached()

    def stop(self):
        if self._hotkey_unreg is not None:
            try:
                import keyboard
                keyboard.remove_hotkey(self._hotkey_unreg)
            except Exception:
                pass
            self._hotkey_unreg = None
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    # ---- 外部线程入口（仅派发，不碰 Tk）----
    def _on_hotkey(self):
        self._root.after(0, self.toggle_visibility)

    def _on_menu_toggle(self, _icon=None, _item=None):
        self._root.after(0, self.toggle_visibility)

    def _on_menu_quit(self, _icon=None, _item=None):
        self._root.after(0, self._on_quit)

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
