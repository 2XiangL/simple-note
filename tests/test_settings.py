import json

import reminder
import settings


def test_default_settings_has_defaults():
    d = settings.default_settings()
    assert d["line_spacing"] == settings.DEFAULT_LINE_SPACING
    assert d["line_spacing"] == "标准"
    assert d["version"] == settings.SETTINGS_VERSION


def test_pomodoro_default_single_source_in_engine():
    # settings 只是 re-export，引擎（reminder）才是 DEFAULT_POMODORO 的真源
    assert settings.DEFAULT_POMODORO is reminder.DEFAULT_POMODORO


def test_preset_order_is_three_levels():
    assert settings.PRESET_ORDER == ["紧凑", "标准", "宽松"]


def test_px_for_level_maps_each_preset():
    assert settings.px_for_level("紧凑") == 0
    assert settings.px_for_level("标准") == 4
    assert settings.px_for_level("宽松") == 8


def test_px_for_level_unknown_falls_back_to_default():
    assert settings.px_for_level("不存在的档") == settings.px_for_level(settings.DEFAULT_LINE_SPACING)
    assert settings.px_for_level(None) == 4


def test_load_settings_missing_file_returns_default(tmp_path):
    p = tmp_path / "settings.json"
    assert settings.load_settings(p) == settings.default_settings()


def test_load_settings_corrupt_json_returns_default(tmp_path, capsys):
    p = tmp_path / "settings.json"
    p.write_text("{不是合法json", encoding="utf-8")
    d = settings.load_settings(p)
    assert d == settings.default_settings()
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()


def test_load_settings_valid_reads_value(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"version": 1, "line_spacing": "宽松"}', encoding="utf-8")
    expected = settings.default_settings()
    expected["line_spacing"] = "宽松"
    assert settings.load_settings(p) == expected


def test_load_settings_unknown_level_falls_back(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"version": 1, "line_spacing": "怪东西"}', encoding="utf-8")
    d = settings.load_settings(p)
    assert d["line_spacing"] == settings.DEFAULT_LINE_SPACING


def test_load_settings_non_dict_returns_default(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert settings.load_settings(p) == settings.default_settings()


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    settings.save_settings({"version": 1, "line_spacing": "紧凑"}, p)
    expected = settings.default_settings()
    expected["line_spacing"] = "紧凑"
    assert settings.load_settings(p) == expected


def test_save_settings_creates_parent_dir(tmp_path):
    p = tmp_path / "nested" / "dir" / "settings.json"
    settings.save_settings(settings.default_settings(), p)
    assert p.exists()


def test_save_settings_oserror_does_not_raise(tmp_path, capsys):
    # 指向一个已存在的目录作为文件路径 -> 写入触发 OSError
    p = tmp_path / "a_dir"
    p.mkdir()
    settings.save_settings(settings.default_settings(), p)  # 不抛
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()


def test_default_settings_includes_new_keys():
    d = settings.default_settings()
    assert d["sound"] == dict(settings.DEFAULT_SOUND)
    assert d["pomodoro"] == dict(settings.DEFAULT_POMODORO)
    assert d["reminders"] == dict(settings.DEFAULT_REMINDERS)


def test_load_settings_preserves_new_keys(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(
        '{"version": 1, "line_spacing": "紧凑", '
        '"sound": {"mode": "custom", "path": "C:/a.wav"}, '
        '"pomodoro": {"work_min": 30, "break_min": 10, "rounds": 2}, '
        '"reminders": {"oneshot": [], "daily": [{"id": "x", "label": "hi", "hour": 8, "minute": 0}]}}',
        encoding="utf-8",
    )
    d = settings.load_settings(p)
    assert d["sound"] == {"mode": "custom", "path": "C:/a.wav"}
    assert d["pomodoro"] == {"work_min": 30, "break_min": 10, "rounds": 2}
    assert d["reminders"]["daily"][0]["label"] == "hi"


def test_load_settings_old_file_without_new_keys_gets_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"version": 1, "line_spacing": "宽松"}', encoding="utf-8")
    d = settings.load_settings(p)
    assert d["line_spacing"] == "宽松"
    assert d["sound"] == {"mode": "system", "path": ""}
    assert d["pomodoro"] == {"work_min": 25, "break_min": 5, "rounds": 4}
    assert d["reminders"] == {"oneshot": [], "daily": []}


def test_load_settings_wrong_type_new_keys_falls_back(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"version": 1, "sound": "junk", "pomodoro": [1], "reminders": "x"}', encoding="utf-8")
    d = settings.load_settings(p)
    assert d["sound"] == {"mode": "system", "path": ""}
    assert d["pomodoro"] == {"work_min": 25, "break_min": 5, "rounds": 4}
    assert d["reminders"] == {"oneshot": [], "daily": []}


def test_save_failure_keeps_original(tmp_path, monkeypatch):
    p = tmp_path / "s.json"
    settings.save_settings({"version": 1, "line_spacing": "宽松"}, p)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", boom)  # 让写入中途失败
    settings.save_settings({"version": 1, "line_spacing": "紧凑"}, p)
    assert settings.load_settings(p)["line_spacing"] == "宽松", "失败写入破坏了原文件"
    assert [f.name for f in tmp_path.iterdir()] == [p.name], "临时文件未清理"


def test_save_load_roundtrip_with_new_keys(tmp_path):
    p = tmp_path / "settings.json"
    data = settings.default_settings()
    data["pomodoro"] = {"work_min": 50, "break_min": 10, "rounds": 3}
    data["reminders"] = {"oneshot": [], "daily": [{"id": "d1", "label": "喝水", "hour": 8, "minute": 0}]}
    settings.save_settings(data, p)
    assert settings.load_settings(p) == data
