"""Local capture staging. Only explicitly approved web clips join Ask."""

import hashlib
import json
import re

from backend.app import clips, project_records
from backend.app.redact import redact


def _rows(db, project):
    if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='captures'").fetchone():
        return []
    return [json.loads(row[0]) for row in db.execute("SELECT data FROM captures WHERE project=? ORDER BY rowid DESC",
                                                    (project["rel"],))]


def listing(root, project):
    with project_records._db(root) as db:
        return _rows(db, project)


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
    with project_records._db(root, True) as db:
        rows = _rows(db, project)
        if existing := next((row for row in rows if row["id"] == identifier), None):
            return {"status": "duplicate", "item": existing}
        if len(rows) >= 100:
            raise ValueError("This project queue holds 100 items; remove an item before adding more")
        db.execute("INSERT INTO captures VALUES (?,?,?)", (project["rel"], identifier, json.dumps(item, ensure_ascii=False)))
    return {"status": "ready for review", "item": item}


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
        return {"item": item}
