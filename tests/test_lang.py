"""lang 模块：语言检测、覆盖与翻译。无显示器可跑。"""

import lang


def test_detect_lcid_chinese_variants(monkeypatch):
    for lcid in (0x0804, 0x0404, 0x0C04, 0x1004, 0x1404):  # zh-CN/TW/HK/SG/MO
        monkeypatch.setattr(lang, "_win_lcid", lambda lcid=lcid: lcid)
        assert lang.detect_system_language() == "zh"


def test_detect_lcid_english(monkeypatch):
    monkeypatch.setattr(lang, "_win_lcid", lambda: 0x0409)  # en-US
    assert lang.detect_system_language() == "en"


def test_detect_falls_back_to_locale(monkeypatch):
    monkeypatch.setattr(lang, "_win_lcid", lambda: None)  # 非 Windows / 调用失败
    monkeypatch.setattr(lang, "_locale_code", lambda: "zh_CN.UTF-8")
    assert lang.detect_system_language() == "zh"
    monkeypatch.setattr(lang, "_locale_code", lambda: "en_US.UTF-8")
    assert lang.detect_system_language() == "en"
    monkeypatch.setattr(lang, "_locale_code", lambda: None)  # 无法判定 -> en
    assert lang.detect_system_language() == "en"


def test_set_and_get_language():
    lang.set_language("en")
    assert lang.get_language() == "en"
    lang.set_language("zh")
    assert lang.get_language() == "zh"
    lang.set_language("fr")  # 非法值归 en
    assert lang.get_language() == "en"


def test_get_language_lazy_detects(monkeypatch):
    monkeypatch.setattr(lang, "_win_lcid", lambda: 0x0409)
    lang.set_language(None)  # 重置为自动检测
    assert lang.get_language() == "en"
    monkeypatch.setattr(lang, "_win_lcid", lambda: 0x0804)
    lang.set_language(None)
    assert lang.get_language() == "zh"


def test_t_zh_returns_key_as_is():
    lang.set_language("zh")
    assert lang.t("保存") == "保存"
    assert lang.t("共 %d 处") == "共 %d 处"


def test_t_en_translates_and_formats():
    lang.set_language("en")
    assert lang.t("保存") == "Save"
    assert lang.t("共 %d 处") % 3 == "3 matches"


def test_t_en_missing_key_falls_back():
    lang.set_language("en")
    assert lang.t("从未见过的文案") == "从未见过的文案"


def test_en_dict_complete_and_nonempty():
    lang.set_language("en")
    lang.set_language(None)  # 防御：恢复自动检测由 conftest 兜底
    assert lang.EN_TRANSLATIONS, "EN_TRANSLATIONS 不得为空"
    for key, value in lang.EN_TRANSLATIONS.items():
        assert value, "译文不得为空: %r" % key
        assert value != key, "译文不得与原文相同: %r" % key


def test_en_dict_covers_all_t_callsites():
    """扫描仓库根目录 *.py 中所有 t("...") 调用点，key 必须都在 EN_TRANSLATIONS。

    防漏译：新 UI 文案忘了补译文时，en 模式会退化为中文，本测试即失败。
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    keys = set()
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        keys.update(re.findall(r'\bt\("([^"]*)"\)', text))
    keys.discard("")  # t("") 不算文案
    missing = sorted(keys - set(lang.EN_TRANSLATIONS))
    assert not missing, "以下 t() 调用点缺少英文译文: %s" % missing
