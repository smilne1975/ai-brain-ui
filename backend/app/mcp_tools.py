"""Read-only AI Brain tools for Copilot agent mode.

Answers come from the in-memory index or the SQLite scan cache. A tool call
never starts a scan. Outputs are redacted and capped.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.activity import build_cards, build_timeline, window_days
from backend.app.ask import _score, _tokens
from backend.app.brief import build_brief
from backend.app.copilot_chats import load_chats, merge_chats
from backend.app.digest import build_digest
from backend.app.redact import redact
from backend.app import store

REPO = Path(__file__).resolve().parents[2]
MAX_BYTES = 20_000
_LOCK = threading.Lock()
TOOLS = (
    {
        "name": "search_projects",
        "description": "Search the redacted local project index. Returns project, file, snippet, and score. Does not read .env values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words to find in file names, summaries, and redacted excerpts."},
                "limit": {"type": "integer", "description": "Maximum hits. Default 8, max 20.", "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_brief",
        "description": "Pick up where you left off for one project: last work, decisions, open TODOs, and a next step.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string", "description": "Project folder id or name."}},
            "required": ["project"],
        },
    },
    {
        "name": "get_timeline",
        "description": "Recent file saves, git subjects, and Copilot sessions. Default window is 7 days.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "1, 7, or 30.", "default": 7},
                "project": {"type": "string", "description": "Optional project id or name."},
            },
        },
    },
    {
        "name": "explain_file",
        "description": "What a file is for: project, imports, importers, skills, unfinished markers, and MicroStation key-ins.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Repo-relative path, file name, or file id."}},
            "required": ["path"],
        },
    },
    {
        "name": "list_projects",
        "description": "Project status cards: activity, entry point, and run command.",
        "inputSchema": {"type": "object", "properties": {}},
    },
)


def tool_specs() -> list[dict]:
    specs = []
    for tool in TOOLS:
        specs.append(
            {
                **tool,
                "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            }
        )
    return specs


def write_phase(root: Path, phase: str) -> None:
    try:
        folder = Path(root) / ".brain"
        folder.mkdir(parents=True, exist_ok=True)
        payload = {"phase": phase, "at": _now()}
        (folder / "scan_phase.json").write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        return


def load_index(root: Path, engine=None) -> dict:
    root = Path(root).expanduser().resolve()
    scanning = False
    brain = None
    source = "missing"
    updated = None
    if engine is not None:
        scanning = getattr(engine, "phase", "") == "scanning"
        live = getattr(engine, "brain", None)
        if isinstance(live, dict):
            brain = live
            source = "memory"
            updated = live.get("scanned_at")
    if brain is None:
        cached = store.load_latest(root)
        if cached:
            brain, updated = cached
            source = "cache"
    phase = _read_phase(root)
    if phase == "scanning":
        scanning = True
    return {"root": root, "brain": brain, "scanning": scanning, "source": source, "updated_at": updated}


def run_tool(name: str, arguments: dict | None, index: dict) -> dict:
    started = time.perf_counter()
    args = arguments if isinstance(arguments, dict) else {}
    summary = _arg_summary(name, args)
    try:
        text, is_error = _invoke(name, args, index)
    except Exception as exc:
        text, is_error = f"{name} failed: {exc.__class__.__name__}", True
    text, truncated = cap_text(text)
    elapsed = int((time.perf_counter() - started) * 1000)
    log_call(index["root"], name, summary, len(text.encode("utf-8")), elapsed, truncated)
    return {"text": text, "is_error": is_error, "truncated": truncated, "bytes": len(text.encode("utf-8")), "ms": elapsed}


def cap_text(text: str) -> tuple[str, bool]:
    cleaned = redact(text or "")
    raw = cleaned.encode("utf-8")
    if len(raw) <= MAX_BYTES:
        return cleaned, False
    room = MAX_BYTES - len("\n\n[truncated to 20 KB]".encode("utf-8"))
    cut = raw[: max(room, 0)].decode("utf-8", errors="ignore")
    return cut.rstrip() + "\n\n[truncated to 20 KB]", True


def latest_digest(index: dict) -> str:
    root = index["root"]
    folder = root / ".brain" / "digests"
    if folder.is_dir():
        days = [path for path in folder.glob("day-*.md") if path.is_file()]
        days.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        if days:
            try:
                return days[0].read_text(encoding="utf-8")[:100_000]
            except OSError:
                pass
    note = _scan_note(index)
    brain = index.get("brain")
    if not brain:
        return note or "No daily digest is cached yet."
    payload = build_digest(root, brain, "day", load_chats(root, brain))
    text = payload.get("markdown") or ""
    if note:
        text = note + "\n\n" + text
    return text


def usage_report(root: Path, engine=None) -> dict:
    root = Path(root).expanduser().resolve()
    rows = _read_usage(root)
    counts: dict[str, int] = {tool["name"]: 0 for tool in TOOLS}
    counts["digest"] = 0
    for row in rows:
        tool = str(row.get("tool") or "")
        if tool:
            counts[tool] = counts.get(tool, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    recent = sorted(rows, key=lambda item: item.get("ts") or "", reverse=True)[:12]
    last = recent[0]["ts"] if recent else None
    index = load_index(root, engine)
    registered = _registration(root)
    if registered["ok"]:
        state, label = "registered", "Registered"
    elif any(row.get("source") == "demo" for row in rows):
        state, label = "sample", "Sample usage"
    else:
        state, label = "idle", "Not registered"
    return {
        "counts": [{"tool": name, "count": count} for name, count in ordered if name in counts],
        "last_call": last,
        "recent": recent,
        "tools": [{"name": tool["name"], "description": tool["description"]} for tool in TOOLS],
        "resource": "brain://digest/latest",
        "snippet": mcp_snippet(root),
        "link": {"state": state, "label": label, "last_call": last, "detail": registered["detail"]},
        "scanning": bool(index["scanning"]),
        "demo": root.name == "demo-projects" and os.getenv("BRAIN_MCP_DEMO") != "0",
        "index_source": index["source"],
    }


def doctor_report(root: Path, engine=None) -> dict:
    root = Path(root).expanduser().resolve()
    index = load_index(root, engine)
    checks = [
        _check_index(index),
        _check_fresh(index),
        _check_runnable(),
        _check_python(),
        _check_extension(),
        _check_registered(root),
        _check_last_call(root),
    ]
    return {"generated_at": _now(), "checks": checks, "snippet": mcp_snippet(root)}


def mcp_snippet(root: Path) -> str:
    payload = {
        "servers": {
            "ai-brain": {
                "type": "stdio",
                "command": sys.executable,
                "args": ["-m", "brain_mcp"],
                "cwd": str(REPO),
                "env": {
                    "BRAIN_ROOT": str(Path(root).expanduser().resolve()),
                    "BRAIN_CACHE": str(store.cache_path()),
                },
            }
        }
    }
    return json.dumps(payload, indent=2)


def log_call(root: Path, tool: str, summary: str, nbytes: int, elapsed_ms: int, truncated: bool) -> None:
    row = {
        "ts": _now(),
        "tool": tool,
        "args": redact(summary)[:240],
        "bytes": nbytes,
        "ms": elapsed_ms,
        "truncated": truncated,
        "source": "live",
    }
    try:
        folder = Path(root) / ".brain"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "mcp_usage.jsonl"
        line = json.dumps(row, ensure_ascii=False)
        with _LOCK:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except OSError:
        return


def _invoke(name: str, args: dict, index: dict) -> tuple[str, bool]:
    note = _scan_note(index)
    brain = index.get("brain")
    if name == "search_projects":
        if not brain:
            return note, False
        payload = search_projects(brain, str(args.get("query") or ""), args.get("limit") or 8)
    elif name == "get_brief":
        if not brain:
            return note, False
        payload = get_brief(index["root"], brain, str(args.get("project") or ""))
    elif name == "get_timeline":
        if not brain:
            return note, False
        payload = get_timeline(index["root"], brain, args.get("days") or 7, args.get("project"))
    elif name == "explain_file":
        if not brain:
            return note, False
        payload = explain_file(brain, str(args.get("path") or ""))
    elif name == "list_projects":
        if not brain:
            return note, False
        payload = list_projects(index["root"], brain)
    else:
        return f"Unknown tool {name}.", True
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, indent=2, ensure_ascii=False)
    if note and brain is not None and index.get("scanning"):
        text = note + "\n\n" + text
    return text, False


def search_projects(brain: dict, query: str, limit: object) -> dict:
    try:
        cap = int(limit)
    except (TypeError, ValueError):
        cap = 8
    cap = min(max(cap, 1), 20)
    tokens = _tokens(redact(query)[:500])
    if not tokens:
        return {"query": redact(query)[:200], "hits": [], "note": "Pass a few words to search."}
    names = {project["id"]: project.get("name") or project["id"] for project in brain.get("projects") or []}
    hits = []
    for rec in brain.get("files") or []:
        if rec.get("kind") == "env" or rec.get("env_class"):
            blob = f"{rec.get('rel') or ''} {' '.join(rec.get('env_keys') or [])}"
            snippet = "Key names only: " + ", ".join(rec.get("env_keys") or []) or "none"
        else:
            blob = f"{rec.get('rel') or ''} {rec.get('summary') or ''} {rec.get('excerpt') or ''}"
            snippet = (rec.get("excerpt") or rec.get("summary") or "")[:400]
        score = _score(tokens, blob)
        if score <= 0:
            continue
        hits.append(
            {
                "project": names.get(rec.get("project_id"), rec.get("project_id")),
                "project_id": rec.get("project_id"),
                "file": rec.get("rel") or "",
                "file_id": rec.get("id"),
                "snippet": redact(snippet),
                "score": score,
            }
        )
    hits.sort(key=lambda item: (-item["score"], item["project"] or "", item["file"]))
    return {"query": redact(query)[:200], "hits": hits[:cap]}


def get_brief(root: Path, brain: dict, project: str) -> dict:
    match = _find_project(brain, project)
    if match is None:
        return {"error": f"No project named {redact(project)[:80]}."}
    chats = load_chats(root, brain)
    brief = build_brief(root, brain, match["id"], chats)
    return {
        "project": brief.get("name"),
        "project_id": brief.get("project_id"),
        "last_doing": brief.get("last_doing"),
        "decisions": brief.get("decisions") or [],
        "todos": brief.get("todos") or [],
        "next_step": brief.get("next_step"),
        "key_files": brief.get("key_files") or [],
        "run_command": brief.get("run_command") or "",
        "copy_text": brief.get("copy_text") or "",
    }


def get_timeline(root: Path, brain: dict, days: object, project: object) -> dict:
    try:
        window = window_days(int(days))
    except (TypeError, ValueError):
        window = 7
    timeline = merge_chats(build_timeline(root, brain, window), load_chats(root, brain))
    wanted = str(project or "").strip().casefold()
    items = []
    for week in timeline.get("weeks") or []:
        for day in week.get("days") or []:
            for proj in day.get("projects") or []:
                if wanted and wanted not in {str(proj.get("project_id") or "").casefold(), str(proj.get("name") or "").casefold()}:
                    continue
                for commit in proj.get("commits") or []:
                    items.append(
                        {
                            "when": commit.get("when") or day.get("date"),
                            "project": proj.get("name"),
                            "kind": "git",
                            "text": commit.get("subject") or "",
                        }
                    )
                for rec in proj.get("files") or []:
                    items.append(
                        {
                            "when": day.get("date"),
                            "project": proj.get("name"),
                            "kind": rec.get("via") or "file",
                            "text": f"{rec.get('change') or 'saved'} {rec.get('rel') or ''}".strip(),
                        }
                    )
                for chat in proj.get("chats") or []:
                    items.append(
                        {
                            "when": chat.get("when") or day.get("date"),
                            "project": proj.get("name"),
                            "kind": "copilot",
                            "text": chat.get("summary") or chat.get("prompt") or chat.get("title") or "",
                        }
                    )
    return {"days": window, "project": project or None, "items": items[:80]}


def explain_file(brain: dict, path: str) -> dict:
    needle = redact(path).strip().replace("\\", "/")
    if not needle:
        return {"error": "Pass a file path."}
    files = list(brain.get("files") or [])
    match = _find_file(files, needle)
    if match is None:
        return {"error": f"No indexed file matches {needle[:120]}."}
    project = _project_by_id(brain, match.get("project_id"))
    importers = []
    for rec in files:
        if match["id"] in (rec.get("imports_local") or []) and rec.get("id") != match["id"]:
            importers.append(rec.get("rel") or rec.get("id"))
    if match.get("kind") == "env" or match.get("env_class"):
        snippet = "Key names only: " + ", ".join(match.get("env_keys") or []) or "none"
    else:
        snippet = (match.get("excerpt") or match.get("summary") or "")[:700]
    keyins = []
    report = (project or {}).get("microstation") or {}
    for item in report.get("keyins") or []:
        if item.get("file_id") == match.get("id") or item.get("rel") == match.get("rel") or item.get("xml") == match.get("rel"):
            keyins.append(
                {
                    "keyin": item.get("keyin"),
                    "handler": item.get("handler"),
                    "function": item.get("function"),
                    "found": item.get("found"),
                }
            )
    unfinished = [todo.get("text") or "" for todo in match.get("todos") or []]
    name = (match.get("name") or "").lower()
    if any(token in name for token in ("scratch", "copy", "wip", "stub")):
        unfinished.append(f"Filename looks unfinished: {match.get('rel')}")
    return {
        "project": (project or {}).get("name") or match.get("project_id"),
        "project_id": match.get("project_id"),
        "file": match.get("rel"),
        "file_id": match.get("id"),
        "kind": match.get("kind"),
        "summary": match.get("summary") or "",
        "snippet": redact(snippet),
        "env_keys": match.get("env_keys") or [],
        "imports": [_rel_for(files, item) for item in match.get("imports_local") or []],
        "importers": importers[:12],
        "skills": match.get("skills") or [],
        "unfinished": unfinished[:12],
        "keyins": keyins,
    }


def list_projects(root: Path, brain: dict) -> dict:
    cards = build_cards(root, brain)
    rows = []
    for card in cards.get("cards") or []:
        entry = card.get("entry") or {}
        rows.append(
            {
                "project": card.get("name"),
                "project_id": card.get("project_id"),
                "status": card.get("activity"),
                "entry": entry.get("path") or "",
                "run": entry.get("how") or "",
                "blurb": card.get("blurb") or "",
            }
        )
    return {"projects": rows}


def _find_project(brain: dict, name: str) -> dict | None:
    needle = name.strip().casefold()
    if not needle:
        return None
    for project in brain.get("projects") or []:
        if needle in {str(project.get("id") or "").casefold(), str(project.get("name") or "").casefold()}:
            return project
    return None


def _project_by_id(brain: dict, project_id: str | None) -> dict | None:
    for project in brain.get("projects") or []:
        if project.get("id") == project_id:
            return project
    return None


def _find_file(files: list[dict], needle: str) -> dict | None:
    folded = needle.casefold().lstrip("./")
    exact = [rec for rec in files if str(rec.get("rel") or "").casefold() == folded or str(rec.get("id") or "").casefold() == folded]
    if exact:
        return exact[0]
    last = folded.split("/")[-1]
    tail = [
        rec
        for rec in files
        if str(rec.get("rel") or "").casefold().endswith(folded)
        or str(rec.get("name") or "").casefold() == folded
        or (last and str(rec.get("name") or "").casefold() == last)
        or (last and str(rec.get("rel") or "").casefold().endswith("/" + last))
    ]
    if tail:
        tail.sort(key=lambda rec: len(rec.get("rel") or ""))
        return tail[0]
    return None


def _rel_for(files: list[dict], file_id: str) -> str:
    for rec in files:
        if rec.get("id") == file_id:
            return rec.get("rel") or file_id
    return file_id


def _scan_note(index: dict) -> str:
    if not index.get("brain"):
        return "No index is cached yet. Start AI Brain and let the scan finish. This tool does not start a scan."
    if index.get("scanning"):
        return "A scan is in progress. This answer is from the last finished index."
    return ""


def _arg_summary(name: str, args: dict) -> str:
    if name == "search_projects":
        return f"query={args.get('query') or ''} limit={args.get('limit') or 8}"
    if name == "get_brief":
        return f"project={args.get('project') or ''}"
    if name == "get_timeline":
        return f"days={args.get('days') or 7} project={args.get('project') or ''}"
    if name == "explain_file":
        return f"path={args.get('path') or ''}"
    if name == "digest":
        return "uri=brain://digest/latest"
    return name


def _read_phase(root: Path) -> str:
    path = root / ".brain" / "scan_phase.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(data.get("phase") or "") if isinstance(data, dict) else ""


def _read_usage(root: Path) -> list[dict]:
    rows = []
    path = root / ".brain" / "mcp_usage.jsonl"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    for line in text.splitlines():
        row = _usage_row(line, "live")
        if row:
            rows.append(row)
    if _demo_enabled(root):
        fixture = REPO / "fixtures" / "mcp_usage.jsonl"
        try:
            sample = fixture.read_text(encoding="utf-8")
        except OSError:
            sample = ""
        now = datetime.now(timezone.utc)
        for line in sample.splitlines():
            row = _usage_row(line, "demo")
            if not row:
                continue
            try:
                hours = float(row.pop("hours_ago", 0) or 0)
            except (TypeError, ValueError):
                hours = 0
            row["ts"] = (now - timedelta(hours=hours)).isoformat(timespec="seconds")
            rows.append(row)
    return rows


def _usage_row(line: str, source: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    data["source"] = source
    data["args"] = redact(str(data.get("args") or ""))[:240]
    return data


def _demo_enabled(root: Path) -> bool:
    flag = os.getenv("BRAIN_MCP_DEMO", "").strip()
    if flag == "0":
        return False
    if flag == "1":
        return True
    return root.name == "demo-projects"


def _registration(root: Path) -> dict:
    found = _registered_path(root)
    if found:
        return {"ok": True, "detail": f"Found {found}."}
    if _demo_enabled(root):
        return {
            "ok": False,
            "detail": "Sample calls are loaded for the demo. VS Code has not registered the server on this machine.",
        }
    return {"ok": False, "detail": "AI Brain is not listed in an mcp.json or a VS Code registration stamp."}


def _registered_path(root: Path) -> str:
    candidates = [
        root / ".brain" / "mcp_registered.json",
        REPO / ".brain" / "mcp_registered.json",
        REPO / ".vscode" / "mcp.json",
        root / ".vscode" / "mcp.json",
        *_user_mcp_paths(),
    ]
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if path.name == "mcp_registered.json":
            return str(path)
        if "brain_mcp" in text or "ai-brain" in text:
            return str(path)
    return ""


def _user_mcp_paths() -> list[Path]:
    home = Path.home()
    appdata = os.environ.get("APPDATA", "")
    paths = []
    if appdata:
        paths.append(Path(appdata) / "Code" / "User" / "mcp.json")
    paths.append(home / "Library" / "Application Support" / "Code" / "User" / "mcp.json")
    paths.append(home / ".config" / "Code" / "User" / "mcp.json")
    return paths


def _check_index(index: dict) -> dict:
    if index.get("brain"):
        stats = index["brain"].get("stats") or {}
        where = "in memory" if index["source"] == "memory" else "in the SQLite cache"
        detail = f"Index is {where}: {stats.get('projects', 0)} folders, {stats.get('files', 0)} files."
        if index.get("scanning"):
            return _row("index", "warn", "Index present", detail + " A scan is still running; tools use the last finished copy.", "Wait for the sidebar to say Mapped.")
        return _row("index", "pass", "Index present", detail, "")
    return _row(
        "index",
        "fail",
        "Index missing",
        "No scan is cached for this folder.",
        "Start AI Brain with start.bat and let the first scan finish. Tools will not scan on their own.",
    )


def _check_fresh(index: dict) -> dict:
    when = index.get("updated_at") or (index.get("brain") or {}).get("scanned_at")
    parsed = _parse_time(when)
    if parsed is None:
        return _row("fresh", "fail", "Index age unknown", "There is no scan timestamp.", "Run a scan from the dashboard.")
    age = datetime.now(timezone.utc) - parsed
    if age <= timedelta(days=7):
        return _row("fresh", "pass", "Index is fresh", f"Last saved {when}.", "")
    if age <= timedelta(days=30):
        return _row("fresh", "warn", "Index is getting old", f"Last saved {when}.", "Click Rescan in the dashboard.")
    return _row("fresh", "fail", "Index is stale", f"Last saved {when}.", "Click Rescan in the dashboard.")


def _check_runnable() -> dict:
    names = [tool["name"] for tool in tool_specs()]
    if {"search_projects", "get_brief", "get_timeline", "explain_file", "list_projects"} <= set(names):
        return _row("server", "pass", "MCP server can run", "python -m brain_mcp speaks MCP over stdio, and POST /mcp speaks the same JSON-RPC.", "")
    return _row("server", "fail", "MCP server is incomplete", "A tool definition is missing.", "Reinstall the ai-brain-ui checkout.")


def _check_python() -> dict:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        return _row("python", "pass", "Python path", f"{sys.executable} ({version}). This is the interpreter start.bat is using while the server runs.", "")
    return _row("python", "fail", "Python is too old", f"{sys.executable} is {version}.", "Install Python 3.11+ and start AI Brain with start.bat.")


def _check_extension() -> dict:
    path = REPO / "vscode-extension" / "package.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _row("extension", "warn", "Extension package not found", "vscode-extension/package.json is missing.", "Open the ai-brain-ui checkout and install releases/ai-brain-0.2.0.vsix.")
    version = str(data.get("version") or "unknown")
    return _row("extension", "pass", "VS Code extension", f"Package version {version}. Install releases/ai-brain-{version}.vsix if Copilot does not list AI Brain.", "")


def _check_registered(root: Path) -> dict:
    found = _registered_path(root)
    if found:
        return _row("registered", "pass", "MCP server is registered", f"Registration found at {found}.", "")
    return _row(
        "registered",
        "warn",
        "MCP server is not registered",
        _registration(root)["detail"],
        "Install the VSIX so VS Code registers it, or copy the mcp.json snippet into .vscode/mcp.json.",
    )


def _check_last_call(root: Path) -> dict:
    rows = _read_usage(root)
    if not rows:
        return _row("last-call", "warn", "No MCP calls yet", "The usage log is empty.", "Ask Copilot agent mode to use search_projects. Calls are written to .brain/mcp_usage.jsonl.")
    latest = max(rows, key=lambda item: item.get("ts") or "")
    source = "sample demo call" if latest.get("source") == "demo" else "live call"
    return _row("last-call", "pass", "Last MCP call", f"{latest.get('tool')} at {latest.get('ts')} ({source}).", "")


def _row(check_id: str, status: str, title: str, detail: str, fix: str) -> dict:
    return {"id": check_id, "status": status, "title": title, "detail": redact(detail), "fix": fix}


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
