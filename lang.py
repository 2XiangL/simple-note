"""界面语言：系统语言检测 + 中英翻译。Tk-free 纯逻辑。

语言在启动时经 detect_system_language() 锁定（main.py 调用 set_language）。
翻译以「中文原文即 key」组织：zh 模式 t(key) 原样返回 key，en 模式查
EN_TRANSLATIONS；缺 key 回退 key 本身（漏译退化为中文，绝不抛/绝不空）。
"""

import locale
import os
import sys

EN_TRANSLATIONS = {
    # ---- 通用 / 文件 ----
    "所有文件": "All files",
    "新建": "New",
    "新建笔记": "Untitled",
    "打开": "Open",
    "打开笔记": "Open Note",
    "打开工作区": "Open Workspace",
    "打开工作区...": "Open Workspace...",
    "保存": "Save",
    "另存为": "Save As",
    "退出": "Quit",
    "文件": "File",
    "编辑": "Edit",
    "查看": "View",
    "提醒": "Reminder",
    "关于": "About",
    "关于程序": "About",
    "关闭": "Close",
    "管理提醒...": "Manage Reminders...",
    "开始番茄钟": "Start Pomodoro",
    "停止番茄钟": "Stop Pomodoro",
    "查找": "Find",
    "查找...": "Find...",
    "打开失败": "Open Failed",
    "无法打开该文件：%s": "Cannot open the file: %s",
    "扫描目录失败：%s": "Failed to scan directory: %s",
    "该目录下没有 .snote 笔记文件。": "No .snote note files in this directory.",
    "…等 %d 个": "...and %d more",
    "已加载 %d 个，跳过重复 %d 个，失败 %d 个：\n%s": "Loaded %d, skipped %d duplicates, failed %d:\n%s",
    "保存失败": "Save Failed",
    "写入失败：%s": "Write failed: %s",
    "“%s”未保存，是否保存？": "\"%s\" is not saved. Save it?",
    "关于 Simple Note": "About Simple Note",
    "Simple Note\n轻量化本地便签工具\nTkinter + Pillow": "Simple Note\nA lightweight local notes app\nTkinter + Pillow",
    "Simple Note — %s %s（%s）": "Simple Note — %s %s (%s)",
    "%s：%s": "%s: %s",
    # ---- 行距档位（仅显示层；settings.json 内部键保持中文）----
    "紧凑": "Compact",
    "标准": "Standard",
    "宽松": "Relaxed",
    # ---- 工具栏 ----
    "颜色": "Color",
    "选择颜色": "Choose Color",
    # ---- 托盘 ----
    "显示/隐藏": "Show/Hide",
    # ---- 查找对话框 ----
    "上一个": "Previous",
    "下一个": "Next",
    "区分大小写": "Match Case",
    "共 %d 处": "%d matches",
    "无匹配": "No matches",
    # ---- 提醒对话框 ----
    "提醒管理": "Manage Reminders",
    "番茄钟": "Pomodoro",
    "工作(分)": "Work (min)",
    "休息(分)": "Break (min)",
    "轮数": "Rounds",
    "开始": "Start",
    "停止": "Stop",
    "提醒列表": "Reminder List",
    "类型": "Type",
    "内容": "Content",
    "时间": "Time",
    "删除选中": "Delete Selected",
    "删除提醒": "Delete Reminder",
    "确认删除选中项？": "Delete the selected item(s)?",
    "新增提醒（每日忽略日期）": "Add Reminder (date ignored for daily)",
    "每日": "Daily",
    "一次性": "One-time",
    "日期": "Date",
    "时": "h",
    "分": "min",
    "添加": "Add",
    "提示音": "Sound",
    "系统提示音": "System Sound",
    "自定义音频": "Custom Audio",
    "浏览...": "Browse...",
    "试听": "Preview",
    "提示音试听": "Sound preview",
    "选择音频文件": "Choose Audio File",
    "Wave 音频": "Wave audio",
    "参数格式不正确。": "Invalid parameter format.",
    "请填写内容。": "Please enter content.",
    "新增提醒": "Add Reminder",
    "时间格式不正确。": "Invalid time format.",
    "时间超出范围（时 0–23，分 0–59）。": "Time out of range (hour 0–23, minute 0–59).",
    "日期格式应为 YYYY-MM-DD。": "Date must be in YYYY-MM-DD format.",
    "时间必须晚于当前。": "Time must be later than now.",
    "每天 %02d:%02d": "Every day %02d:%02d",
    # ---- 番茄钟 / 提醒事件 ----
    "工作中": "Working",
    "休息中": "On break",
    "第%d/共%d轮": "Round %d/%d",
    "番茄钟完成": "Pomodoro finished",
    "已完成全部 %d 轮，休息一下吧。": "All %d rounds done. Take a break!",
    "工作结束": "Work finished",
    "第 %d 轮工作结束，休息 %d 分钟。": "Round %d work finished. Break for %d minutes.",
    "休息结束": "Break finished",
    "开始第 %d 轮工作（%d 分钟）。": "Starting round %d work (%d minutes).",
    "每日提醒": "Daily Reminder",
    # ---- main.py ----
    "未检测到 Pillow，图片粘贴/缩放功能将不可用。": "Pillow not detected. Image paste/resize will be unavailable.",
}

_lang = None  # None = 尚未确定（首次 get_language() 惰性检测）


def _win_lcid():
    """Windows 用户界面语言 LANGID（GetUserDefaultUILanguage 返回 LANGID）；非 Windows 或 API 失败返回 None。"""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        return ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except Exception:
        return None


def _locale_code():
    """当前 locale 代码（如 "zh_CN.UTF-8"）；失败回退 LANG 环境变量，再失败 None。"""
    try:
        code, _enc = locale.getlocale(locale.LC_CTYPE)
    except Exception:
        code = None
    if not code:
        code = os.environ.get("LANG")
    return code


def detect_system_language():
    """返回 "zh"（任何中文变体，含繁体）或 "en"。英文兜底。"""
    lcid = _win_lcid()
    if lcid is not None:
        return "zh" if (lcid & 0x3FF) == 0x04 else "en"
    code = _locale_code()
    if code:
        return "zh" if code.lower().replace("_", "-").startswith("zh") else "en"
    return "en"


def set_language(code):
    """显式覆盖语言；None 重置为自动检测（测试惰性检测用）；非法值归 "en"。"""
    global _lang
    if code in (None, "zh", "en"):
        _lang = code
    else:
        _lang = "en"


def get_language():
    """当前语言；未设置时惰性检测并缓存。"""
    global _lang
    if _lang is None:
        _lang = detect_system_language()
    return _lang


def t(key):
    """取当前语言的文案。zh 原样返回；en 查 EN_TRANSLATIONS，缺 key 回退 key。"""
    if get_language() == "en":
        return EN_TRANSLATIONS.get(key, key)
    return key
