import util


def test_merge_style_overwrites_and_sets():
    assert util.merge_style({"bold": True}, {"size": 20}) == {"bold": True, "size": 20}


def test_merge_style_none_removes_key():
    assert util.merge_style({"bold": True, "size": 20}, {"bold": None}) == {"size": 20}


def test_merge_style_empty_base():
    assert util.merge_style({}, {"italic": True}) == {"italic": True}


def test_style_to_font_basic():
    assert util.style_to_font({}) == ("TkDefaultFont", 20, "")


def test_style_to_font_bold_italic_size():
    assert util.style_to_font({"bold": True, "italic": True, "size": 20}) == (
        "TkDefaultFont",
        20,
        "bold italic",
    )


def test_style_to_tag_config_strike_and_fg():
    cfg = util.style_to_tag_config({"strike": True, "fg": "#ff0000", "size": 14})
    assert cfg["font"] == ("TkDefaultFont", 14, "")
    assert cfg["overstrike"] == 1
    assert cfg["foreground"] == "#ff0000"


def test_style_to_tag_config_no_strike_omits_key():
    cfg = util.style_to_tag_config({"bold": True})
    assert "overstrike" not in cfg
    assert "foreground" not in cfg
    assert cfg["font"] == ("TkDefaultFont", 20, "bold")


def test_get_clipboard_image_rejects_non_image(monkeypatch):
    # 剪贴板复制文件时 grabclipboard 返回路径列表，必须视为无图返回 None，
    # 否则 _on_paste 会把 list 当 PIL.Image 处理而崩溃。
    from PIL import ImageGrab
    monkeypatch.setattr(ImageGrab, "grabclipboard", lambda: ["C:/x.png"])
    assert util.get_clipboard_image() is None
