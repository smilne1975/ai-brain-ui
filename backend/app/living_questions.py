"""Local, manually reviewed evidence changes for personally followed questions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from backend.app import ask, clips, evidence, project_records, knowledge
from backend.app.redact import redact


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def scope_for(brain: dict, requested: list[str] | None) -> list[dict]:
    requested_ids = set(requested or ())
    projects = [{key: p[key] for key in ("id", "rel", "name")} for p in brain["projects"]
                if not requested_ids or p["id"] in requested_ids]
    if not projects or len(projects) > 200 or requested_ids - {p["id"] for p in projects}:
        raise ValueError("Select one or more currently indexed projects (up to 200)")
    return projects


def current_scope(brain: dict, scope: list[dict]) -> list[dict]:
    relative = {item["rel"] for item in scope}
    return [project for project in brain["projects"] if project["rel"] in relative]


def scoped_clips(root: Path, projects: list[dict]) -> tuple[list[dict], bool]:
    result = []
    incomplete = False
    for project in projects:
        try:
            for clip in clips.list_clips(root, project):
                if clip["active"]:
                    result.append({**clip, "project_id": project["id"]})
                if len(result) > 200:
                    return result[:200], True
        except (OSError, ValueError):
            incomplete = True
    return result, incomplete


def snapshot(root: Path, brain: dict, row: dict) -> dict:
    projects = current_scope(brain, row["scope"])
    if not projects:
        return {"items": [], "incomplete": True, "missing_scopes": len(row["scope"])}
    clip_rows, clip_gaps = scoped_clips(root, projects)
    report = ask.answer(brain, f"{row['question']} {row['challenge']}", None, None, project_ids=[project["id"] for project in projects],
                        web_clips=clip_rows, origins=evidence.confirmed_origins(root), local_review=True)
    terms = [term.casefold() for term in row["challenge"].split(";") if len(term.strip()) >= 4]
    files = {item["id"]: item for item in brain["files"]}
    clip_hashes = {clips.reference(item["project_id"], item["id"]): clips.fingerprint(item) for item in clip_rows}
    file_hashes = {}
    items = []
    for rep in report["evidence"]:
        copies = [rep, *rep.get("repeated_sources", [])]
        if origin := rep.get("confirmed_origin"):
            copies = [item for item in copies if evidence.canonical_url(item.get("source_url")) == origin] or [rep]
        # An original's already-seen passage is unchanged if a repost has simply joined it.
        for item in copies:
            excerpt = " ".join(item["excerpt"].split())
            if not excerpt:
                continue
            source = evidence.canonical_url(item.get("source_url")) or f"{item['id']}:{item.get('page', '')}"
            fingerprint = hashlib.sha256(excerpt.encode()).hexdigest()
            entry = {key: item[key] for key in ("id", "label", "kind", "project_id", "excerpt", "source_url", "page") if key in item}
            entry.update(source=source, fingerprint=fingerprint,
                          challenge=any(term.strip() in excerpt.casefold() for term in terms))
            if not any(prev["fingerprint"] == fingerprint or prev["source"] == source for prev in items):
                if item["id"] in files and item["id"] not in file_hashes:
                    file_hashes[item["id"]] = knowledge._fingerprint(root, files[item["id"]])
                entry["source_sha256"] = file_hashes.get(item["id"]) or clip_hashes.get(item["id"])
                items.append(entry)
            if len(items) >= 30:
                break
        if len(items) >= 30:
            break
    missing = len(row["scope"]) - len(projects)
    covered_ids = {project["id"] for project in projects}
    gaps = any(item["project_id"] in covered_ids and item["status"] in {"partial", "unreadable"}
               for item in brain.get("coverage", {}).get("issues", []))
    return {"items": items, "incomplete": bool(report["incomplete"] or missing or clip_gaps or gaps or len(items) >= 30),
            "missing_scopes": missing}


def compare(prior: dict, candidate: dict) -> dict:
    previous_sources = {item["source"]: item for item in prior["items"]}
    current_sources = {item["source"]: item for item in candidate["items"]}
    old_text = {item["fingerprint"] for item in prior["items"]}
    new_text = {item["fingerprint"] for item in candidate["items"]}
    changes = []
    for item in candidate["items"]:
        before = previous_sources.get(item["source"])
        if item["fingerprint"] in old_text:
            continue
        changes.append({"type": "possible challenge" if item["challenge"] else "changed passage" if before else "new matching evidence",
                        "before": before, "after": item})
    # A hit that fell beyond the retrieval/coverage bound is not a confirmed removal.
    for before in prior["items"]:
        if before["source"] not in current_sources and before["fingerprint"] not in new_text:
            changes.append({"type": "not found in this check", "before": before, "after": None})
    return {"changes": changes, "coverage_changed": any(prior[key] != candidate[key] for key in ("incomplete", "missing_scopes"))}


def list_questions(root: Path) -> list[dict]:
    with project_records._db(root) as db:
        if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='living_questions'").fetchone():
            return []
        return [json.loads(row[0]) for row in db.execute("SELECT data FROM living_questions ORDER BY rowid DESC")]


def follow(root: Path, brain: dict, question: str, requested: list[str] | None, challenge: str) -> dict:
    question, challenge = redact(question.strip()), redact(challenge.strip())
    if not ask._tokens(question):
        raise ValueError("Enter a question with searchable words")
    scope = scope_for(brain, requested)
    row = {"id": uuid4().hex, "revision": 1, "question": question, "challenge": challenge, "scope": scope,
           "state": "following", "snoozed_until": None, "checked_at": now(), "pending": None}
    row["reviewed"] = snapshot(root, brain, row)
    with project_records._db(root, True) as db:
        previous = [json.loads(item[0]) for item in db.execute("SELECT data FROM living_questions")]
        existing = next((item for item in previous if item["state"] != "unfollowed"
                         and item["question"].casefold() == question.casefold()
                         and {p["rel"] for p in item["scope"]} == {p["rel"] for p in scope}), None)
        if existing:
            return existing
        if len(previous) >= 50:
            raise ValueError("The local question history has reached its 50-question limit")
        db.execute("INSERT INTO living_questions VALUES (?,?,?)", (row["id"], 1, json.dumps(row, ensure_ascii=False)))
    return row


def change(root: Path, brain: dict, identifier: str, action: str, revision: int) -> dict:
    with project_records._db(root, True) as db:
        memory = db.execute("SELECT data FROM living_questions WHERE id=?", (identifier,)).fetchone()
        if not memory:
            raise KeyError(identifier)
        row = json.loads(memory[0])
        if revision != row["revision"] or row["state"] == "unfollowed":
            raise ValueError("The question changed; reload it before acting")
        if action == "check":
            candidate = snapshot(root, brain, row)
            delta = compare(row["reviewed"], candidate)
            row.update(checked_at=now(), pending={"candidate": candidate, **delta}
                       if delta["changes"] or delta["coverage_changed"] else None)
        elif action == "accept":
            if not row["pending"]:
                raise ValueError("There isn’t a pending evidence comparison to accept")
            if snapshot(root, brain, row) != row["pending"]["candidate"]:
                raise ValueError("The evidence changed after this comparison; check again before accepting")
            row.update(reviewed=row["pending"]["candidate"], pending=None)
        elif action == "snooze":
            row.update(snoozed_until=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds"))
        elif action == "resume":
            row.update(snoozed_until=None)
        elif action == "unfollow":
            row.update(state="unfollowed")
        else:
            raise ValueError("Unsupported action")
        row["revision"] += 1
        db.execute("UPDATE living_questions SET revision=?, data=? WHERE id=? AND revision=?",
                   (row["revision"], json.dumps(row, ensure_ascii=False), identifier, revision))
    return row
