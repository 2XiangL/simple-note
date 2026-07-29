import tray


class _FakeRoot:
    def __init__(self):
        self.withdrawed = False
        self.shown = False
        self.after_calls = 0

    def after(self, ms, fn):
        self.after_calls += 1
        fn()

    def withdraw(self):
        self.withdrawed = True

    def deiconify(self):
        self.shown = True

    def lift(self):
        pass

    def focus_force(self):
        pass


def test_make_icon_image():
    img = tray.make_icon_image()
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


def test_tray_state_machine():
    root = _FakeRoot()
    quits = []
    hides = []
    tc = tray.TrayController(
        root,
        on_quit=lambda: quits.append(1),
        on_hide=lambda: hides.append(1),
    )
    assert tc._hidden is False
    tc.hide()
    assert tc._hidden is True
    assert root.withdrawed is True
    assert hides == [1]
    tc.toggle_visibility()      # 已隐藏 -> show
    assert tc._hidden is False
    assert root.shown is True
    tc.toggle_visibility()      # 已显示 -> hide
    assert tc._hidden is True


def test_tray_on_hotkey_marshals_via_after():
    root = _FakeRoot()
    tc = tray.TrayController(root, on_quit=lambda: None, on_hide=lambda: None)
    tc._on_hotkey()
    assert root.after_calls == 1
    # after 同步执行了 toggle -> hide
    assert tc._hidden is True
