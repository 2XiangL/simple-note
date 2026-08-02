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


def test_tray_on_hotkey_marshals_via_queue():
    root = _FakeRoot()
    tc = tray.TrayController(root, on_quit=lambda: None, on_hide=lambda: None)
    tc._on_hotkey()          # 模拟监听线程入队（不碰 Tk）
    assert tc._hidden is False
    tc._drain()              # 主线程消费 -> toggle -> hide
    assert tc._hidden is True
    assert root.withdrawed is True


def test_hotkey_status_reported_asynchronously_via_queue():
    # 启动不再阻塞等待热键注册：监听线程的注册结果经 _marshal 封送，
    # 主线程 _drain 消费后才更新 status()（消费前保持未知 None）。
    root = _FakeRoot()
    tc = tray.TrayController(root, on_quit=lambda: None, on_hide=lambda: None)
    assert tc.status() == (False, None, 0)
    marshal_status = lambda reg, err: tc._marshal(lambda: tc._on_hotkey_status(reg, err))
    marshal_status(False, 1409)                      # 模拟注册失败（热键被占用）
    assert tc.status() == (False, None, 0)           # 尚未消费
    tc._drain()
    assert tc.status() == (False, False, 1409)
    marshal_status(True, 0)                          # 模拟注册成功
    tc._drain()
    assert tc.status() == (False, True, 0)


def test_hotkey_status_failure_prints_warning(capsys):
    root = _FakeRoot()
    tc = tray.TrayController(root, on_quit=lambda: None, on_hide=lambda: None)
    tc._on_hotkey_status(False, 1409)
    out = capsys.readouterr().out
    assert "已被其他程序占用" in out
    tc._on_hotkey_status(False, 5)
    out = capsys.readouterr().out
    assert "GetLastError=5" in out
    tc._on_hotkey_status(True, 5)   # 注册成功但消息泵 GetMessageW 失败
    out = capsys.readouterr().out
    assert "GetMessageW" in out
    assert tc.status() == (False, True, 5)
