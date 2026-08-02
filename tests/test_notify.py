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
