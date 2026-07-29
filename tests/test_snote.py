import json
import zipfile

import pytest

import snote


def _doc():
    styles = {"s1": {"bold": True, "size": 20}}
    ops = [
        {"k": "tagon", "name": "s1"},
        {"k": "text", "text": "Hi"},
        {"k": "tagoff", "name": "s1"},
        {"k": "image", "id": "img1"},
    ]
    images = {"img1": {"file": "images/img1.png", "width": 10, "height": 8}}
    return snote.build_document(styles, ops, images)


def test_build_document_shape():
    doc = _doc()
    assert doc["format"] == "snote"
    assert doc["version"] == 1
    assert doc["ops"][0] == {"k": "tagon", "name": "s1"}


def test_roundtrip_without_images(tmp_path):
    doc = snote.build_document({"s1": {"bold": True}}, [{"k": "text", "text": "x"}], {})
    path = tmp_path / "a.snote"
    snote.save_document(path, doc, {})
    loaded, blobs = snote.load_document(path)
    assert loaded == doc
    assert blobs == {}


def test_roundtrip_with_images(tmp_path):
    doc = _doc()
    path = tmp_path / "b.snote"
    blobs = {"img1": b"PNG-BYTES"}
    snote.save_document(path, doc, blobs)
    loaded, loaded_blobs = snote.load_document(path)
    assert loaded == doc
    assert loaded_blobs == {"img1": b"PNG-BYTES"}


def test_load_bad_zip_raises(tmp_path):
    path = tmp_path / "bad.snote"
    path.write_bytes(b"not a zip")
    with pytest.raises(ValueError):
        snote.load_document(path)


def test_load_missing_content_json_raises(tmp_path):
    path = tmp_path / "nojson.snote"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("other.txt", "x")
    with pytest.raises(ValueError):
        snote.load_document(path)


def test_load_wrong_format_raises(tmp_path):
    path = tmp_path / "wrong.snote"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("content.json", json.dumps({"format": "other", "version": 1}))
    with pytest.raises(ValueError):
        snote.load_document(path)


def test_missing_image_blob_tolerated(tmp_path):
    doc = snote.build_document(
        {}, [{"k": "image", "id": "img1"}], {"img1": {"file": "images/missing.png", "width": 1, "height": 1}}
    )
    path = tmp_path / "c.snote"
    snote.save_document(path, doc, {})  # 不提供 img1 的 bytes
    loaded, blobs = snote.load_document(path)
    assert loaded == doc
    assert blobs == {}
