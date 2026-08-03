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
    roots = []

    class _FakeRoot:
        def mainloop(self):
            pass

    def _fake_tk():
        r = _FakeRoot()
        roots.append(r)
        return r

    monkeypatch.setattr(main.tk, "Tk", _fake_tk)
    import app as appmod
    monkeypatch.setattr(appmod, "NoteApp", lambda root: None)
    main.main()
    assert len(roots) == 1
    assert main._GUARD == "guard-handle"
