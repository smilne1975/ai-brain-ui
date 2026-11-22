"""Local, review-gated importing of Obsidian Web Clipper Markdown."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from urllib.parse import urlsplit

from backend.app.redact import redact

_LOCK = Lock()
_META = re.compile(r"\A(?:\ufeff)?---\n(.*?)\n---(?:\n|\Z)(.*)\Z", re.S)


def _valid_url(url: object) -> bool:
    if not isinstance(url, str) or len(url) > 2048 or any(char.isspace() or ord(char) < 32 for char in url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in {"http", "https"} and bool(parts.hostname) and parts.username is None and parts.password is None


def preview(markdown: str, filename: str) -> dict:
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    match = _META.match(normalized)
    if not match:
        raise ValueError("Import Markdown with Web Clipper metadata and an original URL")
    frontmatter, body = match.groups()
    props: dict[str, str] = {}
    for line in frontmatter.splitlines():
        field = re.fullmatch(r"(title|source|url|created|captured|date):\s*(.*?)\s*", line, re.I)
        if not field:
            continue
        key, value = field.groups()
        key = key.casefold()
        if key in props:
            raise ValueError(f"Clip metadata repeats {key}")
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"Could not read the clip's {key} field") from None
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        props[key] = value.strip()
    url = props.get("source") or props.get("url") or ""
    if props.get("source") and props.get("url") and props["source"] != props["url"]:
        raise ValueError("Clip has two different original URLs")
    if not _valid_url(url):
        raise ValueError("The clip needs an original HTTP or HTTPS URL without embedded credentials")
    filename = re.split(r"[/\\]", filename)[-1]
    text = redact(body.strip())
    if not text:
        raise ValueError("There is no captured text in this clip")
    return {"id": hashlib.sha256(normalized.encode()).hexdigest(), "filename": redact(filename)[:160],
            "title": redact(props.get("title") or filename or "Untitled clip")[:180], "url": url,
            "captured_at": redact(props.get("created") or props.get("captured") or props.get("date") or "")[:120] or None,
            "content": text}


def _folder(root: Path, project: dict) -> Path:
    scope = hashlib.sha256(project["rel"].encode()).hexdigest()[:24]
    folder = root.resolve() / ".brain" / "web-clips" / scope
    if folder.resolve() != folder:
        raise ValueError("Web clip storage cannot use a linked directory")
    return folder


def _read(path: Path) -> dict | None:
    if path.is_symlink():
        return None
    try:
        if path.stat().st_size > 600_000:
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    required = {"id", "title", "url", "content", "active", "filename", "imported_at", "captured_at"}
    if not isinstance(raw, dict) or not required <= raw.keys() or raw["id"] != path.stem or not _valid_url(raw["url"]):
        return None
    if not isinstance(raw["active"], bool) or any(not isinstance(raw[key], str) for key in ("content", "title", "filename", "imported_at")):
        return None
    return raw


def _write(path: Path, record: dict) -> None:
    if path.is_symlink():
        raise ValueError("Web clip storage cannot use a linked file")
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        try:
            json.dump(record, handle, ensure_ascii=False)
            handle.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def import_clip(root: Path, project: dict, markdown: str, filename: str, expected_id: str) -> tuple[dict, bool]:
    record = preview(markdown, filename)
    if record["id"] != expected_id:
        raise ValueError("Clip changed since the preview")
    return store_preview(root, project, record)


def store_preview(root: Path, project: dict, record: dict) -> tuple[dict, bool]:
    record = dict(record)
    path = _folder(root, project) / f"{record['id']}.json"
    with _LOCK:
        if previous := _read(path):
            return previous, False
        if sum(1 for _ in path.parent.glob("*.json")) >= 200:
            raise ValueError("The project web-clip inbox has reached its 200-item limit")
        record.update(active=True, imported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        _write(path, record)
    return record, True


def set_active(root: Path, project: dict, clip_id: str, active: bool) -> dict:
    if re.fullmatch(r"[0-9a-f]{64}", clip_id) is None:
        raise ValueError("Invalid clip reference")
    path = _folder(root, project) / f"{clip_id}.json"
    with _LOCK:
        record = _read(path)
        if record is None:
            raise KeyError(clip_id)
        record["active"] = active
        _write(path, record)
    return record


def list_clips(root: Path, project: dict) -> list[dict]:
    rows = (record for path in sorted(_folder(root, project).glob("*.json"))[:200] if (record := _read(path)))
    return sorted(rows, key=lambda record: record["imported_at"], reverse=True)


def reference(project_id: str, clip_id: str) -> str:
    return f"clip:{project_id}:{clip_id}"


def approved_clip(root: Path, project: dict, reference_id: str) -> dict | None:
    if not reference_id.startswith(f"clip:{project['id']}:"):
        return None
    clip_id = reference_id.rsplit(":", 1)[-1]
    if reference_id != reference(project["id"], clip_id) or not re.fullmatch(r"[0-9a-f]{64}", clip_id):
        return None
    try:
        record = _read(_folder(root, project) / f"{clip_id}.json")
    except (OSError, ValueError):
        return None
    return record if record and record["active"] else None


def fingerprint(record: dict) -> str:
    fields = [record[key] for key in ("id", "title", "url", "captured_at", "content")]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()
