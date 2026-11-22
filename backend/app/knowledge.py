"""Local, review-gated project pages and reusable workflow drafts.

Generated pages never change scanned source files. A manifest keeps the current
revision while each approved Markdown version remains available for inspection.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from urllib.parse import quote as url_quote

from backend.app import clips
from backend.app.redact import redact
from backend.app.privacy import active as private_folders_active
from backend.app.scanner import _blocked_file, _resolve_under_root


def _home(root: Path) -> Path:
    return root / ".brain" / "knowledge"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")[:64] or "page"


def _page_id(project_id: str, topic: str | None) -> str:
    return project_id if not topic else f"{project_id}~{_slug(topic)}"


def _manifest(root: Path) -> dict:
    if private_folders_active():
        return {}
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
    if rec.get("env_class") or path is None or _blocked_file(path):
        return None
    try:
        if path.stat().st_size > 350_000:
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _file_identity(root: Path, rec: dict) -> str | None:
    path = _resolve_under_root(root, rec)
    if path is None or rec.get("env_class") or _blocked_file(path):
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    if not stat.st_ino:
        return None
    return f"{stat.st_dev}:{stat.st_ino}:{getattr(stat, 'st_birthtime_ns', '')}"


def _sources(root: Path, brain: dict, project_id: str, source_ids: list[str] | None = None) -> list[dict]:
    records = [rec for rec in brain["files"] if rec["project_id"] == project_id and not rec.get("env_class")
               and rec.get("kind") != "binary"]
    if source_ids is not None:
        allowed = set(source_ids)
        records = [rec for rec in records if rec["id"] in allowed]
    # Keep the first draft bounded and prefer documentation and entry points.
    records.sort(key=lambda rec: (not (rec["rel"].lower().endswith(".md") or rec.get("entry")), rec["rel"]))
    result = [dict(id=rec["id"], rel=rec["rel"], sha256=hash_value, summary=redact(rec["summary"]),
                 file_identity=_file_identity(root, rec))
            for rec in records[:20] if (hash_value := _fingerprint(root, rec))]
    if source_ids and not private_folders_active():
        project = _project(brain, project_id)
        for source_id in dict.fromkeys(source_ids):
            if len(result) >= 20:
                break
            if clip := clips.approved_clip(root, project, source_id):
                result.append({"id": source_id, "rel": clip["filename"], "kind": "clip", "source_url": clip["url"],
                               "title": clip["title"], "sha256": clips.fingerprint(clip),
                               "summary": " ".join(clip["content"].split())[:320]})
    return result


def _project(brain: dict, project_id: str) -> dict:
    return next(project for project in brain["projects"] if project["id"] == project_id)


def _passages(root: Path, brain: dict, project: dict, sources: list[dict]) -> list[str]:
    records = {record["id"]: record for record in brain["files"] if record["project_id"] == project["id"]}
    result = []
    for source in sources:
        cite = source["rel"]
        if source.get("kind") == "clip":
            record = clips.approved_clip(root, project, source["id"])
            if not record:
                continue
            cite, text = source["source_url"], record["content"]
            if "`" in cite:
                continue
        elif Path(cite).suffix.casefold() in {".md", ".markdown", ".txt", ".rst"} and "`" not in cite:
            record = records.get(source["id"])
            path = _resolve_under_root(root, record) if record else None
            try:
                if path is None or _blocked_file(path):
                    continue
                with path.open("rb") as handle:
                    text = handle.read(16_000).decode("utf-8-sig", errors="replace")
            except OSError:
                continue
        else:
            continue
        for line in text.splitlines():
            clean = " ".join(line.split())
            if (24 <= len(clean) <= 180 and not clean.startswith(("#", "-", ">", "[", "`", "<", "!"))
                    and '"' not in clean and redact(clean) == clean):
                result.append(f'> "{clean}" — `{cite}`')
                break
        if len(result) >= 8:
            break
    return result


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
    for item in sources:
        if item.get("kind") == "clip":
            title_label = re.sub(r"[\[\]\\\r\n]", " ", item["title"])
            url = url_quote(item["source_url"], safe=":/?#[]@!$&'*+,;=%")
            lines.append(f"- [{title_label}](<{url}>) (approved web clip) — {item['summary']}")
        else:
            lines.append(f"- `{item['rel']}` — {item['summary']}")
    if not sources:
        lines += ["No readable indexed source files; this page should not be approved."]
    if source_ids is not None and (passages := _passages(root, brain, project, sources)):
        lines += ["", "## Evidence excerpts", "", "Check these selected-source passages before drawing conclusions.", "",
                  "\n\n".join(passages)]
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
    if private_folders_active():
        raise ValueError("Knowledge saving is unavailable while private-folder exclusions are enabled")
    draft = preview(root, brain, project_id, topic, source_ids)
    findings = _review_findings(root, brain, draft, content, expected_revision, expected_sources)
    if blockers := [item["detail"] for item in findings if item["blocking"]]:
        raise ValueError(blockers[0])
    manifest = _manifest(root)
    current = manifest.get(draft["page_id"])
    if (current or {}).get("revision") != expected_revision:
        raise ValueError("The page changed since the preview; review it again")
    safe = redact(content.strip())
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


def review(root: Path, brain: dict, project_id: str, content: str, expected_revision: str | None,
           expected_sources: dict[str, str], topic: str | None, source_ids: list[str] | None) -> list[dict]:
    draft = preview(root, brain, project_id, topic, source_ids)
    return _review_findings(root, brain, draft, content, expected_revision, expected_sources)


def review_report(root: Path, brain: dict, project_id: str, content: str, expected_revision: str | None,
                  expected_sources: dict[str, str], topic: str | None, source_ids: list[str] | None) -> dict:
    draft = preview(root, brain, project_id, topic, source_ids)
    findings = _review_findings(root, brain, draft, content, expected_revision, expected_sources)
    before = draft["previous_content"].strip().splitlines()
    after = redact(content.strip()).splitlines()
    # Bound pathologically repetitive input: no quadratic diff on very long line arrays.
    if len(before) + len(after) > 4000:
        return {"findings": findings, "diff": "", "diff_limited": True}
    diff = "\n".join(unified_diff(before, after, fromfile="approved revision", tofile="reviewed draft", lineterm=""))
    return {"findings": findings, "diff": diff[:60_000], "diff_limited": len(diff) > 60_000}


def _review_findings(root: Path, brain: dict, draft: dict, content: str, expected_revision: str | None,
                     expected_sources: dict[str, str] | None) -> list[dict]:
    findings: list[dict] = []

    def report(kind: str, detail: str, blocking: bool = True) -> None:
        findings.append({"kind": kind, "detail": detail, "blocking": blocking})

    if not draft["sources"]:
        report("missing_source", "No readable indexed sources for this project")
    if draft["current_revision"] != expected_revision:
        report("new_revision", "The page changed since the preview; review it again")
    actual_sources = {item["id"]: item["sha256"] for item in draft["sources"]}
    if expected_sources is not None and actual_sources != expected_sources:
        report("stale_source", "Source files changed since the preview; review the new draft")
    if set(draft["source_ids"] or ()) - actual_sources.keys():
        report("missing_source", "One or more selected sources are missing, unreadable or outside the draft limit")
    safe = redact(content.strip())
    if not safe or len(safe) > 30_000 or not safe.startswith("# "):
        report("invalid_page", "Page must have a title and be at most 30,000 characters")
        return findings
    projected = [page for page in pages(root, brain) if page["page_id"] != draft["page_id"]]
    title = _slug(draft["title"])
    titles = {_slug(page["title"]) for page in projected} | {title}
    for link in _links(safe):
        if _slug(link) not in titles:
            report("broken_link", f"Unresolved link: [[{link}]]", False)
    if draft["topic"] and projected and not any(_slug(link) == title for page in projected for link in _links(page["content"])):
        report("orphan", "No other approved page links to this topic", False)
    if claims := list(_explicit_facts(safe)):
        subjects = {subject.casefold() for subject, _ in claims}
        for warning in list(_fact_conflicts(safe, draft["project_id"], projected, subjects))[:20]:
            report("possible_conflict", warning, False)
    allowed = {record["rel"]: record for record in brain["files"] if record["id"] in actual_sources}
    web_quotes = _clip_quote_sources(root, _project(brain, draft["project_id"]), draft["sources"])
    for issue in _quote_problems(root, safe, allowed, web_quotes):
        report("unverified_quote", issue)
    return findings


def _links(content: str) -> list[str]:
    return re.findall(r"\[\[([^\]|#\n]+)", content)


def _explicit_facts(content: str):
    """Only compare explicitly labelled claims; never infer a conflict from similar prose."""
    body = re.sub(r"^\s*(```|~~~).*?^\s*\1[^\n]*", "", content, flags=re.M | re.S)
    for subject, value in re.findall(r"^[^\S\n]*(?:[-*][^\S\n]+)?Fact:[^\S\n]*([^=\n]{2,100})=[^\S\n]*([^\n]{1,260})$", body, re.M | re.I):
        subject, value = subject.strip(), value.strip()
        if subject and value:
            yield subject, value


def _fact_conflicts(content: str, project: str, others: list[dict], only_subjects: set[str] | None = None):
    claims: dict[str, tuple[str, str, str]] = {}
    for page in [*others, {"project_id": project, "title": "this draft", "content": content}]:
        if page["project_id"] != project:
            continue
        for subject, value in _explicit_facts(page["content"]):
            key = " ".join(subject.casefold().split())
            if only_subjects is not None and subject.casefold() not in only_subjects:
                continue
            prior = claims.get(key)
            if prior and " ".join(value.casefold().split()) != prior[0]:
                yield f"Possible conflict about {subject}: {prior[1]} says “{prior[2]}”; {page['title']} says “{value}”. Check the source context."
            else:
                claims[key] = (" ".join(value.casefold().split()), page["title"], value)


def _clip_quote_sources(root: Path, project: dict, sources: list[dict]) -> dict[str, list[str]]:
    by_url: dict[str, list[str]] = {}
    for source in sources:
        if source.get("kind") == "clip" and (record := clips.approved_clip(root, project, source["id"])):
            by_url.setdefault(record["url"], []).append(record["content"])
    return by_url


def _quote_problems(root: Path, content: str, sources: dict[str, dict], web_quotes: dict[str, list[str]]):
    for quote, rel in re.findall(r'^>\s*"([^"\n]+)"\s*[-–—]\s*`?(https?://[^\s`]+|[^`\n]+\.(?:md|markdown|txt|rst))`?[^\S\n]*$', content, re.M | re.I):
        normalized = " ".join(quote.split())
        if rel.lower().startswith(("https://", "http://")):
            if not any(normalized in " ".join(text.split()) for text in web_quotes.get(rel, [])):
                yield "Quote not found at the cited approved web clip URL"
            continue
        rec = sources.get(rel)
        path = _resolve_under_root(root, rec) if rec and not rec.get("env_class") else None
        try:
            text = path.read_text(encoding="utf-8", errors="replace") if path and not _blocked_file(path) and path.stat().st_size <= 350_000 else ""
        except OSError:
            text = ""
        if not text or normalized not in " ".join(text.split()):
            yield f"Quote not found in reviewed source {rel}: {quote[:60]}"


def pages(root: Path, brain: dict) -> list[dict]:
    manifest = _manifest(root)
    records = {rec["id"]: rec for rec in brain["files"]}
    projects = {project["id"]: project for project in brain["projects"]}
    result = []
    for key, page in manifest.items():
        pid = page.get("project_id", key)
        if pid not in projects:
            continue
        if not re.fullmatch(r"[0-9a-f]{16}", str(page.get("revision", ""))):
            continue
        stale = []
        for src in page.get("sources", []):
            if src.get("kind") == "clip":
                record = clips.approved_clip(root, projects[pid], src["id"])
                fingerprint = clips.fingerprint(record) if record is not None else None
            else:
                rec = records.get(src["id"])
                fingerprint = _fingerprint(root, rec) if rec is not None else None
            if fingerprint != src["sha256"]:
                stale.append(src["id"])
        file = _home(root) / _slug(key) / f"{page['revision']}.md"
        content_sha256 = None
        try:
            raw = file.read_bytes()
            content = raw.decode("utf-8").replace("\r\n", "\n")
            content_sha256 = hashlib.sha256(raw).hexdigest()
        except (OSError, UnicodeError):
            content = ""
        result.append({**page, "page_id": key, "content": content, "content_sha256": content_sha256, "stale_sources": stale})
    return result


def source_impact(root: Path, brain: dict, approved_pages: list[dict], saved_answers: list[dict],
                  decisions: list[dict] = (), questions: list[dict] = ()) -> list[dict]:
    """List the approved artifacts that depend on each stale source."""
    records = {record["id"]: record for record in brain["files"]}
    impacts: dict[str, dict] = {}
    identities: dict[str, dict[str, list[dict]]] = {}

    def verified_move(source: dict, project_id: str) -> dict | None:
        identity = source.get("file_identity")
        if not identity:
            return None
        if project_id not in identities:
            index: dict[str, list[dict]] = {}
            for record in records.values():
                if record["project_id"] == project_id and (key := _file_identity(root, record)):
                    index.setdefault(key, []).append(record)
            identities[project_id] = index
        candidates = identities[project_id].get(identity, [])
        if len(candidates) != 1:
            return None
        target = candidates[0]
        if target["id"] == source["id"] or _fingerprint(root, target) != source["sha256"]:
            return None
        return {"id": target["id"], "rel": target["rel"]}

    keys = {"page": ("page_id", "title"), "answer": ("name", "name"), "decision": ("id", "title")}
    for kind, artifacts in (("page", approved_pages), ("answer", saved_answers), ("decision", decisions)):
        for artifact in artifacts:
            sources = {source["id"]: source for source in artifact["sources"]}
            for source_id in artifact["stale_sources"]:
                if source_id not in impacts:
                    record = records.get(source_id)
                    status = ("clip removed or changed" if sources[source_id].get("kind") == "clip" else
                              "missing or not indexed" if record is None else
                              "changed" if _fingerprint(root, record) is not None else "unreadable")
                    impacts[source_id] = {"source_id": source_id, "rel": sources[source_id]["rel"], "status": status,
                                          "affected": []}
                id_key, label_key = keys[kind]
                impacts[source_id]["affected"].append({"kind": kind, "project_id": artifact["project_id"],
                    "id": artifact[id_key], "label": artifact[label_key],
                    "passage": artifact.get("text", "")[:400] if kind == "decision" else None,
                    "move": verified_move(sources[source_id], artifact["project_id"]) if kind == "page" and source_id not in records else None})
    for question in questions:
        if question["state"] != "following":
            continue
        seen = set()
        for item in question["reviewed"]["items"]:
            source_id = item["id"]
            if source_id in seen:
                continue
            if source_id not in impacts and item["kind"] in {"file", "clip"}:
                record = records.get(source_id)
                project = next((p for p in brain["projects"] if p["id"] == item["project_id"]), None)
                clip = clips.approved_clip(root, project, source_id) if project and item["kind"] == "clip" else None
                expected = item.get("source_sha256")
                hash_now = (clips.fingerprint(clip) if clip else _fingerprint(root, record) if record else None) if expected else None
                if not (record or clip) or (expected and expected != hash_now):
                    impacts[source_id] = {"source_id": source_id, "rel": record["rel"] if record else item["label"],
                                          "status": "changed" if hash_now else "missing, unreadable or not indexed", "affected": []}
            if source_id not in impacts:
                continue
            seen.add(source_id)
            impacts[source_id]["affected"].append({"kind": "question", "project_id": item["project_id"],
                "id": question["id"], "label": question["question"], "passage": item["excerpt"], "move": None})
    return sorted(impacts.values(), key=lambda item: item["source_id"])


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
        for link in _links(page["content"]):
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
        selected = {src["id"] for src in page["sources"]}
        sources = {rec["rel"]: rec for rec in brain["files"] if rec["id"] in selected}
        web_quotes = _clip_quote_sources(root, _project(brain, pid), page["sources"])
        for issue in _quote_problems(root, page["content"], sources, web_quotes):
            findings.append({"project_id": pid, "kind": "unverified_quote", "detail": issue})
    if len(all_pages) > 1:
        for page in all_pages:
            if page.get("topic") and not inbound.get(_slug(page["title"]), 0):
                findings.append({"project_id": page["project_id"], "kind": "orphan",
                                 "detail": f"No page links to topic: {page['title']}"})
    for pid in dict.fromkeys(page["project_id"] for page in all_pages):
        findings.extend({"project_id": pid, "kind": "possible_conflict", "detail": warning}
                        for warning in list(_fact_conflicts("", pid, all_pages))[:20])
    return findings


def workflow_candidates(brain: dict, chats: dict, exported_sessions: list[dict] | None = None) -> list[dict]:
    """Only propose recurring, evidenced prompts; no automatic skill writes."""
    groups: dict[tuple[str, str], list[dict]] = {}
    projects = {p["id"] for p in brain["projects"]}
    records = {record["id"]: record for record in brain.get("files", [])}
    for session in chats.get("sessions", []):
        pid = session.get("project_id")
        if pid not in projects:
            continue
        for prompt in session.get("prompts", []):
            text = redact(prompt.get("text") or "").strip()
            normalized = " ".join(re.findall(r"[a-z0-9]+", text.lower())[:10])
            if 12 <= len(text) <= 400 and len(normalized.split()) >= 4:
                refs = []
                for file in prompt.get("files", []):
                    rec = records.get(file.get("file_id"))
                    if rec and rec["project_id"] == pid and not rec.get("env_class"):
                        refs.append(rec["rel"])
                groups.setdefault((pid, normalized), []).append({"session_id": session["id"], "text": text,
                    "when": prompt.get("when") or session.get("when"), "files": list(dict.fromkeys(refs))[:5]})
    candidates = []
    for (pid, key), items in groups.items():
        by_session = {}
        for item in items:
            by_session.setdefault(item["session_id"], item)
        if len(by_session) >= 2:
            candidates.append({"project_id": pid, "name": _slug(key)[:40] + "-" + hashlib.sha256(key.encode()).hexdigest()[:7],
                               "count": len(items), "sessions": len(by_session), "outcome": "unverified",
                               "examples": list(by_session.values())[:3]})
    traced: dict[tuple[str, str], list[dict]] = {}
    for session in exported_sessions or []:
        if (workflow := session.get("workflow")) and session.get("project_id") in projects:
            traced.setdefault((session["project_id"], workflow["name"].casefold()), []).append(session)
    for (pid, name), sessions in traced.items():
        if len({session["id"] for session in sessions}) < 2:
            continue
        successful = next((session for session in sorted(sessions, key=lambda row: row["when"], reverse=True)
                           if session["workflow"]["outcome"] == "success" and session["workflow"]["evidence"]
                           and session["workflow"]["steps"]), None)
        examples = ([successful] + [session for session in sessions if session is not successful]) if successful else sessions
        candidates.append({"project_id": pid, "name": _slug(name)[:35] + "-log-" + hashlib.sha256(name.encode()).hexdigest()[:7],
            "count": len(sessions), "sessions": len(sessions), "outcome": "reported success" if successful else "unverified",
            "suggested_steps": successful["workflow"]["steps"] if successful else [],
            "examples": [{"session_id": session["id"], "text": session["title"], "when": session["when"],
                          "files": [file["rel"] for file in session["files"]], "run_outcome": session["workflow"]["outcome"],
                          "evidence": session["workflow"]["evidence"]} for session in examples[:3]]})
    return candidates[:20]


def save_skill(root: Path, brain: dict, project_id: str, name: str, description: str, steps: str) -> dict:
    if private_folders_active():
        raise ValueError("Skill saving is unavailable while private-folder exclusions are enabled")
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


def save_answer(root: Path, brain: dict, project_id: str, title: str, answer: str, source_ids: list[str],
                passages: list[dict] = ()) -> dict:
    if private_folders_active():
        raise ValueError("Answer saving is unavailable while private-folder exclusions are enabled")
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
    safe_answer = "\n".join(line for line in redact(answer.strip()).splitlines() if not line.startswith("<!-- ai-brain-passage "))
    lines = [f"# {redact(title.strip())[:120]}", "", safe_answer, "", "## Sources", ""]
    lines += [f"- `{src['project_id']}/{src['rel']}` (sha256: {src['sha256']})" for src in sources]
    for passage in passages:
        src = next((item for item in sources if item["id"] == passage["id"]), None)
        if not src or not passage["excerpt"]:
            continue
        record = records[src["id"]]
        page = passage.get("page")
        text = (next((entry["text"] for entry in record.get("pdf_pages", []) if entry["page"] == page), "") if page
                else record.get("excerpt", ""))
        plain = passage["excerpt"].strip("…").strip()
        if not plain or plain not in " ".join(text.split()):
            continue
        path_now = _resolve_under_root(root, record)
        try:
            stat = path_now.stat() if path_now else None
        except OSError:
            continue
        if not stat or record.get("observed") != [str(stat.st_mtime_ns), stat.st_size]:
            continue
        stored = {**passage, "kind": "file", "project_id": src["project_id"], "label": f"{src['project_id']}/{src['rel']}",
                  "source_mtime": record.get("mtime")}
        lines.append("<!-- ai-brain-passage " + json.dumps(stored, ensure_ascii=True).replace("-", r"\u002d") + " -->")
    with path.open("x", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    return {"name": name, "project_id": project_id, "path": str(path), "sources": sources, "stale_sources": []}


def answers(root: Path, brain: dict) -> list[dict]:
    if private_folders_active():
        return []
    folder = root / ".brain" / "answers"
    records = {rec["id"]: rec for rec in brain["files"]}
    result = []
    for pid in (p["id"] for p in brain["projects"]):
        for path in (folder / _slug(pid)).glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            metadata = text.rsplit("\n## Sources\n", 1)[-1]
            sources = [{"rel": path_in_project, "sha256": sha, "id": f"{source_project}:{path_in_project}"}
                       for source_project, path_in_project, sha in re.findall(
                           r"^- `([^/`]+)/([^`]+)` \(sha256: ([0-9a-f]{64})\)$", metadata, re.M)]
            stale = [item["id"] for item in sources if item["id"] not in records or
                     _fingerprint(root, records[item["id"]]) != item["sha256"]]
            citations = []
            source_ids = {item["id"] for item in sources}
            marker = r"^<!-- ai-brain-passage (\{[^\r\n]{1,4000}\}) -->$"
            for encoded in re.findall(marker, metadata, re.M)[-8:]:
                try:
                    item = json.loads(encoded)
                    if isinstance(item.get("id"), str) and item["id"] in source_ids and isinstance(item.get("excerpt"), str):
                        pid_for_source, rel = item["id"].split(":", 1)
                        citations.append({"id": item["id"], "project_id": pid_for_source, "label": f"{pid_for_source}/{rel}",
                                          "kind": "file", "excerpt": redact(item["excerpt"])[:400],
                                          "page": item.get("page") if isinstance(item.get("page"), int) else None,
                                          "source_mtime": item.get("source_mtime") if isinstance(item.get("source_mtime"), int) else None,
                                          "stale": item["id"] in stale})
                except (ValueError, AttributeError):
                    continue
            text = re.sub(marker + r"\n?", "", text, flags=re.M)
            result.append({"name": path.stem, "project_id": pid, "content": text,
                           "sources": sources, "stale_sources": stale, "passages": citations})
    return result
