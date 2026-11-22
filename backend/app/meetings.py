"""Local meeting-note review. Only approved items are written to disk."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from backend.app.redact import redact

_LOCK = Lock()
_TAG = re.compile(r"^(?:\*\*)?(decision|action(?: item)?|todo)(?:\*\*)?\s*[:–—-]\s*(?:\*\*)?(.*)$", re.I)
_BULLET = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+)(?:\[[ xX]\]\s*)?")
_FIELD = re.compile(r"(?:^|[|;])\s*(owner|due(?: date)?)\s*:\s*([^|;]+)", re.I)
_SECTIONS = {"decisions": "decision", "actions": "action", "action items": "action", "todos": "action"}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean(text: str, limit: int) -> str:
    return redact(" ".join(text.split()))[:limit]


def draft(text: str) -> dict:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    section = None
    items = []
    fenced = False
    for line, raw in enumerate(normalized.splitlines(), 1):
        stripped = raw.strip()
        if stripped.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = re.fullmatch(r"(?:#{1,6}\s+)?(?:\*\*)?(decisions|actions|action items|todos)(?:\*\*)?:?", stripped, re.I)
        if heading:
            section = _SECTIONS[heading[1].casefold()]
            continue
        if stripped.startswith("#"):
            section = None
        bullet = _BULLET.match(stripped)
        body = stripped[bullet.end():] if bullet else stripped
        tag = _TAG.match(body)
        if tag:
            kind = "decision" if tag[1].casefold() == "decision" else "action"
            body = tag[2]
        elif section and bullet:
            kind = section
        else:
            continue
        fields = {match[1].casefold().split()[0]: _clean(match[2], 120) for match in _FIELD.finditer(body)}
        title = _clean(_FIELD.sub("", body), 500)
        if title:
            items.append({"line": line, "kind": kind, "text": title, "excerpt": _clean(stripped, 700),
                          "owner": fields.get("owner") or None, "due": fields.get("due") or None})
        if len(items) >= 50:
            break
    return {"source_id": _digest(normalized), "items": items}


def _folder(root: Path, project: dict) -> Path:
    root = root.resolve()
    folder = root / ".brain" / "meetings" / _digest(project["rel"])[:24]
    if folder.resolve() != folder:
        raise ValueError("Meeting storage cannot use a linked directory")
    return folder


def _read(path: Path) -> list[dict]:
    if path.is_symlink():
        return []
    try:
        if path.stat().st_size > 250_000:
            return []
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def approve(root: Path, project: dict, notes: str, source_name: str, source_id: str, edits: list[dict]) -> dict:
    preview = draft(notes)
    if preview["source_id"] != source_id:
        raise ValueError("Meeting notes changed; review them again")
    candidates = {item["line"]: item for item in preview["items"]}
    if any(edit["line"] not in candidates or not _clean(edit["text"], 500) for edit in edits):
        raise ValueError("Each approved item must match a previewed source line and have text")
    folder = _folder(root, project)
    path = folder / f"{source_id}.json"
    with _LOCK:
        if path.is_symlink():
            raise ValueError("Meeting storage is not available")
        items = _read(path)
        saved = {item["line"] for item in items}
        added = 0
        for edit in edits:
            if edit["line"] in saved:
                continue
            item = candidates[edit["line"]]
            items.append({**item, "text": _clean(edit["text"], 500),
                          "owner": _clean(edit.get("owner") or "", 120) or None,
                          "due": _clean(edit.get("due") or "", 120) or None,
                          "source_id": source_id, "source_name": _clean(source_name, 120) or "Pasted meeting notes",
                          "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            saved.add(edit["line"])
            added += 1
        if added:
            folder.mkdir(parents=True, exist_ok=True)
            # Exclusive temporary file plus replace keeps partial batches out of the task list.
            from tempfile import NamedTemporaryFile

            with NamedTemporaryFile("w", encoding="utf-8", dir=folder, delete=False) as handle:
                temporary = Path(handle.name)
                try:
                    json.dump(items, handle, ensure_ascii=False)
                    handle.close()
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
    return {"added": added, "already_saved": len(edits) - added, "items": items}


def list_items(root: Path, project: dict) -> list[dict]:
    folder = _folder(root, project)
    result = []
    for path in sorted(folder.glob("*.json"), reverse=True)[:300]:
        result.extend(_read(path))
    return sorted(result, key=lambda item: item.get("approved_at", ""), reverse=True)[:300]
