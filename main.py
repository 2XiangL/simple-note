"""Simple Note 入口。"""

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

    root = tk.Tk()
    from app import NoteApp
    NoteApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
