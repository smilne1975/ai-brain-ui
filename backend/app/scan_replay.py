"""Bounded, local snapshots of the observed file index, not of file contents."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

from backend.app import store
from backend.app.privacy import active

KEEP = 24
MAX_CHANGES = 250


def record(root: Path, brain: dict) -> None:
    if active() or brain.get("private_policy"):
        return
    manifest = json.dumps({row["id"]: [row["project_id"], row["rel"], row.get("observed")]
                           for row in brain["files"] if row["kind"] != "env"}, sort_keys=True)
    truncated = int(bool(brain.get("truncated")))
    with closing(store._connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        last = db.execute("SELECT manifest, truncated FROM scan_frames WHERE root=? ORDER BY id DESC LIMIT 1",
                          (str(root),)).fetchone()
        if last == (manifest, truncated):
            return
        db.execute("INSERT INTO scan_frames(root, scanned_at, manifest, truncated) VALUES (?, ?, ?, ?)",
                   (str(root), brain["scanned_at"], manifest, truncated))
        db.execute("""DELETE FROM scan_frames WHERE root=? AND id NOT IN
                   (SELECT id FROM scan_frames WHERE root=? ORDER BY id DESC LIMIT ?)""", (str(root), str(root), KEEP))


def frames(root: Path, frame_id: int | None, project_id: str | None) -> dict:
    if active():
        return {"disabled": True, "frames": [], "comparison": None}
    with closing(store._connect()) as db:
        rows = db.execute("SELECT id, scanned_at, truncated, manifest FROM scan_frames WHERE root=? ORDER BY id",
                          (str(root),)).fetchall()
    result = {"disabled": False, "frames": [{"id": row[0], "at": row[1]} for row in rows], "comparison": None}
    if not rows:
        return result
    index = next((i for i, row in enumerate(rows) if row[0] == frame_id), -1) if frame_id is not None else len(rows) - 1
    if index < 0:
        raise KeyError(frame_id)
    after = rows[index]
    before = rows[index - 1] if index else None
    changes = []
    if before is not None:
        old, new = json.loads(before[3]), json.loads(after[3])
        for key in old.keys() | new.keys():
            prior, current = old.get(key), new.get(key)
            project, rel, _ = current if current is not None else prior
            if project_id is not None and project != project_id:
                continue
            state = ("added" if prior is None else "unlisted" if current is None else
                     "changed" if prior[2] is not None and current[2] is not None and prior[2] != current[2] else None)
            if state:
                changes.append({"id": key, "project_id": project, "rel": rel, "state": state})
    changes.sort(key=lambda item: (item["state"], item["project_id"], item["rel"].casefold(), item["id"]))
    result["comparison"] = {"id": after[0], "before": before[1] if before else None, "after": after[1],
                            "incomplete": bool(after[2] or (before and before[2])),
                            "omitted": max(0, len(changes) - MAX_CHANGES), "changes": changes[:MAX_CHANGES]}
    return result
