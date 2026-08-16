import lang
import notify


def test_resolve_sound_system_mode():
    assert notify.resolve_sound({"mode": "system", "path": ""}) == ("system", None)


def test_resolve_sound_missing_mode():
    assert notify.resolve_sound({"path": "C:/a.wav"}) == ("system", None)


def test_resolve_sound_custom_with_existing_file(tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(b"RIFF")
    assert notify.resolve_sound({"mode": "custom", "path": str(f)}) == ("custom", str(f))


def test_resolve_sound_custom_missing_file_falls_back():
    assert notify.resolve_sound({"mode": "custom", "path": "C:/nope.wav"}) == ("system", None)


def test_resolve_sound_custom_empty_path_falls_back():
    assert notify.resolve_sound({"mode": "custom", "path": ""}) == ("system", None)


def test_resolve_sound_non_dict_cfg():
    assert notify.resolve_sound(None) == ("system", None)
    assert notify.resolve_sound("junk") == ("system", None)


def test_resolve_sound_custom_non_wav_file_falls_back(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"ID3")
    assert notify.resolve_sound({"mode": "custom", "path": str(f)}) == ("system", None)


def test_resolve_sound_custom_uppercase_wav_extension(tmp_path):
    f = tmp_path / "a.WAV"
    f.write_bytes(b"RIFF")
    assert notify.resolve_sound({"mode": "custom", "path": str(f)}) == ("custom", str(f))


def test_resolve_sound_path_is_directory_falls_back(tmp_path):
    assert notify.resolve_sound({"mode": "custom", "path": str(tmp_path)}) == ("system", None)


def test_resolve_sound_non_str_path_falls_back(tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(b"RIFF")
    assert notify.resolve_sound({"mode": "custom", "path": f}) == ("system", None)


def test_format_events_single_and_multi():
    one = [{"kind": "daily", "title": "每日提醒", "message": "喝水"}]
    title, msg = notify.format_events(one)
    assert title == "每日提醒" and msg == "喝水"
    many = [
        {"kind": "pomodoro", "title": "工作结束", "message": "休息"},
        {"kind": "daily", "title": "每日提醒", "message": "喝水"},
    ]
    assert notify.format_events(many) == ("提醒", "工作结束：休息\n每日提醒：喝水")


def test_format_events_english():
    lang.set_language("en")
    try:
        many = [
            {"kind": "pomodoro", "title": "Work finished", "message": "Break"},
            {"kind": "daily", "title": "Daily Reminder", "message": "喝水"},
        ]
        assert notify.format_events(many) == ("Reminder", "Work finished: Break\nDaily Reminder: 喝水")
    finally:
        lang.set_language("zh")
