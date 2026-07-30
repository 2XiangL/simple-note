import settings


def test_default_settings_has_defaults():
    d = settings.default_settings()
    assert d["line_spacing"] == settings.DEFAULT_LINE_SPACING
    assert d["line_spacing"] == "标准"
    assert d["version"] == settings.SETTINGS_VERSION


def test_preset_order_is_three_levels():
    assert settings.PRESET_ORDER == ["紧凑", "标准", "宽松"]


def test_px_for_level_maps_each_preset():
    assert settings.px_for_level("紧凑") == 0
    assert settings.px_for_level("标准") == 4
    assert settings.px_for_level("宽松") == 8


def test_px_for_level_unknown_falls_back_to_default():
    assert settings.px_for_level("不存在的档") == settings.px_for_level(settings.DEFAULT_LINE_SPACING)
    assert settings.px_for_level(None) == 4
