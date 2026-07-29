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
