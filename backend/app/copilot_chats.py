"""Read GitHub Copilot chat logs and attach them to scanned projects.

The logs stay on disk. This module never writes them, and it never opens a
project's .env file. Chat text is redacted before it is stored in the response.
A model sees that text only when a provider is configured and BRAIN_COPILOT_LLM
is turned on. Otherwise the summary is a short local heuristic.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from backend.app.activity import _MONTHS, _WEEKDAYS, _cutoff, _project_dir
from backend.app.llm import complete, resolve_provider
from backend.app.redact import redact

log = logging.getLogger("brain.chats")

REPO = Path(__file__).resolve().parents[2]
SAMPLE_USER = REPO / "fixtures" / "copilot-user" / "User"

MAX_WORKSPACES = 60
MAX_SESSIONS_PER_STORE = 20
MAX_SESSIONS = 200
MAX_FILE_BYTES = 1_500_000
MAX_PROMPTS = 8
MAX_TEXT = 280
_OFF = {"0", "false", "no", "off"}
_ON = {"1", "true", "yes", "on"}

_PATH_RE = re.compile(
    r"(?<![\w.-])((?:[A-Za-z]:[\\/])?(?:[\w.-]+[\\/])*[\w.-]+\.(?:py|md|ts|tsx|js|jsx|json|sh|ps1|bat|yml|yaml|txt|css|html|toml))\b",
    re.IGNORECASE,
)
_TICK_RE = re.compile(r"`([^`\n]{1,180})`")
_TRANSCRIPT_TYPES = {
    "session.start",
    "user.message",
    "assistant.message",
    "assistant.turn_start",
    "assistant.turn_end",
    "tool.execution_start",
    "tool.execution_complete",
}
_PATH_KEYS = {"external", "fspath", "uri", "resource", "file", "path", "fsPath", "cwd"}
_DB_KEYS = (
    "interactive.sessions",
    "memento/interactive-session",
    "chat.ChatSessionStore.index",
    "memento/chat",
)


def load_chats(root: Path, brain: dict) -> dict:
    """Return local Copilot sessions matched to projects in ``brain``."""
    if not _enabled():
        return {
            "enabled": False,
            "source": "disabled",
            "roots": [],
            "sessions": [],
            "by_project": {},
            "truncated": False,
            "llm": False,
        }
    root = Path(root).expanduser().resolve()
    projects = _projects(root, brain)
    roots = _user_roots(root)
    sessions: list[dict] = []
    truncated = False
    for user_root in roots:
        found, hit_cap = _scan_user_root(user_root, projects)
        sessions.extend(found)
        truncated = truncated or hit_cap
        if len(sessions) >= MAX_SESSIONS:
            sessions = sessions[:MAX_SESSIONS]
            truncated = True
            break
    sessions = _dedupe(sessions)
    sessions.sort(key=lambda item: item.get("when") or "", reverse=True)
    if len(sessions) > MAX_SESSIONS:
        sessions = sessions[:MAX_SESSIONS]
        truncated = True
    used_model = _maybe_narrate(sessions)
    by_project: dict[str, list[str]] = {}
    for session in sessions:
        project_id = session.get("project_id")
        if project_id:
            by_project.setdefault(project_id, []).append(session["id"])
    return {
        "enabled": True,
        "source": "override" if os.environ.get("BRAIN_COPILOT_CHATS_ROOT", "").strip() else "local",
        "roots": [str(path) for path in roots],
        "sessions": sessions,
        "by_project": by_project,
        "truncated": truncated,
        "llm": used_model,
    }


def merge_chats(timeline: dict, index: dict) -> dict:
    """Add chat events onto a timeline payload. File summaries are left alone."""
    for week in timeline.get("weeks") or []:
        for day in week.get("days") or []:
            for proj in day.get("projects") or []:
                proj.setdefault("chats", [])
    if not index.get("enabled"):
        return timeline
    now = _parse_when(timeline.get("generated_at")) or datetime.now().astimezone()
    window = int(timeline.get("window_days") or 7)
    cutoff = _cutoff(window, now)
    horizon = now + timedelta(minutes=5)
    day_index: dict[str, dict] = {}
    slot_index: dict[tuple[str, str], dict] = {}
    for week in timeline.get("weeks") or []:
        for day in week.get("days") or []:
            day_index[day["date"]] = day
            for proj in day.get("projects") or []:
                slot_index[(day["date"], proj["project_id"])] = proj
    pending: dict[str, dict] = {}
    for session in index.get("sessions") or []:
        project_id = session.get("project_id")
        if not project_id:
            continue
        when = _parse_when(session.get("when"))
        if when is None or when < cutoff or when > horizon:
            continue
        date = when.astimezone(now.tzinfo).date().isoformat()
        event = {
            "id": session["id"],
            "title": session.get("title") or "Copilot chat",
            "when": session.get("when"),
            "prompt": session.get("prompt") or "",
            "summary": session.get("summary") or "",
            "files": session.get("files") or [],
        }
        slot = slot_index.get((date, project_id))
        if slot is None:
            day = day_index.get(date)
            if day is None:
                date_obj = datetime.fromisoformat(date).date()
                day = {
                    "date": date,
                    "label": f"{_WEEKDAYS[date_obj.weekday()]} {_MONTHS[date_obj.month - 1]} {date_obj.day}",
                    "projects": [],
                }
                day_index[date] = day
                pending[date] = day
            slot = {
                "project_id": project_id,
                "name": session.get("project_name") or project_id,
                "summary": session.get("summary") or "Copilot chat.",
                "summary_source": session.get("summary_source") or "heuristic",
                "files": [],
                "commits": [],
                "more": 0,
                "chats": [],
            }
            day["projects"].append(slot)
            slot_index[(date, project_id)] = slot
        slot.setdefault("chats", []).append(event)
    for date, day in pending.items():
        date_obj = datetime.fromisoformat(date).date()
        monday = date_obj - timedelta(days=date_obj.weekday())
        sunday = monday + timedelta(days=6)
        key = f"{monday.isocalendar().year}-W{monday.isocalendar().week:02d}"
        week = next((item for item in timeline["weeks"] if item.get("id") == key), None)
        if week is None:
            week = {
                "id": key,
                "label": f"Week of {_MONTHS[monday.month - 1]} {monday.day}",
                "start": monday.isoformat(),
                "end": sunday.isoformat(),
                "file_count": 0,
                "project_count": 0,
                "days": [],
            }
            timeline.setdefault("weeks", []).append(week)
        week["days"].append(day)
    seen: set[str] = set()
    for week in timeline.get("weeks") or []:
        week["days"].sort(key=lambda item: item.get("date") or "", reverse=True)
        ids: set[str] = set()
        for day in week["days"]:
            for proj in day["projects"]:
                ids.add(proj["project_id"])
                seen.add(proj["project_id"])
                chats = proj.get("chats") or []
                chats.sort(key=lambda item: item.get("when") or "", reverse=True)
                proj["chats"] = chats
        week["project_count"] = len(ids)
    timeline["weeks"] = sorted(timeline.get("weeks") or [], key=lambda item: item.get("start") or "", reverse=True)
    timeline["project_count"] = len(seen)
    return timeline


def _enabled() -> bool:
    raw = os.environ.get("BRAIN_COPILOT_CHATS", "1").strip().lower()
    return raw not in _OFF


def _include_samples(scan_root: Path) -> bool:
    flag = os.environ.get("BRAIN_COPILOT_INCLUDE_SAMPLES", "").strip().lower()
    if flag in _OFF:
        return False
    if flag in _ON:
        return True
    return scan_root.name == "demo-projects"


def _user_roots(scan_root: Path) -> list[Path]:
    override = os.environ.get("BRAIN_COPILOT_CHATS_ROOT", "").strip()
    if override:
        return _expand_user_root(Path(override).expanduser())
    found: list[Path] = []
    for base in _platform_user_dirs():
        found.extend(_expand_user_root(base))
    if _include_samples(scan_root):
        found.extend(_expand_user_root(SAMPLE_USER))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in found:
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _expand_user_root(user: Path) -> list[Path]:
    try:
        if not user.exists():
            return []
    except OSError:
        return []
    found = [user]
    profiles = user / "profiles"
    try:
        children = sorted(profiles.iterdir()) if profiles.is_dir() else []
    except OSError:
        children = []
    for child in children:
        try:
            if child.is_dir():
                found.append(child)
        except OSError:
            continue
    return found


def _platform_user_dirs() -> list[Path]:
    home = Path.home()
    names = ("Code", "Code - Insiders", "VSCodium")
    system = platform.system()
    roots: list[Path] = []
    if system == "Windows":
        appdata = os.environ.get("APPDATA", "").strip()
        bases = [Path(appdata)] if appdata else [home / "AppData" / "Roaming"]
        for base in bases:
            for name in names:
                roots.append(base / name / "User")
    elif system == "Darwin":
        support = home / "Library" / "Application Support"
        for name in names:
            roots.append(support / name / "User")
    else:
        for name in names:
            roots.append(home / ".config" / name / "User")
        roots.append(home / ".vscode-server" / "data" / "User")
        roots.append(home / ".vscode-server-insiders" / "data" / "User")
    return roots


def _projects(root: Path, brain: dict) -> list[dict]:
    files_by: dict[str, list[dict]] = {}
    for rec in brain.get("files") or []:
        files_by.setdefault(rec.get("project_id") or "", []).append(rec)
    projects = []
    for project in brain.get("projects") or []:
        directory = _project_dir(root, project)
        projects.append(
            {
                "id": project["id"],
                "name": project.get("name") or project["id"],
                "rel": project.get("rel") or ".",
                "directory": directory,
                "files": files_by.get(project["id"], []),
            }
        )
    return projects


def _scan_user_root(user_root: Path, projects: list[dict]) -> tuple[list[dict], bool]:
    sessions: list[dict] = []
    truncated = False
    storage = user_root / "workspaceStorage"
    workspaces: list[Path] = []
    try:
        if storage.is_dir():
            workspaces = [path for path in storage.iterdir() if path.is_dir()]
    except OSError:
        log.debug("skip unreadable workspaceStorage %s", storage, exc_info=True)
        workspaces = []
    workspaces.sort(key=_mtime, reverse=True)
    if len(workspaces) > MAX_WORKSPACES:
        workspaces = workspaces[:MAX_WORKSPACES]
        truncated = True
    for folder in workspaces:
        batch, hit = _scan_workspace(folder, projects)
        sessions.extend(batch)
        truncated = truncated or hit
    for relative, source in (
        (Path("globalStorage") / "emptyWindowChatSessions", "globalStorage"),
        (Path("globalStorage") / "transferredChatSessions", "globalStorage"),
        (Path("workspaceStorage") / "no-workspace" / "chatSessions", "chatSessions"),
    ):
        batch, hit = _scan_session_dir(user_root / relative, None, source, "", projects)
        sessions.extend(batch)
        truncated = truncated or hit
    for db_path in (
        user_root / "globalStorage" / "github.copilot-chat" / "session-store.db",
        user_root / "globalStorage" / "GitHub.copilot-chat" / "session-store.db",
    ):
        if db_path.is_file():
            batch = _sessions_from_loose_db(db_path, None, "", projects)
            sessions.extend(batch)
    return sessions, truncated


def _scan_workspace(folder: Path, projects: list[dict]) -> tuple[list[dict], bool]:
    workspace_path = _workspace_label(folder)
    project_id = _match_workspace(folder, projects)
    sessions: list[dict] = []
    truncated = False
    for sub, source in (
        (folder / "chatSessions", "chatSessions"),
        (folder / "GitHub.copilot-chat" / "transcripts", "transcript"),
        (folder / "github.copilot-chat" / "transcripts", "transcript"),
    ):
        batch, hit = _scan_session_dir(sub, project_id, source, workspace_path, projects)
        sessions.extend(batch)
        truncated = truncated or hit
    editing = folder / "chatEditingSessions"
    try:
        edit_dirs = [path for path in editing.iterdir() if path.is_dir()] if editing.is_dir() else []
    except OSError:
        edit_dirs = []
    edit_dirs.sort(key=_mtime, reverse=True)
    kept = 0
    for edit_dir in edit_dirs:
        if kept >= MAX_SESSIONS_PER_STORE:
            truncated = True
            break
        state = edit_dir / "state.json"
        parsed = _editing_session(state, project_id, workspace_path, projects)
        if parsed:
            sessions.append(parsed)
            kept += 1
    db_sessions = _sessions_from_vscdb(folder / "state.vscdb", project_id, workspace_path, projects)
    sessions.extend(db_sessions[:MAX_SESSIONS_PER_STORE])
    if len(db_sessions) > MAX_SESSIONS_PER_STORE:
        truncated = True
    return sessions, truncated


def _scan_session_dir(
    directory: Path,
    project_id: str | None,
    source: str,
    workspace_path: str,
    projects: list[dict],
) -> tuple[list[dict], bool]:
    try:
        if not directory.is_dir():
            return [], False
        files = [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in {".json", ".jsonl"}]
    except OSError:
        log.debug("skip unreadable chat dir %s", directory, exc_info=True)
        return [], False
    files.sort(key=_mtime, reverse=True)
    truncated = len(files) > MAX_SESSIONS_PER_STORE
    sessions: list[dict] = []
    for path in files[:MAX_SESSIONS_PER_STORE]:
        text = _read_text(path)
        if text is None:
            continue
        try:
            parsed = _parse_chat_file(text, path.name)
        except Exception:
            log.debug("skip unreadable chat file %s", path, exc_info=True)
            continue
        for raw in parsed[:MAX_SESSIONS_PER_STORE]:
            session = _session_from_raw(raw, project_id, source if source != "transcript" else _source_for(raw, source), workspace_path, projects)
            if session:
                sessions.append(session)
    return sessions, truncated


def _source_for(raw: dict, default: str) -> str:
    kind = str(raw.get("_brain_source") or "")
    return kind or default


def _workspace_label(folder: Path) -> str:
    meta = folder / "workspace.json"
    text = _read_text(meta) if meta.is_file() else None
    if not text:
        return folder.name
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return folder.name
    paths = _workspace_strings(data if isinstance(data, dict) else {})
    return paths[0] if paths else folder.name


def _match_workspace(folder: Path, projects: list[dict]) -> str | None:
    meta = folder / "workspace.json"
    text = _read_text(meta) if meta.is_file() else None
    hints: list[str] = []
    if text:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            hints.extend(_workspace_strings(data))
            for hint in list(hints):
                hints.extend(_code_workspace_folders(hint))
    if not hints:
        return None
    matched = [_match_location(hint, projects) for hint in hints]
    chosen = [item for item in matched if item]
    unique = list(dict.fromkeys(chosen))
    if len(unique) == 1:
        return unique[0]
    return None


def _workspace_strings(data: dict) -> list[str]:
    found: list[str] = []
    folder = data.get("folder")
    if isinstance(folder, str):
        found.append(folder)
    workspace = data.get("workspace")
    if isinstance(workspace, str):
        found.append(workspace)
    folders = data.get("folders")
    if isinstance(folders, list):
        for item in folders:
            if isinstance(item, str):
                found.append(item)
            elif isinstance(item, dict):
                for key in ("uri", "path", "folder"):
                    value = item.get(key)
                    if isinstance(value, str):
                        found.append(value)
    return found


def _code_workspace_folders(hint: str) -> list[str]:
    path = _uri_to_path(hint)
    if path is None or path.suffix != ".code-workspace" or not path.is_file():
        return []
    text = _read_text(path)
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    return _workspace_strings({"folders": data.get("folders")})


def _match_location(hint: str, projects: list[dict]) -> str | None:
    path = _uri_to_path(hint)
    if path is None:
        return None
    inside: list[str] = []
    parents: list[str] = []
    candidates = [path]
    if not path.is_absolute():
        for project in projects:
            candidates.append(project["directory"].parent / path)
            candidates.append(project["directory"] / path)
    for candidate in candidates:
        try:
            if not candidate.exists():
                continue
            resolved = candidate.resolve()
        except OSError:
            continue
        for project in projects:
            directory = project["directory"]
            try:
                directory = directory.resolve()
            except OSError:
                continue
            if resolved == directory or _is_under(resolved, directory):
                inside.append(project["id"])
            elif _is_under(directory, resolved) and resolved != directory:
                parents.append(project["id"])
    inside = list(dict.fromkeys(inside))
    if len(inside) == 1:
        return inside[0]
    if len(inside) > 1:
        return None
    parents = list(dict.fromkeys(parents))
    if len(parents) == 1:
        return parents[0]
    if len(parents) > 1:
        return None
    return _match_segment(hint, projects) or _match_segment(str(path), projects)


def _match_segment(value: str, projects: list[dict]) -> str | None:
    parts = [unquote(part).casefold() for part in re.split(r"[\\/]", value) if part and part not in {".", ".."}]
    if not parts:
        return None
    hits: list[str] = []
    for project in projects:
        names = {project["name"].casefold(), Path(str(project["rel"])).name.casefold()}
        if names & set(parts):
            hits.append(project["id"])
    hits = list(dict.fromkeys(hits))
    if len(hits) == 1:
        return hits[0]
    return None


def _match_by_files(paths: list[str], projects: list[dict]) -> str | None:
    hits: list[str] = []
    for raw in paths:
        owners = _owners(raw, projects)
        hits.extend(owners)
    hits = list(dict.fromkeys(hits))
    if len(hits) == 1:
        return hits[0]
    return None


def _owners(raw: str, projects: list[dict]) -> list[str]:
    name = Path(raw.replace("\\", "/")).name.casefold()
    rel = _rel_key(raw)
    hits = []
    for project in projects:
        for rec in project["files"]:
            file_rel = str(rec.get("rel") or "").replace("\\", "/").casefold()
            file_name = str(rec.get("name") or Path(file_rel).name).casefold()
            if rel and (file_rel == rel or file_rel.endswith("/" + rel)):
                hits.append(project["id"])
                break
            if name and file_name == name:
                hits.append(project["id"])
                break
    return list(dict.fromkeys(hits))


def _rel_key(raw: str) -> str:
    path = _uri_to_path(raw)
    text = str(path if path is not None else raw).replace("\\", "/").lstrip("/")
    return text.casefold()


def _uri_to_path(value: str) -> Path | None:
    text = value.strip().strip('"').strip("'")
    if not text or "\n" in text:
        return None
    if re.match(r"^[A-Za-z]:[\\/]", text):
        return Path(text)
    if "://" in text or text.startswith("file:"):
        parsed = urlparse(text)
        if parsed.scheme and parsed.scheme != "file":
            return None
        path = unquote(parsed.path or "")
        if re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        if not path:
            return None
        return Path(path)
    return Path(text).expanduser()


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def _parse_chat_file(text: str, filename: str) -> list[dict]:
    stripped = text.strip()
    if not stripped:
        return []
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > 1 and _looks_like_jsonl(lines):
        parsed = _parse_jsonl(text)
        if parsed:
            return parsed
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return _parse_jsonl(text)
    if isinstance(data, dict) and (_is_transcript(data) or _is_mutation(data)):
        parsed = _parse_jsonl(text if "\n" in text else text + "\n")
        if parsed:
            return parsed
    return _sessions_from_json(data, filename)


def _looks_like_jsonl(lines: list[str]) -> bool:
    objects = 0
    for line in lines[:8]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            return False
        if not isinstance(item, dict):
            return False
        objects += 1
    return objects > 0


def _parse_jsonl(text: str) -> list[dict]:
    rows: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    if not rows:
        return []
    if any(_is_transcript(row) for row in rows[:12]):
        session = _session_from_transcript(rows)
        return [session] if session else []
    if any(_is_mutation(row) for row in rows[:12]) or any("requests" in row or "sessionId" in row for row in rows[:3]):
        state = _apply_mutations(rows)
        if isinstance(state, dict):
            return _sessions_from_json(state, "jsonl")
        return []
    requests = [row for row in rows if isinstance(row.get("message"), (dict, str)) or "text" in row]
    if requests:
        return [{"requests": requests, "sessionId": rows[0].get("sessionId") or rows[0].get("id")}]
    return []


def _is_transcript(row: dict) -> bool:
    return str(row.get("type") or "") in _TRANSCRIPT_TYPES


def _is_mutation(row: dict) -> bool:
    return "kind" in row and ("v" in row or "k" in row)


def _apply_mutations(rows: list[dict]) -> dict | None:
    state: dict | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = _kind(row.get("kind"))
        if kind == 0 or (state is None and isinstance(row.get("v"), dict) and kind in {0, None}):
            value = row.get("v", row)
            if isinstance(value, dict):
                state = value
            continue
        if state is None and ("requests" in row or "sessionId" in row):
            state = row
            continue
        if state is None:
            continue
        path = row.get("k")
        if not isinstance(path, list) or not path:
            path = [path] if isinstance(path, str) else None
        if not path:
            continue
        if kind == 1:
            _set_path(state, path, row.get("v"))
        elif kind == 2:
            _append_path(state, path, row.get("v"))
        elif kind == 3:
            _delete_path(state, path)
    return state


def _kind(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _set_path(state: dict, path: list, value) -> None:
    parent, leaf = _parent(state, path, create=True)
    if isinstance(parent, dict) and leaf is not None:
        parent[leaf] = value
    elif isinstance(parent, list) and isinstance(leaf, int) and 0 <= leaf < len(parent):
        parent[leaf] = value


def _append_path(state: dict, path: list, value) -> None:
    parent, leaf = _parent(state, path, create=True)
    target = None
    if isinstance(parent, dict) and leaf is not None:
        target = parent.get(leaf)
        if target is None:
            target = []
            parent[leaf] = target
    elif isinstance(parent, list) and isinstance(leaf, int):
        while len(parent) <= leaf:
            parent.append([])
        target = parent[leaf]
    if isinstance(target, list):
        if isinstance(value, list):
            target.extend(value)
        else:
            target.append(value)


def _delete_path(state: dict, path: list) -> None:
    parent, leaf = _parent(state, path, create=False)
    if isinstance(parent, dict) and leaf in parent:
        parent.pop(leaf, None)
    elif isinstance(parent, list) and isinstance(leaf, int) and 0 <= leaf < len(parent):
        parent.pop(leaf)


def _parent(state, path: list, create: bool):
    current = state
    for part in path[:-1]:
        if isinstance(current, dict):
            if part not in current:
                if not create:
                    return None, None
                current[part] = {}
            current = current[part]
        elif isinstance(current, list) and isinstance(part, int):
            if part < 0 or part >= len(current):
                return None, None
            current = current[part]
        else:
            return None, None
    return current, path[-1]


def _sessions_from_json(data, filename: str) -> list[dict]:
    if isinstance(data, list):
        sessions = []
        for item in data:
            sessions.extend(_sessions_from_json(item, filename))
        return sessions
    if not isinstance(data, dict):
        return []
    if "requests" in data or "sessionId" in data or "creationDate" in data:
        data.setdefault("_filename", filename)
        return [data]
    for key in ("sessions", "chats", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return _sessions_from_json(value, filename)
        if isinstance(value, dict):
            return _sessions_from_json(list(value.values()), filename)
    entries = data.get("entries")
    if isinstance(entries, dict):
        return _sessions_from_json(list(entries.values()), filename)
    if isinstance(entries, list):
        return _sessions_from_json(entries, filename)
    return []


def _session_from_transcript(rows: list[dict]) -> dict | None:
    session_id = ""
    created = None
    cwd = ""
    requests = []
    for row in rows:
        kind = str(row.get("type") or "")
        if not session_id:
            session_id = str(row.get("id") or row.get("sessionId") or "")
        if created is None:
            created = row.get("timestamp") or row.get("createdAt")
        if isinstance(row.get("cwd"), str):
            cwd = row["cwd"]
        if kind == "user.message":
            requests.append(
                {
                    "message": row.get("message") if isinstance(row.get("message"), (dict, str)) else row,
                    "timestamp": row.get("timestamp"),
                }
            )
    if not requests and not session_id:
        return None
    return {
        "sessionId": session_id,
        "creationDate": created,
        "customTitle": "",
        "requests": requests,
        "cwd": cwd,
        "_brain_source": "transcript",
        "_rows": rows,
    }


def _editing_session(path: Path, project_id: str | None, workspace_path: str, projects: list[dict]) -> dict | None:
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return None
    except OSError:
        return None
    text = _read_text(path)
    if not text or not text.strip():
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    paths = _collect_paths(data)
    if project_id is None:
        project_id = _match_by_files(paths, projects)
    when = _mtime_iso(path)
    title = "Copilot edit session"
    summary = "Edited files in a Copilot chat." if paths else "Copilot edit session."
    files = _link_paths(paths, project_id, projects)
    if not files and not text.strip():
        return None
    return _finish(
        session_id=path.parent.name,
        project_id=project_id,
        workspace_path=workspace_path,
        title=title,
        when=when,
        source="chatEditingSessions",
        prompt="",
        prompts=[],
        files=files,
        projects=projects,
        summary=summary,
    )


def _sessions_from_vscdb(path: Path, project_id: str | None, workspace_path: str, projects: list[dict]) -> list[dict]:
    rows = _read_item_table(path, restricted=True)
    sessions: list[dict] = []
    for key, value in rows:
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            continue
        for raw in _sessions_from_json(data, key):
            session = _session_from_raw(raw, project_id, "state.vscdb", workspace_path, projects)
            if session:
                sessions.append(session)
    return sessions


def _sessions_from_loose_db(path: Path, project_id: str | None, workspace_path: str, projects: list[dict]) -> list[dict]:
    blobs = _read_text_cells(path)
    sessions: list[dict] = []
    for blob in blobs:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for raw in _sessions_from_json(data, path.name):
            session = _session_from_raw(raw, project_id, "globalStorage", workspace_path, projects)
            if session:
                sessions.append(session)
        if len(sessions) >= MAX_SESSIONS_PER_STORE:
            break
    return sessions


def _read_item_table(path: Path, restricted: bool) -> list[tuple[str, str]]:
    if not path.is_file():
        return []
    conn = _connect_ro(path)
    if conn is None:
        return []
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "ItemTable" not in tables:
            return []
        found = []
        for key, value in conn.execute("SELECT key, value FROM ItemTable"):
            key_text = str(key or "")
            if restricted and not _interesting_key(key_text):
                continue
            if isinstance(value, bytes):
                text = value.decode("utf-8", errors="replace")
            else:
                text = str(value or "")
            if text:
                found.append((key_text, text))
        return found
    except sqlite3.Error:
        log.debug("skip database %s", path, exc_info=True)
        return []
    finally:
        conn.close()


def _interesting_key(key: str) -> bool:
    lowered = key.lower()
    if key in _DB_KEYS:
        return True
    return "chat" in lowered or "interactive" in lowered or "copilot" in lowered


def _read_text_cells(path: Path) -> list[str]:
    conn = _connect_ro(path)
    if conn is None:
        return []
    blobs: list[str] = []
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables[:8]:
            if not re.fullmatch(r"[A-Za-z0-9_]+", table):
                continue
            columns = []
            for row in conn.execute(f"PRAGMA table_info({table})"):
                col_type = str(row[2] or "").lower()
                if (not col_type) or any(token in col_type for token in ("char", "text", "clob", "json", "blob")):
                    columns.append(str(row[1]))
            for column in columns[:6]:
                if not re.fullmatch(r"[A-Za-z0-9_]+", column):
                    continue
                try:
                    query = f"SELECT {column} FROM {table} LIMIT 40"
                    for (value,) in conn.execute(query):
                        if isinstance(value, str) and value.strip().startswith(("{", "[")):
                            blobs.append(value)
                        elif isinstance(value, bytes):
                            text = value.decode("utf-8", errors="replace")
                            if text.strip().startswith(("{", "[")):
                                blobs.append(text)
                except sqlite3.Error:
                    continue
            if len(blobs) >= 40:
                break
    except sqlite3.Error:
        log.debug("skip loose database %s", path, exc_info=True)
    finally:
        conn.close()
    return blobs


def _connect_ro(path: Path) -> sqlite3.Connection | None:
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        return sqlite3.connect(uri, uri=True)
    except (sqlite3.Error, OSError, ValueError):
        log.debug("could not open %s", path, exc_info=True)
        return None


def _session_from_raw(
    raw: dict,
    project_id: str | None,
    source: str,
    workspace_path: str,
    projects: list[dict],
) -> dict | None:
    if not isinstance(raw, dict):
        return None
    source = source or str(raw.get("_brain_source") or "chatSessions")
    prompts = _prompts(raw)
    paths = _collect_paths(raw)
    for prompt in prompts:
        paths.extend(_paths_in_text(prompt["text"]))
    cwd = raw.get("cwd")
    if isinstance(cwd, str) and project_id is None:
        project_id = _match_location(cwd, projects)
    if project_id is None:
        project_id = _match_by_files(paths, projects)
    files = _link_paths(paths, project_id, projects)
    for prompt in prompts:
        prompt["files"] = _link_paths(_paths_in_text(prompt["text"]) + prompt.get("_paths", []), project_id, projects)
        prompt.pop("_paths", None)
    first = prompts[0]["text"] if prompts else ""
    if not first and not files and not raw.get("customTitle") and not raw.get("title"):
        return None
    title = str(raw.get("customTitle") or raw.get("title") or "").strip()
    if not title:
        title = _clip(first, 80) or "Copilot chat"
    when = _when_from(raw.get("creationDate") or raw.get("createdAt") or (prompts[0].get("when") if prompts else None))
    session_id = str(raw.get("sessionId") or raw.get("id") or raw.get("_filename") or title)
    return _finish(
        session_id=session_id,
        project_id=project_id,
        workspace_path=workspace_path or (cwd if isinstance(cwd, str) else ""),
        title=title,
        when=when,
        source=source,
        prompt=first,
        prompts=prompts,
        files=files,
        projects=projects,
        summary="",
    )


def _finish(
    session_id: str,
    project_id: str | None,
    workspace_path: str,
    title: str,
    when: str | None,
    source: str,
    prompt: str,
    prompts: list[dict],
    files: list[dict],
    projects: list[dict],
    summary: str,
) -> dict:
    prompt = _clip(redact(prompt), MAX_TEXT)
    title = _clip(redact(title), 120) or "Copilot chat"
    clean_prompts = []
    for prompt_row in prompts[:MAX_PROMPTS]:
        text = _clip(redact(str(prompt_row.get("text") or "")), MAX_TEXT)
        if not text and not prompt_row.get("files"):
            continue
        clean_prompts.append({"text": text, "when": prompt_row.get("when"), "files": prompt_row.get("files") or []})
    clean_files = []
    seen = set()
    for item in files:
        key = (item.get("file_id"), item.get("rel"))
        if key in seen:
            continue
        seen.add(key)
        clean_files.append(item)
    if not summary:
        summary = _heuristic_summary(prompt, clean_files, title)
    else:
        summary = _clip(redact(summary), MAX_TEXT)
    project_name = None
    if project_id:
        project_name = next((project["name"] for project in projects if project["id"] == project_id), project_id)
    return {
        "id": session_id,
        "project_id": project_id,
        "project_name": project_name,
        "workspace_path": workspace_path,
        "title": title,
        "when": when,
        "source": source,
        "prompt": prompt,
        "summary": summary,
        "summary_source": "heuristic",
        "prompts": clean_prompts,
        "files": clean_files[:12],
    }


def _prompts(raw: dict) -> list[dict]:
    requests = raw.get("requests")
    if not isinstance(requests, list):
        requests = raw.get("messages") if isinstance(raw.get("messages"), list) else []
    prompts = []
    for request in requests:
        if isinstance(request, str):
            text = request
            when = None
            extra: list[str] = []
        elif isinstance(request, dict):
            message = request.get("message", request)
            text = _message_text(message)
            when = _when_from(request.get("timestamp") or request.get("creationDate") or request.get("when"))
            extra = _collect_paths(request)
        else:
            continue
        text = text.strip()
        if not text and not extra:
            continue
        prompts.append({"text": text, "when": when, "files": [], "_paths": extra})
        if len(prompts) >= MAX_PROMPTS:
            break
    return prompts


def _message_text(message) -> str:
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return ""
    for key in ("text", "content", "prompt", "value"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, list):
            parts = []
            for part in value:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    bit = part.get("text") or part.get("value") or part.get("content")
                    if isinstance(bit, str):
                        parts.append(bit)
            if parts:
                return "\n".join(parts)
    parts = message.get("parts")
    if isinstance(parts, list):
        bits = []
        for part in parts:
            if isinstance(part, str):
                bits.append(part)
            elif isinstance(part, dict):
                bit = part.get("text") or part.get("value")
                if isinstance(bit, str):
                    bits.append(bit)
        if bits:
            return "\n".join(bits)
    return ""


def _collect_paths(data, depth: int = 0, found: list[str] | None = None) -> list[str]:
    if found is None:
        found = []
    if depth > 7 or len(found) > 40:
        return found
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key) in _PATH_KEYS and isinstance(value, str) and _looks_like_path(value):
                found.append(value)
            elif isinstance(value, (dict, list)):
                _collect_paths(value, depth + 1, found)
    elif isinstance(data, list):
        for item in data[:30]:
            _collect_paths(item, depth + 1, found)
    return found


def _paths_in_text(text: str) -> list[str]:
    found = []
    for match in _TICK_RE.findall(text or ""):
        if _looks_like_path(match):
            found.append(match.strip())
    for match in _PATH_RE.findall(text or ""):
        if _looks_like_path(match):
            found.append(match.strip())
    return found


def _looks_like_path(value: str) -> bool:
    text = value.strip()
    if not text or len(text) > 240 or "\n" in text:
        return False
    if text.startswith(("http://", "https://")):
        return False
    name = Path(text.replace("\\", "/")).name
    if name.lower() in {".env", ".env.local"} or name.lower().startswith(".env."):
        return True
    if text.startswith("file:"):
        return True
    return bool(re.search(r"\.[A-Za-z0-9]{1,6}$", name))


def _link_paths(paths: list[str], project_id: str | None, projects: list[dict]) -> list[dict]:
    linked = []
    seen = set()
    scoped = [project for project in projects if project["id"] == project_id] if project_id else projects
    for raw in paths:
        if _is_env_path(raw):
            rel = Path(raw.replace("\\", "/")).name
            key = ("env", rel)
            if key in seen:
                continue
            seen.add(key)
            file_id = _file_id(rel, scoped)
            linked.append({"rel": rel, "name": rel, "file_id": file_id})
            continue
        rel = redact(_display_rel(raw, scoped))
        key = rel.casefold()
        if key in seen:
            continue
        seen.add(key)
        linked.append({"rel": rel, "name": Path(rel).name, "file_id": _file_id(rel, scoped)})
    return linked


def _is_env_path(raw: str) -> bool:
    name = Path(raw.replace("\\", "/")).name.lower()
    return name == ".env" or (name.startswith(".env.") and "example" not in name)


def _display_rel(raw: str, projects: list[dict]) -> str:
    path = _uri_to_path(raw)
    text = str(path if path is not None else raw).replace("\\", "/")
    for project in projects:
        prefix = str(project["directory"]).replace("\\", "/")
        if text.casefold().startswith(prefix.casefold().rstrip("/") + "/"):
            return text[len(prefix.rstrip("/")) + 1 :]
        for rec in project["files"]:
            rel = str(rec.get("rel") or "")
            if rel and (text.casefold().endswith("/" + rel.casefold()) or Path(text).name.casefold() == Path(rel).name.casefold()):
                if Path(text).name.casefold() == Path(rel).name.casefold() and text.casefold().endswith(rel.casefold()):
                    return rel
                if Path(text).name.casefold() == str(rec.get("name") or "").casefold():
                    return rel
    trimmed = text.lstrip("/")
    return trimmed or Path(text).name


def _file_id(rel: str, projects: list[dict]) -> str | None:
    name = Path(rel).name.casefold()
    exact = []
    named = []
    for project in projects:
        for rec in project["files"]:
            file_rel = str(rec.get("rel") or "")
            if file_rel.replace("\\", "/").casefold() == rel.replace("\\", "/").casefold():
                exact.append(rec.get("id"))
            elif name and str(rec.get("name") or "").casefold() == name:
                named.append(rec.get("id"))
    if len(exact) == 1:
        return exact[0]
    if len(named) == 1:
        return named[0]
    return None


def _heuristic_summary(prompt: str, files: list[dict], title: str) -> str:
    text = " ".join((prompt or "").split())
    if not text:
        text = title or "Copilot chat"
    sentence = re.split(r"(?<=[.!?])\s+", text)[0]
    sentence = _clip(sentence, 180)
    names = []
    for item in files:
        name = item.get("name") or item.get("rel")
        if name and name not in names and not _is_env_path(str(name)):
            names.append(str(name))
        if len(names) == 3:
            break
    if names:
        sentence = sentence.rstrip(".") + ". Mentions " + ", ".join(names) + "."
    return _clip(sentence, MAX_TEXT)


def _maybe_narrate(sessions: list[dict]) -> bool:
    flag = os.environ.get("BRAIN_COPILOT_LLM", "").strip().lower()
    if flag not in _ON:
        return False
    provider = resolve_provider()
    if not provider:
        return False
    pending = [session for session in sessions if session.get("prompt")][:8]
    if not pending:
        return False
    lines = []
    for session in pending:
        files = ", ".join(item["rel"] for item in session.get("files") or [])
        lines.append(f"{session['id']}: {session['prompt']} Files: {files}")
    user = (
        "Write a one-sentence summary of each Copilot chat. "
        'Reply with JSON only: {"<id>": "<summary>"}. Do not invent secrets or quote credential values.\n'
        + "\n".join(lines)
    )
    try:
        raw = complete(
            provider,
            "You summarize local coding chats. Reply with JSON only.",
            user,
            max_tokens=500,
            timeout=20,
        )
    except Exception:
        log.debug("copilot chat summary failed", exc_info=True)
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return False
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return False
    if not isinstance(data, dict):
        return False
    applied = False
    for session in pending:
        text = data.get(session["id"])
        if isinstance(text, str) and text.strip():
            session["summary"] = _clip(redact(text.strip()), MAX_TEXT)
            session["summary_source"] = "model"
            applied = True
    return applied


def _dedupe(sessions: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    order: list[str] = []
    for session in sessions:
        key = session.get("id") or ""
        if not key:
            key = f"{session.get('project_id')}:{session.get('prompt')}:{session.get('when')}"
        current = best.get(key)
        if current is None:
            best[key] = session
            order.append(key)
            continue
        if len(session.get("prompt") or "") > len(current.get("prompt") or ""):
            best[key] = session
    return [best[key] for key in order]


def _when_from(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp = stamp / 1000.0
        try:
            return datetime.fromtimestamp(stamp).astimezone().isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        parsed = _parse_when(value)
        if parsed:
            return parsed.isoformat(timespec="seconds")
    return None


def _parse_when(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return None


def _read_text(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        with path.open("rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    if not raw:
        return ""
    if b"\x00" in raw[:1024]:
        return None
    return raw[:MAX_FILE_BYTES].decode("utf-8", errors="replace")


def _clip(text: str, limit: int) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"
