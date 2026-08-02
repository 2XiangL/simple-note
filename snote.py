""".snote 自包含文件格式：zip(content.json + images/<id>.png)。"""

import json
import os
import tempfile
import zipfile

FORMAT = "snote"
VERSION = 1


def build_document(styles, ops, images):
    """组装内存中的 document dict。"""
    return {
        "version": VERSION,
        "format": FORMAT,
        "styles": styles,
        "ops": ops,
        "images": images,
    }


def save_document(path, document, image_blobs=None):
    """把 document 写入 .snote(zip)，原子替换；写入失败不破坏既有文件。

    image_blobs: {img_id: 原始 bytes}，仅写入 document['images'] 中引用且提供的图片。
    """
    image_blobs = image_blobs or {}
    path = str(path)
    parent = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=parent, suffix=".snote.tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("content.json", json.dumps(document, ensure_ascii=False))
            for img_id, meta in document.get("images", {}).items():
                data = image_blobs.get(img_id)
                if data is None:
                    continue
                zf.writestr(meta["file"], data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_document(path):
    """读取 .snote，返回 (document, image_blobs)。

    非 .snote/损坏文件抛 ValueError。缺失的图片 bytes 被容忍（不返回）。
    """
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            if "content.json" not in zf.namelist():
                raise ValueError("missing content.json")
            document = json.loads(zf.read("content.json"))
            names = set(zf.namelist())
            image_blobs = {}
            for img_id, meta in document.get("images", {}).items():
                f = meta.get("file")
                if f and f in names:
                    image_blobs[img_id] = zf.read(f)
    except zipfile.BadZipFile as exc:
        raise ValueError("not a zip / .snote file") from exc

    if document.get("format") != FORMAT:
        raise ValueError("not a .snote document")
    return document, image_blobs
