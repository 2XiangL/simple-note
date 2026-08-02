"""Simple Note 入口。"""

import sys
import tkinter as tk
from tkinter import messagebox


def main():
    try:
        from PIL import Image  # noqa: F401
    except Exception:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("Simple Note", "未检测到 Pillow，图片粘贴/缩放功能将不可用。")
        root.destroy()
        # 缺少 Pillow 时 app→tray 顶层 import PIL 必然 ImportError，探测后直接退出，
        # 不让用户看到带病启动后的裸异常栈。
        sys.exit(1)

    root = tk.Tk()
    from app import NoteApp
    NoteApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
