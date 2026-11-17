"""Local, review-gated project pages and reusable workflow drafts.

Generated pages never change scanned source files. A manifest keeps the current
revision while each approved Markdown version remains available for inspection.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from backend.app.redact import redact
from backend.app.scanner import _resolve_under_root


def _home(root: Path) -> Path:
    return root / ".brain" / "knowledge"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")[:64] or "page"


def _page_id(project_id: str, topic: str | None) -> str:
    return project_id if not topic else f"{project_id}~{_slug(topic)}"


def _manifest(root: Path) -> dict:
    try:
        data = json.loads((_home(root) / "manifest.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_manifest(root: Path, data: dict) -> None:
    home = _home(root)
    home.mkdir(parents=True, exist_ok=True)
    path = home / "manifest.json"
    temp = home / "manifest.json.tmp"
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def _fingerprint(root: Path, rec: dict) -> str | None:
    path = _resolve_under_root(root, rec)
    if rec.get("env_class") or path is None or not path.is_file():
        return None
    try:
        if path.stat().st_size > 350_000:
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _sources(root: Path, brain: dict, project_id: str, source_ids: list[str] | None = None) -> list[dict]:
    records = [rec for rec in brain["files"] if rec["project_id"] == project_id and not rec.get("env_class")]
    if source_ids is not None:
        allowed = set(source_ids)
        records = [rec for rec in records if rec["id"] in allowed]
    # Keep the first draft bounded and prefer documentation and entry points.
    records.sort(key=lambda rec: (not (rec["rel"].lower().endswith(".md") or rec.get("entry")), rec["rel"]))
    return [dict(id=rec["id"], rel=rec["rel"], sha256=hash_value, summary=redact(rec["summary"]))
            for rec in records[:20] if (hash_value := _fingerprint(root, rec))]


def _project(brain: dict, project_id: str) -> dict:
    return next(project for project in brain["projects"] if project["id"] == project_id)


def preview(root: Path, brain: dict, project_id: str, topic: str | None = None,
            source_ids: list[str] | None = None) -> dict:
    project = _project(brain, project_id)
    topic = topic.strip()[:80] if topic else None
    key = _page_id(project_id, topic)
    sources = _sources(root, brain, project_id, source_ids)
    title = topic or project["name"]
    lines = [f"# {redact(title)}", ""]
    if not topic:
        lines += [redact(project["summary"]), ""]
    lines += ["## Source files", ""]
    lines += [f"- `{item['rel']}` — {item['summary']}" for item in sources]
    if not sources:
        lines += ["No readable indexed source files; this page should not be approved."]
    lines += ["", "## Open questions", "", "- What should be verified before relying on this summary?", ""]
    content = "\n".join(lines)
    current = _manifest(root).get(key)
    previous_content = ""
    if current and re.fullmatch(r"[0-9a-f]{16}", str(current.get("revision", ""))):
        try:
            previous_content = (_home(root) / _slug(key) / f"{current['revision']}.md").read_text(encoding="utf-8")
        except OSError:
            pass
    old_sources = {item["id"]: item["sha256"] for item in (current or {}).get("sources", [])}
    changed = [item["id"] for item in sources if old_sources.get(item["id"]) != item["sha256"]]
    missing = [key for key in old_sources if key not in {item["id"] for item in sources}]
    return {"project_id": project_id, "page_id": key, "topic": topic, "source_ids": source_ids,
            "title": title, "content": content,
            "previous_content": previous_content,
            "sources": sources, "changed_sources": changed, "missing_sources": missing,
            "current_revision": (current or {}).get("revision"), "warning": "Project scan reached its file cap" if brain.get("truncated") else ""}


def approve(root: Path, brain: dict, project_id: str, content: str, expected_revision: str | None,
            expected_sources: dict[str, str] | None = None, topic: str | None = None,
            source_ids: list[str] | None = None) -> dict:
    draft = preview(root, brain, project_id, topic, source_ids)
    if not draft["sources"]:
        raise ValueError("No readable indexed sources for this project")
    manifest = _manifest(root)
    current = manifest.get(draft["page_id"])
    if (current or {}).get("revision") != expected_revision:
        raise ValueError("The page changed since the preview; review it again")
    actual_sources = {item["id"]: item["sha256"] for item in draft["sources"]}
    if expected_sources is not None and actual_sources != expected_sources:
        raise ValueError("Source files changed since the preview; review the new draft")
    safe = redact(content.strip())
    if not safe or len(safe) > 30_000 or not safe.startswith("# "):
        raise ValueError("Page must have a title and be at most 30,000 characters")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    revision = hashlib.sha256((safe + now).encode()).hexdigest()[:16]
    folder = _home(root) / _slug(draft["page_id"])
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{revision}.md"
    # Never overwrite: even simultaneous approvals must not erase a revision.
    (folder / filename).open("x", encoding="utf-8").write(safe + "\n")
    manifest[draft["page_id"]] = {"title": draft["title"], "project_id": project_id,
                            "page_id": draft["page_id"], "topic": draft["topic"],
                            "revision": revision, "revisions": (current or {}).get("revisions", []) + [revision],
                            "sources": draft["sources"], "updated_at": now}
    _save_manifest(root, manifest)
    return manifest[draft["page_id"]]


def pages(root: Path, brain: dict) -> list[dict]:
    manifest = _manifest(root)
    records = {rec["id"]: rec for rec in brain["files"]}
    result = []
    for key, page in manifest.items():
        pid = page.get("project_id", key)
        if not any(project["id"] == pid for project in brain["projects"]):
            continue
        if not re.fullmatch(r"[0-9a-f]{16}", str(page.get("revision", ""))):
            continue
        stale = []
        for src in page.get("sources", []):
            rec = records.get(src["id"])
            if rec is None or _fingerprint(root, rec) != src["sha256"]:
                stale.append(src["id"])
        file = _home(root) / _slug(key) / f"{page['revision']}.md"
        try:
            content = file.read_text(encoding="utf-8")
        except OSError:
            content = ""
        result.append({**page, "page_id": key, "content": content, "stale_sources": stale})
    return result


def lint(root: Path, brain: dict) -> list[dict]:
    findings = []
    all_pages = pages(root, brain)
    titles = {_slug(page["title"]) for page in all_pages}
    content_seen: dict[str, dict] = {}
    inbound = {_slug(page["title"]): 0 for page in all_pages}
    for page in all_pages:
        pid = page["project_id"]
        if not page["content"]:
            findings.append({"project_id": pid, "kind": "missing_page", "detail": "Approved Markdown revision is missing"})
        for source in page["stale_sources"]:
            findings.append({"project_id": pid, "kind": "stale_source", "detail": f"Changed or unreadable source: {source}"})
        for link in re.findall(r"\[\[([^\]|#]+)", page["content"]):
            if _slug(link) not in titles:
                findings.append({"project_id": pid, "kind": "broken_link", "detail": f"Unresolved link: [[{link}]]"})
            elif _slug(link) != _slug(page["title"]):
                inbound[_slug(link)] += 1
        normalized = re.sub(r"\s+", " ", page["content"].casefold()).strip()
        if normalized and normalized in content_seen:
            other = content_seen[normalized]
            findings.append({"project_id": pid, "kind": "duplicate", "detail": f"Same content as {other['project_id']}/{other['title']}"})
        else:
            content_seen[normalized] = page
        for quote, rel in re.findall(r'^>\s*"([^"\n]+)"\s*[-–—]\s*`?([^`\n]+\.md)`?\s*$', page["content"], re.M):
            rec = next((rec for rec in brain["files"] if rec["project_id"] == pid and rec["rel"] == rel), None)
            path = _resolve_under_root(root, rec) if rec and not rec.get("env_class") else None
            try:
                text = path.read_text(encoding="utf-8", errors="replace") if path and path.stat().st_size <= 350_000 else ""
            except OSError:
                text = ""
            if not text or " ".join(quote.split()) not in " ".join(text.split()):
                findings.append({"project_id": pid, "kind": "unverified_quote", "detail": f"Quote not found in {rel}: {quote[:60]}"})
    if len(all_pages) > 1:
        for page in all_pages:
            if page.get("topic") and not inbound.get(_slug(page["title"]), 0):
                findings.append({"project_id": page["project_id"], "kind": "orphan",
                                 "detail": f"No page links to topic: {page['title']}"})
    return findings


def workflow_candidates(brain: dict, chats: dict) -> list[dict]:
    """Only propose recurring, evidenced prompts; no automatic skill writes."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for session in chats.get("sessions", []):
        pid = session.get("project_id")
        if pid not in {p["id"] for p in brain["projects"]}:
            continue
        for prompt in session.get("prompts", []):
            text = redact(prompt.get("text") or "").strip()
            normalized = " ".join(re.findall(r"[a-z0-9]+", text.lower())[:10])
            if 12 <= len(text) <= 400 and len(normalized.split()) >= 4:
                groups.setdefault((pid, normalized), []).append({"session_id": session["id"], "text": text})
    return [{"project_id": pid, "name": _slug(key)[:48], "count": len(items), "examples": items[:3]}
            for (pid, key), items in groups.items() if len({item["session_id"] for item in items}) >= 2][:20]


