"""Import reviewed, normalized local session exports into the dashboard timeline."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from backend.app.privacy import active as private_folders_active
from backend.app.redact import redact
from backend.app.scanner import _blocked_file


def load(brain: dict) -> tuple[list[dict], str | None]:
    raw = os.getenv("BRAIN_AGENT_HISTORY_FILE")
    if private_folders_active() or not raw:
        return [], None
    path = Path(raw).expanduser()
    try:
        if not path.is_absolute() or path.drive.startswith("\\\\") or path.suffix.casefold() != ".json" or _blocked_file(path):
            raise ValueError
        with path.open("rb") as file:
            blob = file.read(750_001)
        if len(blob) > 750_000:
            raise ValueError
        data = json.loads(blob)
        if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
            raise ValueError
    except (OSError, ValueError, UnicodeError):
        return [], "The opted-in agent session export is unavailable, oversized, or invalid"
    projects = {p["id"]: p for p in brain["projects"]}
    indexed = {(r["project_id"], r["rel"]): r for r in brain["files"] if not r.get("env_class")}
    sessions, ids = [], set()
    skipped = 0
    def clean(value: object, limit: int) -> str:
        return redact(value.strip())[:limit] if isinstance(value, str) else ""
    for row in data["sessions"][:250]:
        if not isinstance(row, dict):
            skipped += 1
            continue
        provider, local_id, project_id = (clean(row.get(key), 120) for key in ("agent", "id", "project"))
        project = projects.get(project_id)
        title = clean(row.get("title"), 180)
        if not project or not re.fullmatch(r"[\w .-]{2,45}", provider) or not local_id or not title:
            skipped += 1
            continue
        try:
            when = datetime.fromisoformat(clean(row.get("when"), 80))
            if when.utcoffset() is None:
                raise ValueError
        except ValueError:
            skipped += 1
            continue
        file_refs = row.get("files") if isinstance(row.get("files"), list) else []
        files = []
        for ref in file_refs[:12]:
            if isinstance(ref, str) and (rec := indexed.get((project_id, ref.replace("\\", "/")))):
                files.append({"file_id": rec["id"], "rel": rec["rel"], "name": rec["name"]})
        identifier = hashlib.sha256(f"{project_id}:{provider}:{local_id}".encode()).hexdigest()[:24]
        if identifier in ids:
            continue
        ids.add(identifier)
        session = {"id": f"agent-export:{identifier}", "project_id": project_id, "project_name": project["name"],
                         "title": title, "when": when.isoformat(), "agent": provider, "prompt": "", "files": files,
                         "summary": clean(row.get("summary"), 1000), "summary_source": "heuristic"}
        workflow = row.get("workflow")
        if isinstance(workflow, dict) and (name := clean(workflow.get("name"), 140)):
            outcome = workflow.get("outcome")
            steps = workflow.get("steps")
            session["workflow"] = {"name": name, "outcome": outcome if outcome in ("success", "failure") else "unknown",
                                   "evidence": clean(workflow.get("evidence"), 400),
                                   "steps": [step for value in (steps[:12] if isinstance(steps, list) else [])
                                             if (step := clean(value, 400))]}
        sessions.append(session)
    unseen = max(0, len(data["sessions"]) - 250)
    warning = f"Agent export: {skipped} invalid or unmatched session(s), {unseen} beyond the import limit" if skipped or unseen else None
    return sessions, warning
