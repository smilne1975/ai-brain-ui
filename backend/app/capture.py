"""Local capture staging. Only explicitly approved web clips join Ask."""

import base64
import binascii
import hashlib
import json
import re
import struct
import zlib

from backend.app import clips, project_records
from backend.app.redact import redact


def _rows(db, project):
    if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='captures'").fetchone():
        return []
    return [json.loads(row[0]) for row in db.execute("SELECT data FROM captures WHERE project=? ORDER BY rowid DESC",
                                                    (project["rel"],))]


def listing(root, project):
    with project_records._db(root) as db:
        return [_public(row) for row in _rows(db, project)]


def _public(item):
    return {key: value for key, value in item.items() if key != "png_data"}


def _insert(root, project, item):
    with project_records._db(root, True) as db:
        rows = _rows(db, project)
        if existing := next((row for row in rows if row["id"] == item["id"]), None):
            return {"status": "duplicate", "item": _public(existing)}
        if len(rows) >= 100:
            raise ValueError("This project queue holds 100 items; remove an item before adding more")
        if item["kind"] == "image" and sum(row["kind"] == "image" for row in rows) >= 10:
            raise ValueError("This project queue holds up to ten PNG captures")
        db.execute("INSERT INTO captures VALUES (?,?,?)", (project["rel"], item["id"], json.dumps(item, ensure_ascii=False)))
    return {"status": "ready for review", "item": _public(item)}


def stage(root, project, text, filename, kind):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip() or "\0" in text:
        raise ValueError("Choose a non-empty text or Markdown item")
    filename = redact(re.split(r"[/\\]", filename)[-1])[:160]
    clip = clips.preview(text, filename) if kind == "clip" else None
    if clip:
        previous = next((row for row in clips.list_clips(root, project) if row["id"] == clip["id"]), None)
        if previous:
            return {"status": "duplicate", "existing_clip": previous}
    content = clip["content"] if clip else redact(text.strip())
    identifier = hashlib.sha256(f"{kind}\0{clip['id'] if clip else text.strip()}".encode()).hexdigest()
    item = {"id": identifier, "kind": kind, "name": clip["title"] if clip else filename or "Pasted capture",
            "content": content, "clip": clip, "state": "staged", "tags": "", "filing": ""}
    return _insert(root, project, item)


def _png(data: str) -> tuple[bytes, int, int]:
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Choose a valid PNG screenshot") from None
    if not 45 <= len(raw) <= 1024 * 1024 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Choose a PNG screenshot up to 1 MiB")
    position = 8
    width = height = 0
    image = False
    for _ in range(500):
        if position + 12 > len(raw):
            break
        size = struct.unpack_from(">I", raw, position)[0]
        end = position + 12 + size
        if end > len(raw):
            break
        chunk = raw[position + 4:end - 4]
        kind = chunk[:4]
        if zlib.crc32(chunk) != struct.unpack_from(">I", raw, end - 4)[0] or kind in {b"acTL", b"fcTL", b"fdAT"}:
            break
        if position == 8:
            if kind != b"IHDR" or size != 13:
                break
            width, height = struct.unpack_from(">II", chunk, 4)
            if width < 1 or height < 1 or width * height > 4_000_000:
                raise ValueError("PNG screenshots may have at most four million pixels")
        if kind == b"IDAT" and size:
            image = True
        if kind == b"IEND":
            if size == 0 and end == len(raw) and image and width and height:
                return raw, width, height
            break
        position = end
    raise ValueError("Choose a complete, non-animated PNG screenshot")


def stage_image(root, project, data, filename):
    raw, width, height = _png(data)
    filename = redact(re.split(r"[/\\]", filename)[-1])[:160]
    identifier = hashlib.sha256(b"image\0" + raw).hexdigest()
    return _insert(root, project, {"id": identifier, "kind": "image", "name": filename or "Screenshot.png",
                                  "content": "", "clip": None, "state": "staged", "tags": "", "filing": "",
                                  "width": width, "height": height, "png_data": data})


def read_image(root, project, identifier):
    with project_records._db(root) as db:
        if db is not None and db.execute("SELECT 1 FROM sqlite_master WHERE name='captures'").fetchone():
            row = db.execute("SELECT data FROM captures WHERE project=? AND id=?", (project["rel"], identifier)).fetchone()
            if row:
                item = json.loads(row[0])
                if item["kind"] == "image":
                    return _png(item["png_data"])[0]
    raise KeyError(identifier)


def change(root, project, identifier, action, tags, filing):
    with project_records._db(root, True) as db:
        entry = db.execute("SELECT data FROM captures WHERE project=? AND id=?", (project["rel"], identifier)).fetchone()
        if entry is None:
            raise KeyError(identifier)
        item = json.loads(entry[0])
        if action == "remove" and item["state"] == "staged":
            db.execute("DELETE FROM captures WHERE project=? AND id=?", (project["rel"], identifier))
            return {"removed": True}
        if action == "approve" and item["state"] == "staged":
            if item["clip"]:
                saved, created = clips.store_preview(root, project, item["clip"])
                if not created:
                    return {"duplicate": saved}
            item.update(state="filed", tags=redact(tags.strip()), filing=redact(filing.strip()))
        elif action == "undo" and item["state"] == "filed":
            if item["clip"]:
                clips.set_active(root, project, item["clip"]["id"], False)
                # The clip has its own restore action. Do not file a second copy from staging.
                item["state"] = "withdrawn"
            else:
                item["state"] = "staged"
        elif action == "remove" and item["state"] == "withdrawn":
            db.execute("DELETE FROM captures WHERE project=? AND id=?", (project["rel"], identifier))
            return {"removed": True}
        else:
            raise ValueError("This capture changed; reload the queue before acting")
        db.execute("UPDATE captures SET data=? WHERE project=? AND id=?",
                   (json.dumps(item, ensure_ascii=False), project["rel"], identifier))
        return {"item": _public(item)}
