"""应用级偏好：纯函数读写设置文件（无 Tk 依赖）。"""

import json
import sys
from pathlib import Path

SETTINGS_VERSION = 1
DEFAULT_LINE_SPACING = "标准"

# 档位 -> 像素。PRESET_ORDER 决定菜单顺序。
LINE_SPACING_PRESETS = {"紧凑": 0, "标准": 4, "宽松": 8}
PRESET_ORDER = ["紧凑", "标准", "宽松"]


def default_settings():
    """返回含全部默认值的完整设置 dict。"""
    return {"version": SETTINGS_VERSION, "line_spacing": DEFAULT_LINE_SPACING}


def px_for_level(name):
    """档位名 -> 像素；未知值回退到默认档。"""
    return LINE_SPACING_PRESETS.get(name, LINE_SPACING_PRESETS[DEFAULT_LINE_SPACING])


def settings_path():
    """设置文件默认路径：~/.simple-note/settings.json。"""
    return Path.home() / ".simple-note" / "settings.json"


def load_settings(path=None):
    """读取设置；缺失/损坏/类型错/未知档位均回退默认值，绝不抛。

    path 为 None 时用 settings_path()。返回值总是完整的（含 version 与合法 line_spacing）。
    """
    path = Path(path) if path is not None else settings_path()
    data = default_settings()
    try:
        if not path.exists():
            return data
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as exc:
        print("warning: failed to load settings (%s); using defaults" % exc, file=sys.stderr)
        return data
    if isinstance(raw, dict):
        level = raw.get("line_spacing")
        if level in LINE_SPACING_PRESETS:
            data["line_spacing"] = level
    return data


def save_settings(settings_data, path=None):
    """写入设置；OSError 仅向 stderr 警告，不抛、不阻塞 UI。"""
    path = Path(path) if path is not None else settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(settings_data, f, ensure_ascii=False)
    except OSError as exc:
        print("warning: failed to save settings (%s)" % exc, file=sys.stderr)
