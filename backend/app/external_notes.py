"""Read-only, opted-in local Obsidian and OneNote text export search."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from backend.app.privacy import active as private_folders_active
from backend.app.redact import redact
from backend.app.scanner import _blocked_file, _is_reparse, ignored_dir_name

MAX_NOTES = 200
MAX_READ = 24_000


def collect(projects: list[dict]) -> tuple[list[dict], list[str]]:
    raw = os.getenv("BRAIN_NOTES_ROOTS")
    if private_folders_active() or raw is None:
        return [], []
    try:
        configured = json.loads(raw)
    except ValueError:
        return [], ["External note sources are disabled: invalid BRAIN_NOTES_ROOTS JSON"]
    if not isinstance(configured, dict):
        return [], ["External note sources are disabled: BRAIN_NOTES_ROOTS must map projects to folders"]
    rows, warnings = [], []
    for project in projects:
        entries = configured.get(project["rel"], [])
        if not isinstance(entries, list) or len(entries) > 8:
            warnings.append(f"{project['name']}: expected up to eight configured note folders")
            continue
        for index, entry in enumerate(entries, 1):
            if not isinstance(entry, dict) or entry.get("kind") not in {"obsidian", "onenote-export"} or not isinstance(entry.get("path"), str):
                warnings.append(f"{project['name']}: note folder {index} has invalid settings")
                continue
            root = Path(entry["path"]).expanduser()
            label = redact(str(entry.get("label") or f"local notes {index}"))[:100]
            if not root.is_absolute() or root.drive.startswith("\\\\") or _is_reparse(root) or not root.is_dir():
                warnings.append(f"{project['name']}/{label}: note folder is unavailable or not a local directory")
                continue
            seen = 0
            skipped = 0
            partial = 0
            failures = []
            hit_limit = False
            for directories, (parent, subdirs, names) in enumerate(os.walk(root, followlinks=False, onerror=failures.append), 1):
                subdirs[:] = sorted(name for name in subdirs if not name.startswith(".") and not ignored_dir_name(name) and not _is_reparse(Path(parent) / name))
                if directories > 200 or seen >= 500 or len(rows) >= MAX_NOTES:
                    hit_limit = True
                    break
                for name in sorted(names):
                    if seen >= 500 or len(rows) >= MAX_NOTES:
                        hit_limit = True
                        break
                    seen += 1
                    path = Path(parent) / name
                    if name.startswith("."):
                        continue
                    if path.suffix.casefold() not in {".md", ".markdown", ".txt"} or _blocked_file(path):
                        skipped += 1
                        continue
                    try:
                        with path.open("rb") as handle:
                            data = handle.read(MAX_READ + 1)
                        if b"\x00" in data[:1024]:
                            raise ValueError
                        text = redact(data[:MAX_READ].decode("utf-8-sig", errors="replace"))
                    except (OSError, ValueError):
                        skipped += 1
                        continue
                    if len(data) > MAX_READ:
                        partial += 1
                    rel = redact(path.relative_to(root).as_posix())
                    identifier = hashlib.sha256(f"{project['id']}:{index}:{rel}".encode()).hexdigest()[:24]
                    rows.append({"id": f"external-note:{identifier}", "project_id": project["id"],
                                 "label": f"{project['name']}/{label}/{rel}", "text": text, "kind": entry["kind"]})
            if hit_limit or skipped or partial or failures:
                warnings.append(f"{project['name']}/{label}: {skipped} skipped, {partial} partially read, {len(failures)} unreadable folders"
                                + ("; scan limit reached" if hit_limit else ""))
            if len(rows) >= MAX_NOTES:
                return rows, warnings[:30] + ["External note search reached its combined 200-note limit"]
    return rows, warnings[:30]
