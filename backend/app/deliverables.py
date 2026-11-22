"""Local Markdown exports with immutable artifacts and reviewable source history."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from uuid import uuid4

from backend.app import clips, knowledge
from backend.app.redact import redact
from backend.app.scanner import _resolve_under_root

_LOCK = Lock()
_ID = re.compile(r"[0-9a-f]{32}")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _seal(data: object) -> str:
    return _sha(json.dumps(data, sort_keys=True, ensure_ascii=False).encode())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _home(root: Path, project: dict) -> Path:
    directory = root.resolve() / ".brain" / "deliverables" / _sha(project["rel"].encode())[:24]
    if directory.resolve() != directory:
        raise ValueError("Deliverable storage cannot use a linked directory")
    return directory


def _text(title: str, content: str) -> tuple[str, str]:
    title = redact(" ".join(title.split()))
    content = redact(content.strip())
    if not title or not content:
        raise ValueError("A title and Markdown content are required")
    return title, f"# {title}\n\n{content}\n"


def _approved(root: Path, brain: dict, project: dict) -> dict[str, dict]:
    return {page["page_id"]: page for page in knowledge.pages(root, brain) if page["project_id"] == project["id"]}


def preview(root: Path, brain: dict, project: dict, title: str, content: str, page_ids: list[str]) -> dict:
    title, markdown = _text(title, content)
    current = _approved(root, brain, project)
    pages = []
    for page_id in dict.fromkeys(page_ids):
        page = current.get(page_id)
        if not page or not page["content"] or not page["sources"] or page["stale_sources"]:
            raise ValueError("Every selected page must be approved, readable, and up to date")
        pages.append({"id": page_id, "title": page["title"], "revision": page["revision"],
                      "sha256": page["content_sha256"], "sources": page["sources"]})
    if not pages:
        raise ValueError("Choose at least one approved knowledge page")
    details = {"title": title, "artifact_sha256": _sha(markdown.encode()), "pages": pages}
    return {**details, "markdown": markdown, "token": _seal(details)}


def export(root: Path, brain: dict, project: dict, title: str, content: str, page_ids: list[str], token: str) -> dict:
    with _LOCK:
        reviewed = preview(root, brain, project, title, content, page_ids)
        if reviewed["token"] != token:
            raise ValueError("The export or its evidence changed; preview it again")
        home = _home(root, project)
        home.mkdir(parents=True, exist_ok=True)
        if sum(1 for path in home.iterdir() if _ID.fullmatch(path.name)) >= 250:
            raise ValueError("This project has reached its limit of 250 tracked deliverables")
        identifier = uuid4().hex
        folder = home / identifier
        draft = home / f".pending-{identifier}"
        draft.mkdir()
        record = {key: reviewed[key] for key in ("title", "artifact_sha256", "pages")}
        record.update(id=identifier, created_at=_now(), reviews=[])
        try:
            (draft / "deliverable.md").write_bytes(reviewed["markdown"].encode())
            (draft / "provenance.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            draft.rename(folder)
        finally:
            if draft.is_dir():
                for name in ("deliverable.md", "provenance.json"):
                    (draft / name).unlink(missing_ok=True)
                draft.rmdir()
    return {**record, "artifact_path": str(folder / "deliverable.md")}


def _read(folder: Path) -> dict | None:
    path = folder / "provenance.json"
    if folder.is_symlink() or path.is_symlink():
        return None
    try:
        if path.stat().st_size > 1_000_000:
            return None
        row = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    required = {"id", "title", "pages", "artifact_sha256", "created_at", "reviews"}
    if not isinstance(row, dict) or not required <= row.keys() or row["id"] != folder.name:
        return None
    return row


def _source_now(root: Path, project: dict, records: dict[str, dict], source: dict) -> tuple[str, str | None]:
    if source.get("kind") == "clip":
        clip = clips.approved_clip(root, project, source["id"])
        return ("available", clips.fingerprint(clip)) if clip else ("removed or unreadable clip", None)
    rec = records.get(source["id"])
    if rec:
        fingerprint = knowledge._fingerprint(root, rec)
        return ("available", fingerprint) if fingerprint else ("missing or unreadable", None)
    path = _resolve_under_root(root, {"project_rel": project["rel"], "rel": source["rel"]})
    if path is None:
        return "excluded or unavailable", None
    try:
        path.lstat()
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "unreadable", None
    return "not indexed", None


def _status(root: Path, project: dict, folder: Path, row: dict, pages: dict, files: dict) -> dict:
    path = folder / "deliverable.md"
    try:
        artifact = _sha(path.read_bytes()) if not path.is_symlink() and path.stat().st_size <= 500_000 else None
    except OSError:
        artifact = None
    changes = []
    if artifact != row["artifact_sha256"]:
        changes.append({"kind": "export", "label": path.name, "status": "changed" if artifact else "missing or unreadable",
                        "current": artifact})
    for original in row["pages"]:
        page = pages.get(original["id"])
        current = [page["revision"], page["content_sha256"]] if page and page["content"] else None
        if current != [original["revision"], original["sha256"]]:
            changes.append({"kind": "page", "label": original["title"], "status": "changed" if current else "missing or unreadable",
                            "current": current})
        for source in original["sources"]:
            availability, digest = _source_now(root, project, files, source)
            if digest != source["sha256"]:
                changes.append({"kind": "source", "label": source["rel"], "status": "changed" if digest else availability,
                                "current": digest, "source_id": source["id"]})
    snapshot = _seal(changes)
    checked = row["reviews"][-1] if row["reviews"] else None
    status = "current" if not changes else "reviewed" if checked and checked["snapshot"] == snapshot else "needs review"
    return {**row, "artifact_path": str(path), "changes": changes, "snapshot": snapshot, "status": status}


def list_exports(root: Path, brain: dict, project: dict) -> list[dict]:
    home = _home(root, project)
    if not home.is_dir():
        return []
    pages = _approved(root, brain, project)
    files = {record["id"]: record for record in brain["files"] if record["project_id"] == project["id"]}
    result = [_status(root, project, folder, row, pages, files)
              for folder in sorted(home.iterdir()) if _ID.fullmatch(folder.name) and (row := _read(folder))]
    return sorted(result, key=lambda row: row["created_at"], reverse=True)


def acknowledge(root: Path, brain: dict, project: dict, identifier: str, snapshot: str) -> dict:
    if not _ID.fullmatch(identifier):
        raise KeyError(identifier)
    folder = _home(root, project) / identifier
    with _LOCK:
        row = _read(folder)
        if row is None:
            raise KeyError(identifier)
        pages = _approved(root, brain, project)
        files = {record["id"]: record for record in brain["files"] if record["project_id"] == project["id"]}
        result = _status(root, project, folder, row, pages, files)
        if snapshot != result["snapshot"] or result["status"] != "needs review":
            raise ValueError("Review the current changes before acknowledging them")
        if len(row["reviews"]) >= 100:
            raise ValueError("This deliverable has reached its review-history limit")
        row["reviews"].append({"at": _now(), "snapshot": snapshot, "changes": result["changes"]})
        with NamedTemporaryFile("w", encoding="utf-8", dir=folder, delete=False) as handle:
            temp = Path(handle.name)
            try:
                json.dump(row, handle, ensure_ascii=False, indent=2)
                handle.close()
                temp.replace(folder / "provenance.json")
            finally:
                temp.unlink(missing_ok=True)
        return {**result, "status": "reviewed"}
