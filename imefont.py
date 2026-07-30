"""输入法预编辑窗字体同步（Windows）。

中文输入法打字时，拼音候选窗由系统 IME 绘制，其字体取自 Tk 控件的基础字体，而非
光标处带标签正文的字体——导致拼音字号与正文不一致。本模块通过 ImmSetCompositionFont
把当前样式直接设给控件所属输入上下文（IME context），使预编辑窗与正文同号。
非 Windows 平台为空操作。
"""

import sys

_IS_WIN = sys.platform == "win32"

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    class LOGFONTW(ctypes.Structure):
        _fields_ = [
            ("lfHeight", wintypes.LONG),
            ("lfWidth", wintypes.LONG),
            ("lfEscapement", wintypes.LONG),
            ("lfOrientation", wintypes.LONG),
            ("lfWeight", wintypes.LONG),
            ("lfItalic", wintypes.BYTE),
            ("lfUnderline", wintypes.BYTE),
            ("lfStrikeOut", wintypes.BYTE),
            ("lfCharSet", wintypes.BYTE),
            ("lfOutPrecision", wintypes.BYTE),
            ("lfClipPrecision", wintypes.BYTE),
            ("lfQuality", wintypes.BYTE),
            ("lfPitchAndFamily", wintypes.BYTE),
            ("lfFaceName", wintypes.WCHAR * 32),
        ]

    _imm32 = ctypes.windll.imm32
    _imm32.ImmGetContext.restype = wintypes.LPVOID
    _imm32.ImmGetContext.argtypes = [wintypes.HWND]
    _imm32.ImmReleaseContext.restype = wintypes.BOOL
    _imm32.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.LPVOID]
    _imm32.ImmSetCompositionFontW.restype = wintypes.BOOL
    _imm32.ImmSetCompositionFontW.argtypes = [wintypes.LPVOID, ctypes.POINTER(LOGFONTW)]


def set_composition_font(widget, family, point_size, bold=False, italic=False, strike=False):
    """把控件输入法预编辑窗字体设为 (family, point_size, 粗/斜/删除线)。

    成功返回 True；未取到输入上下文或出错返回 False（调用方可稍后重试）。
    非 Windows 平台恒返回 True（无需同步）。
    """
    if not _IS_WIN:
        return True
    try:
        dpi = widget.winfo_fpixels("1i")  # 每英寸像素数，用于点 -> 像素换算
        lf = LOGFONTW()
        lf.lfHeight = -int(round(point_size * dpi / 72.0))  # 负值=以字符高度刻画
        lf.lfWeight = 700 if bold else 400                    # FW_BOLD / FW_NORMAL
        lf.lfItalic = 1 if italic else 0
        lf.lfStrikeOut = 1 if strike else 0
        lf.lfCharSet = 1  # DEFAULT_CHARSET
        lf.lfFaceName = (family or "")[:31]
        hwnd = widget.winfo_id()
        himc = _imm32.ImmGetContext(hwnd)
        if not himc:
            return False
        try:
            _imm32.ImmSetCompositionFontW(himc, ctypes.byref(lf))
        finally:
            _imm32.ImmReleaseContext(hwnd, himc)
        return True
    except Exception:
        return False
