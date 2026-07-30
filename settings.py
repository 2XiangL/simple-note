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
