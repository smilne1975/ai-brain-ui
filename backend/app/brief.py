"""A short 'pick up where I left off' brief for one scanned project.

The brief is local. It uses the index, recent commits, and Copilot prompts
that were already loaded. .env files are never opened. A model rewrites the
prose only when BRAIN_BRIEF_LLM=1 and a provider is configured.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from backend.app.activity import (
    _as_local,
    _entry,
    _file_when,
    _git_commits,
    _indexed_text,
    _iso,
    _project_dir,
)
from backend.app.llm import complete, resolve_provider
from backend.app.redact import redact

log = logging.getLogger("brain.brief")

HANDOFF_NAME = "BRAIN_HANDOFF.md"
_ON = {"1", "true", "yes", "on"}
_DECISION_RE = re.compile(r"(?i)\b(decided|decision|keep|switch|will not|won't)\b")


def build_briefs(root: Path, brain: dict, chats: dict, now: datetime | None = None) -> dict:
    now = _as_local(now)
    briefs = []
    for project in brain.get("projects") or []:
        briefs.append(_one(root, brain, project, chats, now))
    used_model = _maybe_narrate(briefs)
    for brief in briefs:
        brief["copy_text"] = _copy_text(brief)
    source = "model" if used_model and briefs and all(item["source"] == "model" for item in briefs) else "heuristic"
    if used_model and any(item["source"] == "model" for item in briefs) and source != "model":
        source = "mixed"
    return {"generated_at": _iso(now), "source": source, "briefs": briefs}


def build_brief(root: Path, brain: dict, project_id: str, chats: dict, now: datetime | None = None) -> dict:
    board = build_briefs(root, brain, chats, now)
    brief = next((item for item in board["briefs"] if item["project_id"] == project_id), None)
    if brief is None:
        raise KeyError(project_id)
    return brief


def save_handoff(root: Path, brain: dict, project_id: str, chats: dict, now: datetime | None = None) -> dict:
    """Write BRAIN_HANDOFF.md. Called only from the explicit save endpoint."""
    brief = build_brief(root, brain, project_id, chats, now)
    project = next(item for item in brain.get("projects") or [] if item["id"] == project_id)
    directory = _project_dir(Path(root), project)
    target = (directory / HANDOFF_NAME).resolve()
    root_resolved = Path(root).expanduser().resolve()
    try:
        target.relative_to(directory.resolve())
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise KeyError(project_id) from exc
    directory.mkdir(parents=True, exist_ok=True)
    target.write_text(brief["copy_text"] + "\n", encoding="utf-8")
    return {"project_id": project_id, "path": str(target), "name": HANDOFF_NAME, "bytes": target.stat().st_size}


def _one(root: Path, brain: dict, project: dict, chats: dict, now: datetime) -> dict:
    files = [rec for rec in brain.get("files") or [] if rec.get("project_id") == project["id"]]
    sessions = [
        session
        for session in (chats or {}).get("sessions") or []
        if session.get("project_id") == project["id"]
    ]
    sessions.sort(key=lambda item: item.get("when") or "", reverse=True)
    todos = _todos(files)
    decisions = _decisions(root, project, files)
    entry = _entry(root, project, files)
    run_command = (entry or {}).get("how") or ""
    recent = _recent_files(root, project, files, now)
    commits = _git_commits(_project_dir(root, project), limit=3)
    key_files = _key_files(files, sessions, recent, entry)
    last_doing = _last_doing(sessions, recent, commits, project)
    next_step = _next_step(todos, files, sessions, run_command, project)
    return {
        "project_id": project["id"],
        "name": project.get("name") or project["id"],
        "generated_at": _iso(now),
        "source": "heuristic",
        "last_doing": last_doing,
        "decisions": decisions[:4],
        "todos": todos[:6],
        "todo_count": sum(1 for item in todos if item["kind"] == "TODO"),
        "fixme_count": sum(1 for item in todos if item["kind"] == "FIXME"),
        "next_step": next_step,
        "key_files": key_files[:6],
        "run_command": redact(run_command),
        "chats": [
            {
                "id": session.get("id"),
                "when": session.get("when"),
                "prompt": session.get("prompt") or "",
                "summary": session.get("summary") or "",
            }
            for session in sessions[:3]
        ],
        "copy_text": "",
    }


def _todos(files: list[dict]) -> list[dict]:
    items = []
    for rec in files:
        if rec.get("env_class") or rec.get("kind") == "env":
            continue
        for todo in rec.get("todos") or []:
            text = redact(str(todo.get("text") or "")).strip()
            if not text:
                continue
            kind = "FIXME" if re.search(r"(?i)\bFIXME\b", text) else "TODO"
            items.append({"text": text[:180], "rel": rec.get("rel") or "", "kind": kind, "line": todo.get("line")})
    items.sort(key=lambda item: (0 if item["kind"] == "FIXME" else 1, item["rel"], item.get("line") or 0))
    return items


def _decisions(root: Path, project: dict, files: list[dict]) -> list[str]:
    found: list[str] = []
    for rec in files:
        if rec.get("env_class") or rec.get("kind") == "env":
            continue
        name = (rec.get("name") or "").lower()
        if "decision" not in name:
            continue
        text = redact(_indexed_text(root, project, rec, limit=8000))
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("- ", "* ")):
                continue
            if re.search(r"(?i)\b(TODO|FIXME|HACK|XXX)\b", stripped):
                continue
            cleaned = redact(stripped[2:].strip())
            if cleaned and cleaned not in found:
                found.append(cleaned[:180])
    for commit in _git_commits(_project_dir(root, project), limit=8):
        subject = redact(str(commit.get("subject") or "")).strip()
        if subject and _DECISION_RE.search(subject) and subject not in found:
            found.append(subject[:180])
    return found


def _recent_files(root: Path, project: dict, files: list[dict], now: datetime) -> list[dict]:
    ranked = []
    for rec in files:
        if rec.get("env_class") or rec.get("kind") == "env":
            continue
        when = _file_when(root, project, rec, now)
        if when is None:
            continue
        ranked.append((when, rec))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [{"rel": rec.get("rel") or "", "when": _iso(when), "file_id": rec.get("id")} for when, rec in ranked[:6]]


def _key_files(files: list[dict], sessions: list[dict], recent: list[dict], entry: dict | None) -> list[dict]:
    by_rel = {rec.get("rel"): rec for rec in files}
    chosen: list[dict] = []
    seen: set[str] = set()

    def add(rel: str, why: str, file_id: str | None = None) -> None:
        rel = (rel or "").replace("\\", "/")
        if not rel or rel in seen:
            return
        rec = by_rel.get(rel)
        if rec and (rec.get("env_class") or rec.get("kind") == "env"):
            return
        seen.add(rel)
        chosen.append({"rel": rel, "file_id": file_id or (rec.get("id") if rec else None), "why": why})

    if entry and entry.get("path"):
        add(entry["path"], "entry point")
    prompted = _prompted(sessions)
    for session in ([prompted] if prompted else sessions[:1]):
        for item in session.get("files") or []:
            add(item.get("rel") or "", "named in the last Copilot prompt", item.get("file_id"))
    for rec in files:
        if rec.get("todos"):
            add(rec.get("rel") or "", "open TODO")
            if sum(1 for item in chosen if item["why"] == "open TODO") >= 2:
                break
    for item in recent[:2]:
        add(item["rel"], "saved recently", item.get("file_id"))
    return chosen


def _prompted(sessions: list[dict]) -> dict | None:
    for session in sessions:
        if (session.get("prompt") or "").strip():
            return session
    return None


def _last_doing(sessions: list[dict], recent: list[dict], commits: list[dict], project: dict) -> str:
    prompted = _prompted(sessions)
    if prompted:
        return f"Stu was last asking Copilot: {_sentence(prompted['prompt'])}"
    if sessions and (sessions[0].get("summary") or "").strip():
        return f"Stu was last in a Copilot session: {_sentence(sessions[0]['summary'])}"
    if commits and (commits[0].get("subject") or "").strip():
        return f"Stu last committed \"{redact(str(commits[0]['subject'])).strip()}\"."
    if recent:
        return f"Stu last saved {recent[0]['rel']}."
    summary = _sentence(project.get("summary") or "This folder has no recent note.")
    return f"Stu last left this folder as: {summary}"


def _next_step(todos: list[dict], files: list[dict], sessions: list[dict], run_command: str, project: dict) -> str:
    if todos:
        item = todos[0]
        verb = "Fix" if item["kind"] == "FIXME" else "Pick up"
        return f"{verb} {item['text']} ({item['rel']})."
    stubs = [rec for rec in files if _looks_unfinished(rec)]
    if stubs:
        return f"Finish the stub {stubs[0].get('rel')}."
    prompted = _prompted(sessions)
    if prompted:
        return f"Continue the last Copilot thread: {_sentence(prompted['prompt'])}"
    if run_command:
        return f"Run {run_command} and note what still breaks."
    if not project.get("entries"):
        return "This folder has no entry point. Write down the next step in the README."
    return "Re-read the README and write the next step at the top."


def _looks_unfinished(rec: dict) -> bool:
    name = (rec.get("name") or "").lower()
    if rec.get("kind") not in {"python", "shell", "notebook"}:
        return False
    return any(token in name for token in ("scratch", "copy", "wip", "stub"))


def _sentence(text: str) -> str:
    clean = redact(" ".join(str(text or "").split()))
    if len(clean) > 220:
        clean = clean[:219].rstrip() + "…"
    if clean and clean[-1] not in ".!?…":
        clean += "."
    return clean or "No note was saved."


def _copy_text(brief: dict) -> str:
    lines = [
        f"# Pick up where I left off: {brief['name']}",
        "",
        f"Stu was last doing: {brief['last_doing']}",
        "",
        "Recent decisions:",
    ]
    if brief["decisions"]:
        lines.extend(f"- {item}" for item in brief["decisions"])
    else:
        lines.append("- None written down.")
    lines.append("")
    lines.append(f"Open TODOs ({brief['todo_count']} TODO, {brief['fixme_count']} FIXME):")
    if brief["todos"]:
        lines.extend(f"- {item['kind']} in {item['rel']}: {item['text']}" for item in brief["todos"])
    else:
        lines.append("- None in the scan.")
    lines.extend(["", f"Suggested next step: {brief['next_step']}", "", "Key files:"])
    if brief["key_files"]:
        lines.extend(f"- {item['rel']} ({item['why']})" for item in brief["key_files"])
    else:
        lines.append("- None picked out.")
    lines.append("")
    if brief["run_command"]:
        lines.extend(["Run:", f"`{brief['run_command']}`", ""])
    else:
        lines.extend(["Run:", "No entry command found.", ""])
    lines.append("Paste this into a new Copilot or Claude chat. .env values are not included.")
    return redact("\n".join(lines))


def _maybe_narrate(briefs: list[dict]) -> bool:
    flag = os.environ.get("BRAIN_BRIEF_LLM", "").strip().lower()
    if flag not in _ON:
        return False
    provider = resolve_provider()
    if not provider:
        return False
    pending = briefs[:8]
    if not pending:
        return False
    blocks = []
    for brief in pending:
        blocks.append(
            "\n".join(
                [
                    f"id: {brief['project_id']}",
                    f"last: {brief['last_doing']}",
                    f"decisions: {'; '.join(brief['decisions']) or 'none'}",
                    f"next: {brief['next_step']}",
                ]
            )
        )
    user = (
        "Rewrite each local handoff in one sentence for last_doing and one sentence for next_step. "
        "Keep decisions as a JSON array of short strings, or an empty array. "
        'Reply with JSON only: {"<id>": {"last_doing": "", "decisions": [], "next_step": ""}}. '
        "Do not invent secrets or credential values.\n\n" + "\n\n".join(blocks)
    )
    try:
        raw = complete(
            provider,
            "You write short local handoff notes. Reply with JSON only.",
            user,
            max_tokens=700,
            timeout=20,
        )
    except Exception:
        log.debug("brief narration failed", exc_info=True)
        return False
    data = _parse_object(raw)
    applied = False
    for brief in pending:
        row = data.get(brief["project_id"])
        if not isinstance(row, dict):
            continue
        last = row.get("last_doing")
        step = row.get("next_step")
        decisions = row.get("decisions")
        if isinstance(last, str) and last.strip():
            brief["last_doing"] = _sentence(last)
            brief["source"] = "model"
            applied = True
        if isinstance(step, str) and step.strip():
            brief["next_step"] = _sentence(step)
            brief["source"] = "model"
            applied = True
        if isinstance(decisions, list):
            cleaned = []
            for item in decisions:
                if isinstance(item, str) and item.strip():
                    cleaned.append(_sentence(item).rstrip("."))
            if cleaned:
                brief["decisions"] = cleaned[:4]
                brief["source"] = "model"
                applied = True
    return applied


def _parse_object(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}
