"""Simple Note 入口。"""

import sys
import tkinter as tk
from tkinter import messagebox

import singleinstance

import lang
from lang import t

_GUARD = None    # 单实例互斥体句柄：须持有至进程退出（OS 退出时自动释放）
_LISTENER = None  # 单实例监听线程（早于 Tk 创建，消除启动竞态）


def _start_single_instance_listener():
    """acquire 成功后立即启动监听线程（早于任何 Tk 创建）。

    不传 on_activate：默认分派到 set_activation_handler 注册的模块级回调，
    由 NoteApp 就绪时接线。
    """
    global _LISTENER
    _LISTENER = singleinstance.SingleInstanceListener()
    _LISTENER.start()


def stop_single_instance_listener():
    """mainloop 退出后停掉监听线程（进程即将结束，清理窗口类/消息泵）。"""
    if _LISTENER is not None:
        _LISTENER.stop()


def _startup():
    """首实例启动流程：Pillow 探测 + Tk + NoteApp。"""
    try:
        from PIL import Image  # noqa: F401
    except Exception:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("Simple Note", t("未检测到 Pillow，图片粘贴/缩放功能将不可用。"))
        root.destroy()
        # 缺少 Pillow 时 app→tray 顶层 import PIL 必然 ImportError，探测后直接退出，
        # 不让用户看到带病启动后的裸异常栈。
        sys.exit(1)

    root = tk.Tk()
    from app import NoteApp
    NoteApp(root)
    root.mainloop()


def main():
    global _GUARD
    lang.set_language(lang.detect_system_language())
    _GUARD = singleinstance.acquire()
    if _GUARD is None:
        # 已有实例在运行：尽力激活其窗口，本进程静默退出（不创建任何 Tk 对象）
        singleinstance.activate_existing()
        return
    if _GUARD is not singleinstance.PASS:
        # 真实持有互斥体才需要监听（PASS 为 fail-open：无守卫，多开不受限，不打扰）
        _start_single_instance_listener()
    try:
        _startup()
    finally:
        stop_single_instance_listener()


if __name__ == "__main__":
    main()
