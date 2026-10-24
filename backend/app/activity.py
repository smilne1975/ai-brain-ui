"""Timeline and plain-English project cards.

Both views are derived from the indexed scan. File contents are not read again
for .env files. Git history is names and subjects only — never a diff.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from backend.app.llm import _parse_json_object, complete
from backend.app.redact import redact
from backend.app.scanner import ignored_dir_name
from backend.app import store

log = logging.getLogger("brain.activity")

_STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
_PKG_ALIASES = {
    "pil": {"pillow", "pil"},
    "cv2": {"opencv-python", "opencv-python-headless", "cv2"},
    "sklearn": {"scikit-learn", "sklearn"},
    "yaml": {"pyyaml", "yaml"},
    "dotenv": {"python-dotenv", "dotenv"},
    "bs4": {"beautifulsoup4", "bs4"},
    "github": {"pygithub", "github"},
    "atproto": {"atproto"},
    "chromadb": {"chromadb"},
}
_PKG_DISPLAY = {
    "pil": "pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "bs4": "beautifulsoup4",
    "github": "pygithub",
}
_EXT_LANG = {
    ".py": "Python",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".txt": "Text",
    ".rst": "Text",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".json": "JSON",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
    ".ini": "Config",
    ".cfg": "Config",
    ".sh": "Shell",
    ".bash": "Shell",
    ".ps1": "PowerShell",
    ".bat": "Batch",
    ".cmd": "Batch",
    ".ipynb": "Notebook",
    ".html": "HTML",
    ".css": "CSS",
}
_CMD_RE = re.compile(
    r"(?im)(?<![A-Za-z0-9_])((?:python3?|py|npm(?:\s+run)?|npx|node|uvicorn|streamlit|flask|bash)\s+[^\n`#]{1,120}|\./[A-Za-z0-9_./-]+)"
)
_ENTRY_NAMES = {"main.py", "app.py", "manage.py", "server.py", "index.js", "index.ts", "main.go"}
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def window_days(days: int) -> int:
    if days <= 1:
        return 1
    if days <= 7:
        return 7
    return 30


def build_timeline(root: Path, brain: dict, days: int, now: datetime | None = None) -> dict:
    root = Path(root).expanduser().resolve()
    now = _as_local(now)
    window = window_days(days)
    cutoff = _cutoff(window, now)
    projects = list(brain.get("projects") or [])
    files_by_project: dict[str, list[dict]] = {}
    for rec in brain.get("files") or []:
        files_by_project.setdefault(rec["project_id"], []).append(rec)

    buckets: dict[str, dict[str, dict]] = {}
    for project in projects:
        group = files_by_project.get(project["id"], [])
        indexed = {rec["rel"]: rec for rec in group}
        commits = _git_commits(_project_dir(root, project))
        for rec in group:
            when = _file_when(root, project, rec, now)
            if when is None or when < cutoff or when > now + timedelta(minutes=5):
                continue
            _add_file(
                buckets,
                project,
                when,
                rec["rel"],
                "saved",
                "mtime",
                None,
                _file_note("saved", rec["rel"], rec),
            )
        for commit in commits:
            when = commit.get("when")
            if not isinstance(when, datetime):
                continue
            when = _align(when, now)
            if when < cutoff or when > now + timedelta(minutes=5):
                continue
            day = when.date().isoformat()
            slot = _slot(buckets, day, project)
            slot["commits"].append(
                {"hash": commit["hash"], "subject": commit["subject"], "when": _iso(when)}
            )
            for item in commit["files"]:
                rec = indexed.get(item["rel"])
                _add_file(
                    buckets,
                    project,
                    when,
                    item["rel"],
                    item["change"],
                    "git",
                    commit["hash"],
                    _file_note(item["change"], item["rel"], rec),
                )

    weeks = _weeks(buckets)
    file_count = 0
    project_ids: set[str] = set()
    for week in weeks:
        for day in week["days"]:
            for proj in day["projects"]:
                project_ids.add(proj["project_id"])
                file_count += len(proj["files"])
                proj["summary"] = _change_summary(proj)
                proj["summary_source"] = "heuristic"
    return {
        "window_days": window,
        "label": {1: "Today", 7: "7 days", 30: "30 days"}[window],
        "generated_at": _iso(now),
        "source": "heuristic",
        "project_count": len(project_ids),
        "file_count": file_count,
        "weeks": weeks,
    }


def build_cards(root: Path, brain: dict, now: datetime | None = None) -> dict:
    root = Path(root).expanduser().resolve()
    now = _as_local(now)
    files_by_project: dict[str, list[dict]] = {}
    for rec in brain.get("files") or []:
        files_by_project.setdefault(rec["project_id"], []).append(rec)
    cards = []
    for project in brain.get("projects") or []:
        group = files_by_project.get(project["id"], [])
        cards.append(_card(root, project, group, now))
    cards.sort(key=lambda card: card.get("last_touched") or "", reverse=True)
    source = "heuristic"
    if cards and all(card["blurb_source"] == "model" for card in cards):
        source = "model"
    elif any(card["blurb_source"] == "model" for card in cards):
        source = "mixed"
    return {"generated_at": _iso(now), "source": source, "cards": cards}


def narrate_timeline(provider: dict, payload: dict) -> dict:
    groups = []
    for week in payload.get("weeks") or []:
        for day in week.get("days") or []:
            for proj in day.get("projects") or []:
                groups.append((f"{proj['project_id']}@{day['date']}", day["date"], proj))
    if not groups:
        return payload
    mapping = _narrate(
        provider,
        "timeline",
        [f"{key}:{proj['summary']}" for key, _date, proj in groups],
        _timeline_prompt(groups[:24]),
    )
    applied = 0
    total = 0
    for week in payload["weeks"]:
        for day in week["days"]:
            for proj in day["projects"]:
                total += 1
                text = mapping.get(f"{proj['project_id']}@{day['date']}")
                if not text:
                    continue
                proj["summary"] = _two_sentences(text)
                proj["summary_source"] = "model"
                applied += 1
    if applied and applied == total:
        payload["source"] = "model"
    elif applied:
        payload["source"] = "mixed"
    return payload


def narrate_cards(provider: dict, payload: dict) -> dict:
    pending = [card for card in payload.get("cards") or [] if card.get("blurb_source") != "model"]
    if not pending:
        payload["source"] = "model" if payload.get("cards") else payload.get("source", "heuristic")
        return payload
    mapping = _narrate(
        provider,
        "cards",
        [f"{card['project_id']}:{card['blurb']}" for card in pending],
        _cards_prompt(pending[:24]),
    )
    for card in payload["cards"]:
        text = mapping.get(card["project_id"])
        if not text:
            continue
        card["blurb"] = _two_sentences(text)
        card["blurb_source"] = "model"
    sources = {card["blurb_source"] for card in payload["cards"]}
    if sources == {"model"}:
        payload["source"] = "model"
    elif "model" in sources:
        payload["source"] = "mixed"
    return payload


def _narrate(provider: dict, kind: str, parts: list[str], user: str) -> dict[str, str]:
    if not user.strip():
        return {}
    key = _cache_key(kind, provider, parts)
    cached = store.load_llm(key)
    if cached:
        try:
            data = json.loads(cached)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and data:
            return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v.strip()}
    try:
        raw = complete(
            provider,
            "You describe messy local coding folders. Reply with JSON only. Never invent secrets or paste credential values.",
            user,
            max_tokens=800,
            timeout=20,
        )
    except Exception:
        log.exception("%s narration failed", kind)
        return {}
    mapping = _parse_json_object(raw)
    if mapping:
        store.save_llm(key, json.dumps(mapping))
    return mapping


def _timeline_prompt(groups: list[tuple[str, str, dict]]) -> str:
    blocks = []
    for key, date, proj in groups:
        files = ", ".join(item["rel"] for item in proj.get("files") or [])[:500]
        commits = "; ".join(item["subject"] for item in proj.get("commits") or [])[:400]
        blocks.append(
            f"id: {key}\ndate: {date}\nfolder: {proj['name']}\nfiles: {files or 'none'}\n"
            f"commits: {commits or 'none'}\nheuristic: {proj.get('summary') or ''}"
        )
    return (
        "For each id, write one plain-English sentence about what changed that day. "
        "Use only the file names and commit subjects given. Do not invent work.\n"
        "Return a JSON object mapping id to sentence, and nothing else.\n\n" + "\n\n".join(blocks)
    )


def _cards_prompt(cards: list[dict]) -> str:
    blocks = []
    for card in cards:
        entry = card.get("entry") or {}
        unfinished = card.get("unfinished") or {}
        blocks.append(
            "\n".join(
                [
                    f"id: {card['project_id']}",
                    f"name: {card['name']}",
                    f"heuristic: {card.get('blurb') or ''}",
                    f"run: {entry.get('how') or 'unknown'}",
                    f"todos: {unfinished.get('todos', 0)} fixmes: {unfinished.get('fixmes', 0)}",
                ]
            )
        )
    return (
        "For each id, write one or two plain-English sentences about what the folder is for. "
        "Do not invent services, keys, or files. Do not mention secret values.\n"
        "Return a JSON object mapping id to text, and nothing else.\n\n" + "\n\n".join(blocks)
    )


def _cache_key(kind: str, provider: dict, parts: list[str]) -> str:
    digest = hashlib.sha256()
    digest.update(kind.encode())
    digest.update(str(provider.get("name") or "").encode())
    digest.update(str(provider.get("model") or "").encode())
    for part in parts:
        digest.update(b"\0")
        digest.update(part.encode())
    return digest.hexdigest()


def _card(root: Path, project: dict, files: list[dict], now: datetime) -> dict:
    last = _last_touched(root, project, files, now)
    blurb, blurb_source = _blurb(project, files)
    entry = _entry(root, project, files)
    todos, fixmes = _marker_counts(files)
    languages = _languages(files)
    return {
        "project_id": project["id"],
        "name": project["name"],
        "blurb": blurb,
        "blurb_source": blurb_source,
        "activity": _activity(last, now),
        "run": "runs" if entry else "unknown",
        "entry": entry,
        "last_touched": _iso(last) if last else None,
        "files": len(files),
        "languages": languages,
        "unfinished": {
            "todos": todos,
            "fixmes": fixmes,
            "stubs": [rec["rel"] for rec in files if _is_stub(rec)][:8],
            "empty": [rec["rel"] for rec in files if _is_empty(rec)][:8],
            "missing_requirements": _missing_requirements(root, project, files),
        },
    }


def _activity(last: datetime | None, now: datetime) -> str:
    if last is None:
        return "abandoned"
    age = now - last
    if age <= timedelta(days=7):
        return "active"
    if age <= timedelta(days=30):
        return "stale"
    return "abandoned"


def _blurb(project: dict, files: list[dict]) -> tuple[str, str]:
    if project.get("summary_source") == "model" and (project.get("summary") or "").strip():
        return _two_sentences(project["summary"]), "model"
    readme = _readme(files)
    if readme and (readme.get("intro") or "").strip():
        return _two_sentences(readme["intro"]), "heuristic"
    for rec in files:
        if rec.get("entry") and (rec.get("intro") or "").strip():
            return _two_sentences(rec["intro"]), "heuristic"
    return _two_sentences(project.get("summary") or "No description yet."), "heuristic"


def _entry(root: Path, project: dict, files: list[dict]) -> dict | None:
    commands = _readme_commands(root, project, files)
    ranked = sorted((rec for rec in files if rec.get("entry")), key=lambda rec: _entry_rank(rec, commands))
    scripts = _package_scripts(root, project, files)
    shell = _shell_entry(files)
    chosen = ranked[0] if ranked else None
    command = _best_command(commands, chosen)
    if command:
        path = chosen["rel"] if chosen else _command_path(command, files)
        return {"path": path or "", "how": command, "kind": "readme"}
    if scripts:
        name, _cmd = _preferred_script(scripts)
        pkg = next(rec for rec in files if rec["name"] == "package.json")
        how = "npm start" if name == "start" else f"npm run {name}"
        parent = str(Path(pkg["rel"]).parent).replace("\\", "/")
        if parent not in {"", "."}:
            how = f"cd {parent} && {how}"
        return {"path": pkg["rel"], "how": how, "kind": "package"}
    if chosen:
        how = _python_how(chosen["rel"]) if chosen["kind"] == "python" or chosen["rel"].endswith(".py") else chosen["rel"]
        if chosen["kind"] in {"shell"} or chosen["name"].endswith((".sh", ".ps1", ".bat", ".cmd")):
            how = _shell_how(chosen["rel"])
        return {"path": chosen["rel"], "how": how, "kind": "python" if chosen["rel"].endswith(".py") else "script"}
    if shell:
        return {"path": shell["rel"], "how": _shell_how(shell["rel"]), "kind": "shell"}
    return None


def _entry_rank(rec: dict, commands: list[str]) -> tuple:
    name = rec["name"].lower()
    named = 0 if any(name in command.lower() for command in commands) else 1
    preferred = 0 if name in _ENTRY_NAMES else 1
    stub = 1 if _is_stub(rec) else 0
    return (named, preferred, stub, rec["rel"].count("/"), rec["rel"].lower())


def _best_command(commands: list[str], chosen: dict | None) -> str:
    if not commands:
        return ""
    if chosen:
        name = chosen["name"].lower()
        for command in commands:
            if name in command.lower():
                return command
    return commands[0]


def _command_path(command: str, files: list[dict]) -> str:
    lowered = command.lower()
    for rec in files:
        if rec["name"].lower() in lowered:
            return rec["rel"]
    return ""


def _python_how(rel: str) -> str:
    rel = rel.replace("\\", "/")
    return f"python {rel}"


def _shell_how(rel: str) -> str:
    rel = rel.replace("\\", "/")
    if rel.endswith(".ps1"):
        return f"powershell -File {rel}"
    if rel.endswith((".bat", ".cmd")):
        return rel
    return rel if rel.startswith("./") else f"./{rel}"


def _shell_entry(files: list[dict]) -> dict | None:
    names = {"run.sh", "start.sh", "start.bat", "start.cmd", "start.ps1"}
    hits = [rec for rec in files if rec["name"].lower() in names]
    if not hits:
        return None
    hits.sort(key=lambda rec: (rec["rel"].count("/"), rec["name"].lower()))
    return hits[0]


def _preferred_script(scripts: dict[str, str]) -> tuple[str, str]:
    for name in ("start", "dev", "serve"):
        if name in scripts:
            return name, scripts[name]
    name = sorted(scripts)[0]
    return name, scripts[name]


def _package_scripts(root: Path, project: dict, files: list[dict]) -> dict[str, str]:
    rec = next((item for item in files if item["name"] == "package.json"), None)
    if rec is None:
        return {}
    text = _indexed_text(root, project, rec)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    raw = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}
    scripts = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, str) and value.strip():
            scripts[key] = value.strip()[:160]
    return scripts


def _readme_commands(root: Path, project: dict, files: list[dict]) -> list[str]:
    ordered = sorted(files, key=lambda rec: _readme_rank(rec))
    commands: list[str] = []
    for rec in ordered:
        if _readme_rank(rec) > 1:
            break
        text = _indexed_text(root, project, rec)
        for match in _CMD_RE.finditer(text):
            command = _clean_command(match.group(1))
            if command and command not in commands:
                commands.append(command)
    return commands[:6]


def _readme_rank(rec: dict) -> int:
    name = rec["name"].lower()
    if name in {"readme.md", "readme.txt", "readme.rst"}:
        return 0
    if name in {"howto.md", "running.md"}:
        return 1
    return 9


def _clean_command(command: str) -> str:
    text = command.strip().strip("`").strip()
    text = text.rstrip(".,;:)]}")
    text = re.sub(r"\s+", " ", text)
    return text[:180]


def _readme(files: list[dict]) -> dict | None:
    for rec in files:
        if rec["name"].lower() == "readme.md":
            return rec
    return None


def _last_touched(root: Path, project: dict, files: list[dict], now: datetime) -> datetime | None:
    moments = []
    for rec in files:
        when = _file_when(root, project, rec, now)
        if when is not None:
            moments.append(when)
    commits = _git_commits(_project_dir(root, project), limit=1)
    for commit in commits:
        when = commit.get("when")
        if isinstance(when, datetime):
            moments.append(_align(when, now))
    if not moments:
        return None
    return max(moments)


def _marker_counts(files: list[dict]) -> tuple[int, int]:
    todos = 0
    fixmes = 0
    for rec in files:
        for item in rec.get("todos") or []:
            text = item.get("text") or ""
            if re.search(r"(?i)\bFIXME\b", text):
                fixmes += 1
            else:
                todos += 1
    return todos, fixmes


def _is_empty(rec: dict) -> bool:
    if rec.get("kind") == "env" or rec.get("env_class"):
        return False
    return not (rec.get("excerpt") or "").strip() and rec.get("lines", 0) <= 1


def _is_stub(rec: dict) -> bool:
    if rec.get("kind") == "env" or rec.get("env_class") or _is_empty(rec):
        return False
    name = (rec.get("name") or "").lower()
    if rec.get("kind") in {"python", "shell", "notebook"} and any(token in name for token in ("scratch", "copy", "wip", "stub")) and rec.get("lines", 0) <= 40:
        return True
    excerpt = (rec.get("excerpt") or "").strip()
    compact = re.sub(r"\s+", " ", excerpt).lower()
    if compact in {"pass", "...", "raise notimplementederror"}:
        return True
    if "notimplementederror" in compact and rec.get("lines", 0) <= 30:
        return True
    return False


def _missing_requirements(root: Path, project: dict, files: list[dict]) -> list[str]:
    local = set()
    imported: list[str] = []
    for rec in files:
        if rec.get("kind") != "python":
            continue
        rel = Path(rec["rel"])
        local.add(rel.stem)
        local.update(part for part in rel.parts[:-1])
        for name in rec.get("imports_top") or []:
            if name not in imported:
                imported.append(name)
    declared = _declared_requirements(root, project, files)
    missing = []
    for name in imported:
        if name in local or name in _STDLIB:
            continue
        if _requirement_satisfied(name, declared):
            continue
        label = _PKG_DISPLAY.get(name.lower(), name.lower().replace("_", "-"))
        if label not in missing:
            missing.append(label)
    return missing[:8]


def _requirement_satisfied(module: str, declared: set[str]) -> bool:
    options = {item.replace("_", "-") for item in _PKG_ALIASES.get(module.lower(), {module.lower()})}
    options.add(module.lower().replace("_", "-"))
    return bool(options & declared)


def _declared_requirements(root: Path, project: dict, files: list[dict]) -> set[str]:
    names: set[str] = set()
    for rec in files:
        lower = rec["name"].lower()
        if lower in {"requirements.txt", "requirements-dev.txt", "pipfile"} or lower.endswith(".txt") and "requirement" in lower:
            names.update(_requirement_tokens(_indexed_text(root, project, rec)))
        elif lower == "pyproject.toml":
            names.update(_requirement_tokens(_indexed_text(root, project, rec)))
        elif lower == "package.json":
            names.update(_package_deps(_indexed_text(root, project, rec)))
    return names


def _requirement_tokens(text: str) -> set[str]:
    found = set()
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip().strip(",").strip().strip('"').strip("'")
        if not stripped or stripped.startswith(("-", "[", "]", "{", "}")):
            continue
        token = re.split(r"[<>=!~;\[]", stripped, maxsplit=1)[0].strip()
        token = token.lower().replace("_", "-")
        if token and re.match(r"^[a-z0-9][a-z0-9.-]*$", token):
            found.add(token)
    return found


def _package_deps(text: str) -> set[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return set()
    found = set()
    if not isinstance(data, dict):
        return found
    for key in ("dependencies", "devDependencies"):
        block = data.get(key)
        if isinstance(block, dict):
            for name in block:
                if isinstance(name, str) and name.strip():
                    found.add(name.strip().lower())
    return found


def _languages(files: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for rec in files:
        if rec.get("kind") == "env" or rec.get("env_class"):
            name = "Env"
        else:
            name = _EXT_LANG.get(Path(rec["rel"]).suffix.lower(), (rec.get("kind") or "other").title())
        counts[name] = counts.get(name, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"name": name, "count": count} for name, count in ranked]


def _change_summary(proj: dict) -> str:
    files = proj.get("files") or []
    commits = proj.get("commits") or []
    shown = [item["rel"] for item in files[:3]]
    if len(files) > 3:
        shown.append(f"{len(files) - 3} more")
    names = _join(shown)
    if commits:
        subject = commits[0]["subject"].strip().rstrip(".")
        if files:
            return f"{subject}. Touched {names}."
        return f"{subject}."
    if not files:
        return "No files in this window."
    if len(files) == 1:
        return files[0].get("note") or f"Saved {files[0]['rel']}."
    return f"Saved {names}."


def _file_note(change: str, rel: str, rec: dict | None) -> str:
    if _is_env_rel(rel) or (rec and (rec.get("kind") == "env" or rec.get("env_class"))):
        return "Env file changed. Values are not read."
    verb = {"added": "Added", "deleted": "Removed", "modified": "Edited", "saved": "Saved"}.get(change, "Updated")
    summary = ""
    if rec and rec.get("summary") and rec.get("kind") != "env":
        summary = _two_sentences(rec["summary"], 1)
    name = Path(rel).name
    if summary and summary.lower() != name.lower():
        return f"{verb} {name}. {summary}"
    return f"{verb} {rel}."


def _add_file(buckets, project, when: datetime, rel: str, change: str, via: str, commit: str | None, note: str) -> None:
    if _skip_rel(rel):
        return
    day = when.date().isoformat()
    slot = _slot(buckets, day, project)
    existing = next((item for item in slot["files"] if item["rel"] == rel), None)
    event = {
        "rel": rel,
        "name": Path(rel).name,
        "when": _iso(when),
        "via": via,
        "change": change,
        "commit": commit,
        "note": note,
    }
    if existing is None:
        if len(slot["files"]) >= 40:
            slot["more"] = slot.get("more", 0) + 1
            return
        slot["files"].append(event)
        return
    if via == "git" and existing["via"] == "mtime":
        existing["via"] = "both"
    elif via == "mtime" and existing["via"] == "git":
        existing["via"] = "both"
    if change != "saved":
        existing["change"] = change
    if commit:
        existing["commit"] = commit
    if note and (existing.get("change") == "saved" or via == "git"):
        existing["note"] = note
    if _iso(when) >= existing["when"]:
        existing["when"] = _iso(when)


def _slot(buckets: dict, day: str, project: dict) -> dict:
    day_bucket = buckets.setdefault(day, {})
    slot = day_bucket.get(project["id"])
    if slot is None:
        slot = {
            "project_id": project["id"],
            "name": project["name"],
            "files": [],
            "commits": [],
            "more": 0,
        }
        day_bucket[project["id"]] = slot
    return slot


def _weeks(buckets: dict) -> list[dict]:
    days = []
    for day in sorted(buckets, reverse=True):
        projects = list(buckets[day].values())
        for proj in projects:
            proj["files"].sort(key=lambda item: item["when"], reverse=True)
            proj["commits"] = _unique_commits(proj["commits"])
        projects.sort(key=lambda proj: proj["files"][0]["when"] if proj["files"] else "", reverse=True)
        date = datetime.fromisoformat(day).date()
        days.append(
            {
                "date": day,
                "label": f"{_WEEKDAYS[date.weekday()]} {_MONTHS[date.month - 1]} {date.day}",
                "projects": projects,
            }
        )
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for day in days:
        date = datetime.fromisoformat(day["date"]).date()
        monday = date - timedelta(days=date.weekday())
        sunday = monday + timedelta(days=6)
        key = f"{monday.isocalendar().year}-W{monday.isocalendar().week:02d}"
        if key not in grouped:
            grouped[key] = {
                "id": key,
                "label": f"Week of {_MONTHS[monday.month - 1]} {monday.day}",
                "start": monday.isoformat(),
                "end": sunday.isoformat(),
                "file_count": 0,
                "project_count": 0,
                "days": [],
                "_projects": set(),
            }
            order.append(key)
        bucket = grouped[key]
        bucket["days"].append(day)
        for proj in day["projects"]:
            bucket["file_count"] += len(proj["files"])
            bucket["_projects"].add(proj["project_id"])
    weeks = []
    for key in order:
        bucket = grouped[key]
        bucket["project_count"] = len(bucket.pop("_projects"))
        weeks.append(bucket)
    return weeks


def _unique_commits(commits: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for commit in commits:
        if commit["hash"] in seen:
            continue
        seen.add(commit["hash"])
        unique.append(commit)
    return unique[:8]


def _git_commits(project_dir: Path, limit: int = 40) -> list[dict]:
    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return []
    cmd = [
        "git",
        "-C",
        str(project_dir),
        "log",
        f"--max-count={limit}",
        "--date=iso-strict",
        "--name-status",
        "--pretty=format:COMMIT%x09%H%x09%ad%x09%s",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return _parse_git_log(proc.stdout)


def _parse_git_log(text: str) -> list[dict]:
    commits = []
    current: dict | None = None
    for line in text.splitlines():
        if line.startswith("COMMIT\t"):
            if current:
                commits.append(current)
            parts = line.split("\t", 3)
            current = None
            if len(parts) < 4:
                continue
            _tag, sha, when_raw, subject = parts
            try:
                when = datetime.fromisoformat(when_raw)
            except ValueError:
                when = None
            current = {
                "hash": sha[:12],
                "when": when,
                "subject": redact(subject).strip()[:180],
                "files": [],
            }
            continue
        if current is None or not line.strip():
            continue
        bits = line.split("\t")
        status = bits[0]
        if status.startswith(("R", "C")) and len(bits) >= 3:
            path = bits[-1]
            change = "added" if status.startswith("C") else "modified"
        elif status[:1] in {"A", "D", "M", "T"} and len(bits) >= 2:
            path = bits[1]
            change = {"A": "added", "D": "deleted", "M": "modified", "T": "modified"}[status[:1]]
        else:
            continue
        path = path.strip().strip('"').replace("\\", "/")
        if not path or _skip_rel(path):
            continue
        current["files"].append({"rel": path, "change": change})
    if current:
        commits.append(current)
    return commits


def _file_when(root: Path, project: dict, rec: dict, now: datetime) -> datetime | None:
    mtime = rec.get("mtime")
    if isinstance(mtime, (int, float)) and mtime > 0:
        return datetime.fromtimestamp(mtime, tz=now.tzinfo)
    path = _safe_file(root, project, rec.get("rel") or "")
    if path is None:
        return None
    try:
        return datetime.fromtimestamp(path.lstat().st_mtime, tz=now.tzinfo)
    except OSError:
        return None


def _indexed_text(root: Path, project: dict, rec: dict, limit: int = 20000) -> str:
    if rec.get("env_class") or rec.get("kind") == "env" or _is_env_rel(rec.get("rel") or ""):
        return ""
    path = _safe_file(root, project, rec.get("rel") or "")
    if path is None:
        return rec.get("excerpt") or ""
    try:
        raw = path.read_bytes()[:limit]
    except OSError:
        return rec.get("excerpt") or ""
    if b"\x00" in raw[:1024]:
        return ""
    return raw.decode("utf-8", errors="replace")


def _safe_file(root: Path, project: dict, rel: str) -> Path | None:
    if not rel or rel.startswith(("/", "\\")) or ".." in Path(rel).parts:
        return None
    base = _project_dir(root, project)
    candidate = (base / rel).resolve()
    try:
        candidate.relative_to(base)
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _project_dir(root: Path, project: dict) -> Path:
    rel = project.get("rel") or "."
    if rel in {"", "."}:
        return root.resolve()
    return (root / rel).resolve()


def _skip_rel(rel: str) -> bool:
    parts = [part for part in rel.split("/") if part not in {"", "."}]
    return any(ignored_dir_name(part) for part in parts)


def _is_env_rel(rel: str) -> bool:
    name = Path(rel).name.lower()
    return name == ".env" or (name.startswith(".env.") and "example" not in name and "sample" not in name and "template" not in name)


def _two_sentences(text: str, limit: int = 2) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if not clean:
        return "No description yet."
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", clean) if part.strip()]
    if not parts:
        parts = [clean]
    kept = parts[:limit]
    sentence = " ".join(kept)
    if len(sentence) > 360:
        sentence = sentence[:357].rstrip() + "..."
    if sentence[-1:] not in ".!?":
        sentence += "."
    return sentence


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _as_local(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now().astimezone()
    if now.tzinfo is None:
        return now.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return now.astimezone()


def _align(when: datetime, now: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=now.tzinfo)
    return when.astimezone(now.tzinfo)


def _cutoff(window: int, now: datetime) -> datetime:
    if window <= 1:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(days=window)


def _iso(when: datetime) -> str:
    return when.isoformat(timespec="seconds")
