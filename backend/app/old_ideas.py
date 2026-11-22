"""One on-demand, traceable link between current work and an older note."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app import ask, clips, evidence, living_questions, project_records
from backend.app.redact import redact

_GENERIC = {"make", "help", "need", "notes", "good", "work", "used", "use", "keep", "using", "time", "new", "old"}
_CUES = (("earlier dead end", r"\b(failed|dead end|revert(?:ed)?|did not work|didn't work)\b"),
         ("possible counterexample", r"\b(counterexample|exception|only if|unless|did not apply)\b"),
         ("possible transferable lesson", r"\b(lesson|learned|worked|workaround|checklist|because|takeaway)\b"))


def _time(value: str | float | None) -> datetime | None:
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if value:
            date = datetime.fromisoformat(value)
            return date if date.tzinfo else date.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, OSError, OverflowError):
        pass
    return None


def _dismissed(root: Path) -> set[str]:
    with project_records._db(root) as db:
        if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='old_idea_feedback'").fetchone():
            return set()
        return {row[0] for row in db.execute("SELECT id FROM old_idea_feedback WHERE state != 'snooze' OR until > ?",
                                            (living_questions.now(),))}


def suggest(root: Path, brain: dict, question: str, scope: list[dict], *, at: datetime | None = None) -> dict | None:
    question = redact(question.strip())[:2000]
    raw_terms = ask._tokens(question) - _GENERIC
    if len(raw_terms) < 2:
        return None
    at = at or datetime.now(timezone.utc)
    cutoff = at - timedelta(days=30)
    projects = living_questions.current_scope(brain, scope)
    if not projects:
        return None
    index = {project["id"]: project["name"] for project in projects}
    inputs = []
    for rec in brain["files"]:
        if rec["project_id"] not in index or rec.get("kind") != "markdown" or rec.get("name", "").casefold() == "brain_handoff.md":
            continue
        if rec.get("excerpt") and (date := _time(rec.get("mtime"))) and date <= at + timedelta(minutes=5):
            inputs.append({"id": rec["id"], "label": f"{index[rec['project_id']]}/{rec['rel']}",
                           "project_id": rec["project_id"], "kind": "file", "text": rec["excerpt"], "date": date})
    rows, _ = living_questions.scoped_clips(root, projects)
    for clip in rows:
        date = _time(clip.get("captured_at") or clip.get("imported_at"))
        if date and date <= at + timedelta(minutes=5):
            pid = clip["project_id"]
            inputs.append({"id": clips.reference(pid, clip["id"]), "label": f"{index[pid]}/{clip['title']}", "kind": "clip",
                           "project_id": pid, "source_url": clip["url"], "text": clip["content"], "date": date})
    dismissed = _dismissed(root)
    pairs = []
    anchors = sorted((item for item in inputs if item["date"] >= cutoff and len(raw_terms & ask._tokens(item["text"])) >= 2),
                     key=lambda item: (-len(raw_terms & ask._tokens(item["text"])), item["id"]))[:8]
    for current in anchors:
        for item in inputs:
            if item["date"] >= cutoff or " ".join(item["text"].split()) == " ".join(current["text"].split()):
                continue
            old_url, current_url = evidence.canonical_url(item.get("source_url")), evidence.canonical_url(current.get("source_url"))
            if old_url and old_url == current_url:
                continue
            overlap = raw_terms & ask._tokens(item["text"]) & ask._tokens(current["text"])
            if len(overlap) < 2:
                continue
            # Use a sentence that actually contains the cue, not a document-wide claim.
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", item["text"][:8000]):
                relation = next((name for name, cue in _CUES if re.search(cue, sentence, re.I)), None)
                if not relation or len(sentence.strip()) < 25 or not (overlap & ask._tokens(sentence)):
                    continue
                stable = hashlib.sha256(f"{old_url or item['id']}\n{' '.join(sentence.split())}".encode()).hexdigest()
                if stable not in dismissed:
                    pairs.append((len(overlap), stable, relation, sorted(overlap), current, item, sentence))
                break
    if not pairs:
        return None
    _, identifier, relation, overlap, current, previous, sentence = min(pairs, key=lambda x: (-x[0], x[1]))

    def card(item: dict, quote: str) -> dict:
        return {**{key: item[key] for key in ("id", "label", "kind", "project_id", "source_url") if key in item},
                "excerpt": quote, "date": item["date"].date().isoformat()}

    return {"id": identifier, "relation": relation, "question": question, "scope": scope,
            "why": f"Both passages mention {', '.join(overlap[:5])}. The older note may help you test your next step; the situations are not assumed equivalent.",
            "older": card(previous, sentence.strip()[:360]), "current": card(current, ask._matched_excerpt(current["text"], set(overlap)))}


def remember(root: Path, item: dict, action: str) -> None:
    if action not in {"keep", "dismiss", "snooze"}:
        raise ValueError("Unsupported feedback")
    until = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds") if action == "snooze" else None
    with project_records._db(root, True) as db:
        if db.execute("SELECT COUNT(*) FROM old_idea_feedback").fetchone()[0] >= 1000:
            raise ValueError("The local feedback history has reached its limit")
        db.execute("INSERT OR REPLACE INTO old_idea_feedback VALUES (?,?,?)", (item["id"], action, until))
        if action == "keep":
            db.execute("INSERT OR REPLACE INTO kept_old_ideas VALUES (?,?)", (item["id"], json.dumps(item, ensure_ascii=False)))


def kept(root: Path, brain: dict) -> list[dict]:
    with project_records._db(root) as db:
        if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='kept_old_ideas'").fetchone():
            return []
        rows = [json.loads(row[0]) for row in db.execute("SELECT data FROM kept_old_ideas ORDER BY rowid DESC LIMIT 50")]
    mapping = {(p["rel"], p["id"]) for p in brain["projects"]}
    return [dict(id=row["id"], question=row["question"], older=row["older"]["label"], current=row["current"]["label"])
            for row in rows if all((p["rel"], p["id"]) in mapping for p in row["scope"])]
