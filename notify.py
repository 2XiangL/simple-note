"""提醒通知：唤回窗口 + 提示音 + 模态弹框。薄 UI 胶水。"""

import os
import sys
from tkinter import messagebox


def resolve_sound(sound_cfg):
    """纯函数：决定播放哪种提示音。

    返回 ("custom", path) 或 ("system", None)。
    mode == "custom" 且 path 非空、以 .wav 结尾（忽略大小写）且文件存在 -> custom；否则 system。
    """
    if not isinstance(sound_cfg, dict):
        return ("system", None)
    if sound_cfg.get("mode") != "custom":
        return ("system", None)
    path = sound_cfg.get("path")
    if (
        isinstance(path, str)
        and path
        and path.lower().endswith(".wav")
        and os.path.isfile(path)
    ):
        return ("custom", path)
    return ("system", None)


def _play_sound(sound_cfg, root):
    kind, path = resolve_sound(sound_cfg)
    try:
        if sys.platform == "win32":
            import winsound
            if kind == "custom":
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return
    except Exception:
        pass
    try:
        root.bell()
    except Exception:
        pass


def notify(root, title, message, sound_cfg=None):
    """唤回主窗口、播放提示音、弹模态框。任何失败都不阻断弹框。"""
    try:
        root.deiconify()
        root.lift()
        root.focus_force()
    except Exception:
        pass
    _play_sound(sound_cfg, root)
    messagebox.showinfo(title, message)
