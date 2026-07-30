"""纯函数：富文本样式逻辑 + 剪贴板图片工具。"""

DEFAULT_FAMILY = "TkDefaultFont"
DEFAULT_SIZE = 20


def merge_style(base, delta):
    """返回 base 合并 delta 后的新样式 dict。

    delta 值为 None 表示删除该键；否则覆盖/新增。
    """
    merged = dict(base)
    for key, value in delta.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def style_to_font(style, family=DEFAULT_FAMILY, base_size=DEFAULT_SIZE):
    """构造 Tk 字体元组 (family, size, flags)。"""
    size = style.get("size", base_size)
    flags = []
    if style.get("bold"):
        flags.append("bold")
    if style.get("italic"):
        flags.append("italic")
    return (family, size, " ".join(flags))


def style_to_tag_config(style, family=DEFAULT_FAMILY, base_size=DEFAULT_SIZE):
    """根据样式 dict 生成 Text.tag_configure 的关键字参数。"""
    config = {"font": style_to_font(style, family, base_size)}
    if style.get("strike"):
        config["overstrike"] = 1
    if "fg" in style:
        config["foreground"] = style["fg"]
    return config


def get_clipboard_image():
    """从剪贴板获取 PIL.Image，无图或失败返回 None。"""
    try:
        from PIL import ImageGrab
    except Exception:
        return None
    try:
        img = ImageGrab.grabclipboard()
    except Exception:
        return None
    return img
