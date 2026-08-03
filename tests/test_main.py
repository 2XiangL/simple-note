import main


class _FakeListener:
    def __init__(self, on_activate=None):
        self.on_activate = on_activate
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


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
    # 首实例：持有守卫句柄、启动监听线程并照常进入启动流程
    monkeypatch.setattr(main.singleinstance, "acquire", lambda: "guard-handle")
    monkeypatch.setattr(main.singleinstance, "SingleInstanceListener", _FakeListener)
    roots = []
    loops = []

    class _FakeRoot:
        def mainloop(self):
            loops.append(1)

    monkeypatch.setattr(main.tk, "Tk", lambda: roots.append(1) or _FakeRoot())
    import app as appmod
    monkeypatch.setattr(appmod, "NoteApp", lambda root: None)
    main.main()
    assert len(roots) == 1
    assert loops == [1]
    assert main._GUARD == "guard-handle"


def test_main_fail_open_pass_sentinel_proceeds(monkeypatch):
    # acquire 返回 PASS（非 Windows/Win32 失败）：放行启动，不当作第二实例
    monkeypatch.setattr(main.singleinstance, "acquire", lambda: main.singleinstance.PASS)
    monkeypatch.setattr(main.singleinstance, "SingleInstanceListener", _FakeListener)
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

    class _EventsListener:
        def start(self):
            events.append("listener-start")

        def stop(self):
            events.append("listener-stop")

    monkeypatch.setattr(main.singleinstance, "SingleInstanceListener",
                        lambda: _EventsListener())

    class _FakeRoot:
        def mainloop(self):
            events.append("mainloop")

    monkeypatch.setattr(main.tk, "Tk", lambda: _FakeRoot())
    import app as appmod
    monkeypatch.setattr(appmod, "NoteApp", lambda root: events.append("noteapp"))
    main.main()
    assert events == ["listener-start", "noteapp", "mainloop", "listener-stop"]
