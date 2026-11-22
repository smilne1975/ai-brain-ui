"""Reviewed project memory, fact corrections and explicitly owned task handoffs."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.app import knowledge
from backend.app.redact import redact

KINDS = {"decision", "constraint", "gotcha", "failed attempt", "fact", "handoff"}
FACT_STATES = {"confirmed", "inferred", "unknown"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _path(root: Path) -> Path:
    path = root.resolve() / ".brain" / "project-records.sqlite"
    if path.resolve() != path:
        raise ValueError("Project records cannot use linked storage")
    return path


@contextmanager
def _db(root: Path, write: bool = False):
    path = _path(root)
    if not write and not path.is_file():
        yield None
        return
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path if write else path.as_uri() + "?mode=ro", uri=not write, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        with db:
            if write:
                db.execute("""CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, project TEXT NOT NULL,
                            revision INTEGER NOT NULL, data TEXT NOT NULL)""")
                db.execute("""CREATE TABLE IF NOT EXISTS record_log (record_id TEXT NOT NULL, revision INTEGER NOT NULL,
                            project TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (record_id, revision))""")
                db.execute("CREATE INDEX IF NOT EXISTS records_project ON records(project)")
                db.execute("""CREATE TABLE IF NOT EXISTS recall_receipts (id TEXT PRIMARY KEY, project TEXT NOT NULL,
                            data TEXT NOT NULL)""")
                db.execute("CREATE TABLE IF NOT EXISTS living_questions (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL)")
                db.execute("CREATE TABLE IF NOT EXISTS old_idea_feedback (id TEXT PRIMARY KEY, state TEXT NOT NULL, until TEXT)")
                db.execute("CREATE TABLE IF NOT EXISTS kept_old_ideas (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
                db.execute("CREATE TABLE IF NOT EXISTS link_reviews (project TEXT, id TEXT, state TEXT NOT NULL, PRIMARY KEY (project, id))")
                db.execute("CREATE TABLE IF NOT EXISTS captures (project TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY (project, id))")
                db.execute("BEGIN IMMEDIATE")
            yield db
    finally:
        db.close()


def _clean(value: str | None, limit: int) -> str:
    return redact((value or "").strip())[:limit]


def _source_records(root: Path, brain: dict, project: dict, ids: list[str]) -> list[dict]:
    result = knowledge._sources(root, brain, project["id"], ids)
    if {source["id"] for source in result} != set(ids):
        raise ValueError("Select readable evidence in this project, or leave the fact unknown")
    return [{key: value for key, value in source.items() if key != "file_identity"} for source in result]


def _encode(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False)


def _write(db, scope: str, record: dict, old_revision: int | None = None):
    data = _encode(record)
    if old_revision is None:
        db.execute("INSERT INTO records VALUES (?,?,?,?)", (record["id"], scope, record["revision"], data))
    elif db.execute("UPDATE records SET revision=?, data=? WHERE id=? AND project=? AND revision=?",
                    (record["revision"], data, record["id"], scope, old_revision)).rowcount != 1:
        raise ValueError("The record changed; reload it before saving")
    db.execute("INSERT INTO record_log VALUES (?,?,?,?)", (record["id"], record["revision"], scope, data))


def _get(db, scope: str, identifier: str) -> dict:
    row = db.execute("SELECT data FROM records WHERE id=? AND project=?", (identifier, scope)).fetchone()
    if row is None:
        raise KeyError(identifier)
    return json.loads(row["data"])


def _entry(root: Path, brain: dict, project: dict, payload: dict, previous: dict | None = None) -> dict:
    kind, state = payload["kind"], payload.get("state")
    title, text, next_step, intended = (_clean(payload.get(key), length) for key, length in
        (("title", 140), ("text", 3000), ("next_step", 1200), ("intended", 120)))
    if kind not in KINDS or not title or not text:
        raise ValueError("A record type, subject and content are required")
    if previous and (previous["kind"] != kind or kind == "handoff"):
        raise ValueError("Only facts and memory entries can be edited in place")
    if kind == "fact" and state not in FACT_STATES:
        raise ValueError("Label the fact confirmed, inferred, or unknown")
    sources = _source_records(root, brain, project, payload.get("source_ids") or [])
    if kind != "handoff" and not sources and not (kind == "fact" and state == "unknown"):
        raise ValueError("Pick supporting evidence or mark a fact unknown")
    if kind == "handoff" and not next_step:
        raise ValueError("A handoff needs a next step")
    references = {rec["rel"]: rec for rec in brain["files"] if rec["id"] in {source["id"] for source in sources}}
    web_quotes = knowledge._clip_quote_sources(root, project, sources)
    if problem := next(knowledge._quote_problems(root, text, references, web_quotes), None):
        raise ValueError(problem)
    now = _now()
    return {"id": previous["id"] if previous else uuid4().hex, "revision": previous["revision"] + 1 if previous else 1,
            "kind": kind, "state": state if kind == "fact" else "pending" if kind == "handoff" else "reviewed",
            "title": title, "text": text, "next_step": next_step, "intended": intended, "owner": None,
            "sources": sources, "created_at": previous["created_at"] if previous else now, "updated_at": now,
            "memory": [], "session": payload.get("session") if kind == "handoff" else None}


def save(root: Path, brain: dict, project: dict, payload: dict, identifier: str | None = None, expected: int | None = None) -> dict:
    scope = project["rel"]
    with _db(root, True) as db:
        prior = _get(db, scope, identifier) if identifier else None
        if prior and expected != prior["revision"]:
            raise ValueError("The record changed; reload it before saving")
        if not prior and db.execute("SELECT COUNT(*) FROM records WHERE project=?", (scope,)).fetchone()[0] >= 500:
            raise ValueError("This project has reached its limit of 500 records")
        entry = _entry(root, brain, project, payload, prior)
        if entry["kind"] == "handoff":
            for memory_id in dict.fromkeys(payload.get("memory_ids") or []):
                item = _get(db, scope, memory_id)
                if item["state"] not in {"reviewed", "confirmed"} or _stale(root, brain, project, item):
                    raise ValueError("Handoff memory must be reviewed and supported by current evidence")
                entry["memory"].append({key: item[key] for key in ("id", "title", "revision", "text")})
        _write(db, scope, entry, prior["revision"] if prior else None)
    return entry


def transition(root: Path, project: dict, identifier: str, action: str, actor: str, expected: int) -> dict:
    actor = _clean(actor, 120)
    if not actor:
        raise ValueError("Enter the name that is taking this action")
    scope = project["rel"]
    with _db(root, True) as db:
        row = _get(db, scope, identifier)
        if row["kind"] != "handoff" or row["revision"] != expected:
            raise ValueError("The handoff changed; reload it before acting")
        states = {"claim": "claimed", "complete": "completed", "cancel": "cancelled"}
        allowed = (action == "claim" and row["state"] == "pending" or
                   action == "complete" and row["state"] == "claimed" and row["owner"] == actor or
                   action == "cancel" and (row["state"] == "pending" or row["state"] == "claimed" and row["owner"] == actor))
        if not allowed:
            raise ValueError("A handoff can be claimed once; only its claimant can complete or cancel a claimed handoff")
        row.update(state=states[action], actor=actor, updated_at=_now(), revision=expected + 1)
        if action == "claim":
            row["owner"] = actor
        _write(db, scope, row, expected)
    return row


def _stale(root: Path, brain: dict, project: dict, row: dict) -> list[str]:
    fresh = {source["id"]: source["sha256"] for source in knowledge._sources(
        root, brain, project["id"], [source["id"] for source in row["sources"]])}
    return [source["id"] for source in row["sources"] if fresh.get(source["id"]) != source["sha256"]]


def board(root: Path, brain: dict, project: dict) -> dict:
    with _db(root) as db:
        if db is None:
            return {"items": [], "history": []}
        scope = project["rel"]
        rows = [json.loads(row["data"]) for row in db.execute("SELECT data FROM records WHERE project=?", (scope,))]
        history = [json.loads(row["data"]) for row in db.execute(
            "SELECT data FROM record_log WHERE project=? ORDER BY rowid DESC LIMIT 50", (scope,))]
    revisions = {record["id"]: record["revision"] for record in rows}
    referenced = {source["id"] for row in rows for source in row["sources"]}
    fingerprints = {}
    if referenced:
        # _sources has a per-call cap; batch the distinct IDs only once.
        unique = sorted(referenced)
        for offset in range(0, len(unique), 20):
            fingerprints.update({source["id"]: source["sha256"] for source in knowledge._sources(
                root, brain, project["id"], unique[offset:offset + 20])})
    for row in rows:
        row["stale_sources"] = [source["id"] for source in row["sources"] if fingerprints.get(source["id"]) != source["sha256"]]
    stale = {row["id"] for row in rows if row["stale_sources"]}
    for row in rows:
        row["stale_memory"] = [ref["id"] for ref in row["memory"] if revisions.get(ref["id"]) != ref["revision"] or ref["id"] in stale]
    return {"items": sorted(rows, key=lambda row: row["updated_at"], reverse=True), "history": history}


def store_receipt(root: Path, project: dict, payload: dict) -> dict:
    row = {**payload, "id": uuid4().hex, "at": _now(), "delivery": "response prepared; use not confirmed"}
    with _db(root, True) as db:
        db.execute("INSERT INTO recall_receipts VALUES (?,?,?)", (row["id"], project["rel"], _encode(row)))
        db.execute("DELETE FROM recall_receipts WHERE project=? AND rowid NOT IN (SELECT rowid FROM recall_receipts WHERE project=? ORDER BY rowid DESC LIMIT 100)",
                   (project["rel"], project["rel"]))
    return row


def receipts(root: Path, project: dict) -> list[dict]:
    with _db(root) as db:
        if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='recall_receipts'").fetchone():
            return []
        return [json.loads(row["data"]) for row in db.execute(
            "SELECT data FROM recall_receipts WHERE project=? ORDER BY rowid DESC LIMIT 100", (project["rel"],))]


def brief_memory(root: Path, brain: dict, project: dict) -> dict:
    try:
        reviewed = [row for row in board(root, brain, project)["items"] if row["state"] in {"reviewed", "confirmed"}]
    except (OSError, sqlite3.Error, ValueError):
        return {"items": [], "stale_count": 0, "unavailable": True}
    current = [row for row in reviewed if not row["stale_sources"]]
    return {"items": [{"title": row["title"], "kind": row["kind"], "text": row["text"][:300],
                       "references": [source["rel"] for source in row["sources"]][:4]} for row in current[:4]],
            "stale_count": len(reviewed) - len(current)}
