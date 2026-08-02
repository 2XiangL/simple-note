import imefont


def test_non_windows_returns_true(monkeypatch):
    monkeypatch.setattr(imefont, "_IS_WIN", False)
    assert imefont.set_composition_font(None, "SimSun", 20) is True


def test_set_composition_font_returns_bool(tk_root):
    # 返回值恒为 bool：成功 True、失败 False（调用方据此决定是否缓存可重试）
    import tkinter as tk
    ed = tk.Text(tk_root)
    assert isinstance(imefont.set_composition_font(ed, "SimSun", 20), bool)
