"""Daily and weekly digests of the scanned folders.

The markdown is written under the scan root's .brain/digests/ only when the
user exports it, or when BRAIN_DIGEST=daily|weekly is set on a running server.
.env files are not read. Chat text is included from the local Copilot index
and is not sent to a model unless BRAIN_DIGEST_LLM=1 and a provider exists.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from backend.app.activity import _as_local, _cutoff, _iso, build_cards, build_timeline, window_days
from backend.app.brief import build_briefs
from backend.app.llm import complete, resolve_provider
from backend.app.redact import redact

log = logging.getLogger("brain.digest")


def normalize_period(period: str) -> str:
    raw = (period or "week").strip().lower()
    if raw in {"day", "daily", "today", "1"}:
        return "day"
    if raw in {"week", "weekly", "7"}:
        return "week"
    raise ValueError(period)


def digest_mode() -> str | None:
    raw = os.environ.get("BRAIN_DIGEST", "").strip().lower()
    if raw in {"", "0", "off", "false", "no"}:
        return None
    try:
        return normalize_period(raw)
    except ValueError:
        return None


def build_digest(root: Path, brain: dict, period: str, chats: dict, now: datetime | None = None) -> dict:
    period = normalize_period(period)
    now = _as_local(now)
    window = window_days(1 if period == "day" else 7)
    timeline = build_timeline(root, brain, window, now)
    cards = build_cards(root, brain, now)
    briefs = {item["project_id"]: item for item in build_briefs(root, brain, chats, now)["briefs"]}
    cutoff = _cutoff(window, now)
    touched = _touched(timeline)
    sessions = _sessions_in_window(chats, cutoff, now)
    stale, abandoned = _newly_quiet(cards["cards"], cutoff, now)
    todos = _todo_rollup(briefs)
    focus = _focus(briefs, touched, stale, abandoned, sessions)
    payload = {
        "period": period,
        "label": "Today" if period == "day" else "This week",
        "generated_at": _iso(now),
        "source": "heuristic",
        "window_start": _iso(cutoff),
        "window_end": _iso(now),
        "touched": touched,
        "newly_stale": stale,
        "newly_abandoned": abandoned,
        "todos": todos,
        "chats": sessions[:8],
        "focus": focus,
        "markdown": "",
    }
    _maybe_narrate(payload)
    payload["markdown"] = render_markdown(payload)
    return payload


def export_digest(root: Path, brain: dict, period: str, chats: dict, now: datetime | None = None) -> dict:
    now = _as_local(now)
    payload = build_digest(root, brain, period, chats, now)
    path = _write(root, payload["period"], payload["markdown"], now)
    payload["saved_path"] = str(path)
    return payload


def write_scheduled(root: Path, brain: dict, now: datetime | None = None) -> Path | None:
    """Write today's or this week's digest once. No-op unless BRAIN_DIGEST is set."""
    period = digest_mode()
    if period is None or not brain:
        return None
    now = _as_local(now)
    destination = _digest_path(root, period, now)
    if destination.exists():
        return None
    from backend.app.copilot_chats import load_chats

    payload = build_digest(root, brain, period, load_chats(root, brain), now)
    return _write(root, period, payload["markdown"], now)


def render_markdown(payload: dict) -> str:
    lines = [
        f"# AI Brain digest — {payload['label']}",
        "",
        f"Generated {payload['generated_at']}.",
        f"Window {payload['window_start']} to {payload['window_end']}.",
        "",
        "## Projects touched",
    ]
    lines.extend(_project_lines(payload["touched"], "No folder was saved in this window."))
    lines.extend(["", "## Newly stale"])
    lines.extend(_project_lines(payload["newly_stale"], "No folder slipped from active to stale in this window."))
    lines.extend(["", "## Newly abandoned"])
    lines.extend(_project_lines(payload["newly_abandoned"], "No folder slipped to abandoned in this window."))
    todos = payload["todos"]
    lines.extend(
        [
            "",
            "## Open TODOs",
            f"{todos['open']} open ({todos['fixmes']} FIXME).",
        ]
    )
    if todos["top"]:
        for item in todos["top"]:
            lines.append(f"- {item['kind']} in {item['project']} `{item['rel']}`: {item['text']}")
    else:
        lines.append("- None in the scan.")
    lines.extend(["", "## Copilot chats"])
    if payload["chats"]:
        for chat in payload["chats"]:
            when = chat.get("when") or "undated"
            lines.append(f"- {when} · {chat.get('project') or 'unmatched'} — {chat.get('prompt') or chat.get('summary')}")
    else:
        lines.append("- No Copilot session in this window.")
    lines.extend(["", "## Suggested focus"])
    if payload["focus"]:
        for index, item in enumerate(payload["focus"], start=1):
            lines.append(f"{index}. **{item['name']}** — {item['why']}")
    else:
        lines.append("Nothing is asking for attention.")
    lines.extend(["", "Values from .env files are not included."])
    return redact("\n".join(lines))


def _project_lines(items: list[dict], empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    lines = []
    for item in items:
        detail = item.get("detail") or ""
        suffix = f" — {detail}" if detail else ""
        lines.append(f"- **{item['name']}**{suffix}")
    return lines


def _touched(timeline: dict) -> list[dict]:
    grouped: dict[str, dict] = {}
    for week in timeline.get("weeks") or []:
        for day in week.get("days") or []:
            for project in day.get("projects") or []:
                slot = grouped.setdefault(
                    project["project_id"],
                    {
                        "project_id": project["project_id"],
                        "name": project["name"],
                        "files": 0,
                        "detail": "",
                    },
                )
                slot["files"] += len(project.get("files") or [])
                if not slot["detail"]:
                    slot["detail"] = project.get("summary") or ""
    rows = list(grouped.values())
    for row in rows:
        count = row["files"]
        summary = row["detail"]
        row["detail"] = f"{count} file{'s' if count != 1 else ''} saved. {summary}".strip()
    rows.sort(key=lambda item: item["files"], reverse=True)
    return rows


def _sessions_in_window(chats: dict, cutoff: datetime, now: datetime) -> list[dict]:
    rows = []
    horizon = now + timedelta(minutes=5)
    for session in (chats or {}).get("sessions") or []:
        when = _parse_when(session.get("when"))
        if when is None or when < cutoff or when > horizon:
            continue
        rows.append(
            {
                "id": session.get("id"),
                "project_id": session.get("project_id"),
                "project": session.get("project_name") or session.get("project_id") or "Unmatched",
                "when": session.get("when"),
                "prompt": session.get("prompt") or "",
                "summary": session.get("summary") or "",
            }
        )
    rows.sort(key=lambda item: item.get("when") or "", reverse=True)
    return rows


def _newly_quiet(cards: list[dict], cutoff: datetime, now: datetime) -> tuple[list[dict], list[dict]]:
    stale = []
    abandoned = []
    for card in cards:
        last = _parse_when(card.get("last_touched"))
        if last is None:
            continue
        row = {
            "project_id": card["project_id"],
            "name": card["name"],
            "detail": f"last touched {card.get('last_touched')}",
        }
        if card.get("activity") == "stale" and cutoff <= last + timedelta(days=7) <= now:
            stale.append(row)
        if card.get("activity") == "abandoned" and cutoff <= last + timedelta(days=30) <= now:
            abandoned.append(row)
    return stale, abandoned


def _todo_rollup(briefs: dict[str, dict]) -> dict:
    top = []
    open_count = 0
    fixmes = 0
    for brief in briefs.values():
        open_count += brief.get("todo_count", 0) + brief.get("fixme_count", 0)
        fixmes += brief.get("fixme_count", 0)
        for item in brief.get("todos") or []:
            top.append(
                {
                    "project_id": brief["project_id"],
                    "project": brief["name"],
                    "rel": item["rel"],
                    "text": item["text"],
                    "kind": item["kind"],
                }
            )
    top.sort(key=lambda item: (0 if item["kind"] == "FIXME" else 1, item["project"], item["rel"]))
    return {"open": open_count, "fixmes": fixmes, "top": top[:8]}


def _focus(briefs: dict[str, dict], touched: list[dict], stale: list[dict], abandoned: list[dict], sessions: list[dict]) -> list[dict]:
    order: list[str] = []
    for bucket in (abandoned, stale, touched):
        for item in bucket:
            if item["project_id"] not in order:
                order.append(item["project_id"])
    for session in sessions:
        project_id = session.get("project_id")
        if project_id and project_id not in order:
            order.append(project_id)
    ranked = []
    for project_id in order:
        brief = briefs.get(project_id)
        if not brief:
            continue
        score = 0
        if any(item["project_id"] == project_id for item in abandoned):
            score += 5
        if any(item["project_id"] == project_id for item in stale):
            score += 4
        if brief.get("fixme_count"):
            score += 3
        if brief.get("todo_count"):
            score += 2
        if any(session.get("project_id") == project_id for session in sessions):
            score += 1
        if score == 0:
            continue
        ranked.append((score, {"project_id": project_id, "name": brief["name"], "why": brief["next_step"]}))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item for _score, item in ranked[:5]]


def _maybe_narrate(payload: dict) -> None:
    flag = os.environ.get("BRAIN_DIGEST_LLM", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return
    provider = resolve_provider()
    if not provider:
        return
    names = ", ".join(item["name"] for item in payload["touched"][:8]) or "none"
    focus = "; ".join(f"{item['name']}: {item['why']}" for item in payload["focus"][:5]) or "none"
    user = (
        "Write two sentences for a local coding digest. "
        f"Touched: {names}. Focus: {focus}. "
        'Reply with JSON only: {"summary": ""}. Do not invent secrets.'
    )
    try:
        raw = complete(provider, "You summarize local coding weeks. Reply with JSON only.", user, max_tokens=200, timeout=20)
    except Exception:
        log.debug("digest narration failed", exc_info=True)
        return
    import json
    import re

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return
    summary = data.get("summary") if isinstance(data, dict) else None
    if isinstance(summary, str) and summary.strip():
        payload["summary"] = redact(" ".join(summary.split()))[:400]
        payload["source"] = "model"


def _digest_path(root: Path, period: str, now: datetime) -> Path:
    folder = Path(root).expanduser().resolve() / ".brain" / "digests"
    if period == "day":
        name = f"day-{now.date().isoformat()}.md"
    else:
        iso = now.isocalendar()
        name = f"week-{iso.year}-W{iso.week:02d}.md"
    return folder / name


def _write(root: Path, period: str, markdown: str, now: datetime) -> Path:
    path = _digest_path(root, period, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved = path.resolve()
    resolved.relative_to(Path(root).expanduser().resolve())
    resolved.write_text(markdown if markdown.endswith("\n") else markdown + "\n", encoding="utf-8")
    return resolved


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
