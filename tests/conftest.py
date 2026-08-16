import lang
import tkinter as tk

import pytest


@pytest.fixture()
def tk_root():
    try:
        root = tk.Tk()
    except Exception as exc:  # 无显示环境
        pytest.skip("no display for Tk: %s" % exc)
    root.withdraw()
    yield root
    try:
        root.update()
        root.destroy()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _force_lang_zh():
    """强制 zh 语言：现有测试断言中文文案，须与运行机系统语言解耦。"""
    saved = lang.get_language()
    lang.set_language("zh")
    yield
    lang.set_language(saved)