def save_skill(root: Path, brain: dict, project_id: str, name: str, description: str, steps: str) -> dict:
    _project(brain, project_id)
    slug = _slug(name)
    if not description.strip() or not steps.strip() or len(steps) > 10000:
        raise ValueError("A description and reviewed steps are required")
    folder = root / ".brain" / "skills" / _slug(project_id) / slug
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "SKILL.md"
    safe_description = redact(description.replace("\n", " ").strip()).replace('"', "'")[:250]
    text = f'---\nname: {slug}\ndescription: "{safe_description}"\n---\n\n# {redact(name.strip())[:80]}\n\n{redact(steps.strip())}\n'
    with path.open("x", encoding="utf-8") as file:
        file.write(text)
    return {"path": str(path), "name": slug}


def save_answer(root: Path, brain: dict, project_id: str, title: str, answer: str, source_ids: list[str]) -> dict:
    _project(brain, project_id)
    records = {rec["id"]: rec for rec in brain["files"]}
    sources = [{"id": sid, "rel": records[sid]["rel"], "project_id": records[sid]["project_id"], "sha256": digest}
               for sid in dict.fromkeys(source_ids) if sid in records
               if (digest := _fingerprint(root, records[sid]))]
    if not sources or not answer.strip() or len(answer) > 10_000:
        raise ValueError("An answer and a readable cited file in this project are required")
    name = _slug(title) or "answer"
    folder = root / ".brain" / "answers" / _slug(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    lines = [f"# {redact(title.strip())[:120]}", "", redact(answer.strip()), "", "## Sources", ""]
    lines += [f"- `{src['project_id']}/{src['rel']}` (sha256: {src['sha256']})" for src in sources]
    with path.open("x", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    return {"name": name, "project_id": project_id, "path": str(path), "sources": sources, "stale_sources": []}


def answers(root: Path, brain: dict) -> list[dict]:
    folder = root / ".brain" / "answers"
    records = {rec["id"]: rec for rec in brain["files"]}
    result = []
    for pid in (p["id"] for p in brain["projects"]):
        for path in (folder / _slug(pid)).glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            sources = [{"rel": path_in_project, "sha256": sha, "id": f"{source_project}:{path_in_project}"}
                       for source_project, path_in_project, sha in re.findall(
                           r"^- `([^/`]+)/([^`]+)` \(sha256: ([0-9a-f]{64})\)$", text, re.M)]
            stale = [item["id"] for item in sources if item["id"] not in records or
                     _fingerprint(root, records[item["id"]]) != item["sha256"]]
            result.append({"name": path.stem, "project_id": pid, "content": text,
                           "sources": sources, "stale_sources": stale})
    return result
