"""Answer questions from the local index, optionally with a model."""

from __future__ import annotations

import re

from backend.app.catalog import SERVICES
from backend.app.llm import complete
from backend.app.microstation import index_for_ask
from backend.app.redact import redact

_STOP = {
    "a", "an", "the", "this", "that", "what", "which", "who", "how", "does", "do",
    "is", "are", "was", "were", "to", "of", "in", "on", "for", "and", "or", "with",
    "about", "me", "my", "your", "from", "into", "over", "still", "show", "up",
    "where", "when", "why", "can", "you", "tell", "please", "actually", "system",
}


def answer(brain: dict, question: str, project_id: str | None, provider: dict | None) -> dict:
    question = redact(question.strip())[:2000]
    if not question:
        return {
            "answer": "Ask about a folder, a skill, or a service in this corpus.",
            "citations": [],
            "provider": "heuristic",
        }
    projects = _scoped_projects(brain, project_id)
    files = [f for f in brain["files"] if f["project_id"] in {p["id"] for p in projects}]
    heuristic = _heuristic(brain, question, projects, files)
    if not provider:
        return heuristic
    try:
        packed = _pack(projects, files, question)
        text = complete(
            provider,
            (
                "You explain a person's messy local AI and coding folders. "
                "Use only the context. Write 2 to 5 plain sentences. "
                "Mention file paths when they help. "
                "Never invent API keys, tokens, or secret values. "
                "If a value was redacted, mention the key name only. "
                "If the context is thin, say so."
            ),
            f"Question: {question}\n\nContext:\n{packed}",
            max_tokens=500,
        )
        text = redact(text).strip()
        if not text:
            raise RuntimeError("empty")
        return {"answer": text, "citations": heuristic["citations"], "provider": provider["display"]}
    except Exception:
        heuristic["answer"] += "\n\nThe model call failed, so this answer is from the local index."
        heuristic["provider"] = "heuristic"
        return heuristic


def _scoped_projects(brain: dict, project_id: str | None) -> list[dict]:
    if project_id and project_id not in {"corpus", "all"}:
        chosen = [p for p in brain["projects"] if p["id"] == project_id]
        if chosen:
            return chosen
    return list(brain["projects"])


def _heuristic(brain: dict, question: str, projects: list[dict], files: list[dict]) -> dict:
    low = question.lower()
    keyin = _keyin_answer(brain, question, projects)
    if keyin and (re.search(r"key[\s-]?ins?\b", low) or _keyin_phrase(question, brain)):
        return keyin
    if re.search(r"unfinished|todo|fixme|\bwip\b|\bhack\b|left to do", low):
        return _todos(projects, files)
    service = _match_service(low, brain["connections"])
    if service and re.search(r"which folder|which project|talk to|connect|uses|depend|who uses", low):
        return _service_answer(service, projects, brain)
    if re.search(r"\bwired\b|architecture|flowchart|how is", low):
        named = _named_projects(low, projects)
        if named:
            return _wired(named[0], brain, files)
    named = _named_projects(low, projects)
    skill = _match_skill(low, brain["skills"])
    if skill and re.search(r"where|show up|implemented|which file", low):
        return _skill_answer(skill, projects)
    if named and re.search(r"what|summar|do\b|about", low):
        return _explain_project(named[0], files)
    if skill:
        return _skill_answer(skill, projects)
    if named:
        return _explain_project(named[0], files)
    return _overlap(question, projects, files)


def _todos(projects: list[dict], files: list[dict]) -> dict:
    names = {p["id"]: p["name"] for p in projects}
    lines = []
    citations = []
    for rec in files:
        for todo in rec["todos"]:
            label = f"{names.get(rec['project_id'], rec['project_id'])}/{rec['rel']}"
            lines.append(f"{label}:{todo['line']}  {todo['text']}")
            citations.append(_cite(rec, names))
            if len(lines) >= 12:
                break
        if len(lines) >= 12:
            break
    if not lines:
        return {
            "answer": "No TODO, FIXME, or HACK markers showed up in the scanned notes and scripts.",
            "citations": [],
            "provider": "heuristic",
        }
    return {
        "answer": "Unfinished markers in the scan:\n" + "\n".join(lines),
        "citations": _unique_cites(citations)[:6],
        "provider": "heuristic",
    }


def _service_answer(service: dict, projects: list[dict], brain: dict) -> dict:
    names = {p["id"]: p["name"] for p in brain["projects"]}
    folders = [names[pid] for pid in service["projects"] if pid in names and any(p["id"] == pid for p in projects)]
    if service["status"] == "connected":
        key_bits = [e["how"] for e in service["evidence"] if e["how"].startswith("env key")]
        key_text = f" {key_bits[0]}." if key_bits else ""
        status = f"{service['name']} is connected.{key_text}"
    elif service["status"] == "referenced":
        status = f"{service['name']} is mentioned in the folders. No live env key name was found for it."
    else:
        status = f"{service['name']} does not appear in this scan."
    if folders:
        body = status + " Folders: " + _join(folders) + "."
    else:
        body = status
    citations = []
    for item in service["evidence"]:
        if item["project_id"] not in names:
            continue
        citations.append(
            {
                "id": item["file_id"],
                "label": f"{names[item['project_id']]}/{item['rel']}",
                "kind": "file",
                "project_id": item["project_id"],
            }
        )
    return {"answer": body, "citations": _unique_cites(citations)[:6], "provider": "heuristic"}


def _wired(project: dict, brain: dict, files: list[dict]) -> dict:
    graph = brain["architecture"]["projects"].get(project["id"], {"nodes": []})
    decisions = [n["label"] for n in graph["nodes"] if n["kind"] == "decision"]
    service_names = [_service_name(sid) for sid in project.get("services") or []]
    lines = [project["summary"]]
    if project.get("entries"):
        lines.append("Entry: " + ", ".join(project["entries"]) + ".")
    if decisions:
        lines.append("Decision points: " + ", ".join(decisions) + ".")
    if service_names:
        lines.append("Services on the map: " + _join(service_names) + ".")
    keys = project.get("stats", {}).get("env_keys") or []
    if keys:
        lines.append("Env key names: " + ", ".join(keys) + ". Values are not loaded.")
    cites = [_cite(rec, {project["id"]: project["name"]}) for rec in files if rec.get("entry")]
    if not cites:
        cites = [_cite(rec, {project["id"]: project["name"]}) for rec in files[:3]]
    return {"answer": "\n".join(lines), "citations": cites[:6], "provider": "heuristic"}


def _explain_project(project: dict, files: list[dict]) -> dict:
    names = {project["id"]: project["name"]}
    lines = [project["summary"]]
    interesting = sorted(files, key=lambda rec: (not rec.get("entry"), -rec["lines"]))[:4]
    if interesting:
        lines.append("Files worth opening:")
        for rec in interesting:
            lines.append(f"- {rec['rel']} — {rec['summary']}")
    return {
        "answer": "\n".join(lines),
        "citations": [_cite(rec, names) for rec in interesting],
        "provider": "heuristic",
    }


def _skill_answer(skill: dict, projects: list[dict]) -> dict:
    names = {p["id"]: p["name"] for p in projects}
    folders = [names[pid] for pid in skill["projects"] if pid in names]
    examples = []
    citations = []
    for item in skill["files"]:
        if item["project_id"] not in names:
            continue
        label = f"{names[item['project_id']]}/{item['rel']}"
        examples.append(label)
        citations.append(
            {
                "id": item["file_id"],
                "label": label,
                "kind": "file",
                "project_id": item["project_id"],
            }
        )
        if len(examples) >= 5:
            break
    folder_text = _join(folders) if folders else "no focused folder"
    example_text = ", ".join(examples) if examples else "the scan"
    return {
        "answer": (
            f"{skill['name']} ({skill['category']}): {skill['blurb']} "
            f"It shows up in {folder_text}. Examples: {example_text}."
        ),
        "citations": citations,
        "provider": "heuristic",
    }


def _overlap(question: str, projects: list[dict], files: list[dict]) -> dict:
    q = _tokens(question)
    if not projects:
        return {
            "answer": "This folder does not contain any scannable projects yet.",
            "citations": [],
            "provider": "heuristic",
        }
    ranked_p = sorted(projects, key=lambda p: _score(q, p["name"] + " " + p["summary"]), reverse=True)
    ranked_f = sorted(files, key=lambda rec: _score(q, rec["rel"] + " " + rec["summary"] + " " + (rec.get("excerpt") or "")), reverse=True)
    best = ranked_p[0]
    top_files = [rec for rec in ranked_f if _score(q, rec["rel"] + rec["summary"]) > 0][:3]
    if not top_files:
        top_files = ranked_f[:2]
    lines = [best["summary"]]
    if top_files:
        lines.append("Closest files:")
        for rec in top_files:
            lines.append(f"- {best['name'] if rec['project_id']==best['id'] else rec['project_id']}/{rec['rel']} — {rec['summary']}")
    names = {p["id"]: p["name"] for p in projects}
    return {
        "answer": "\n".join(lines),
        "citations": [_cite(rec, names) for rec in top_files],
        "provider": "heuristic",
    }


def _match_service(question: str, connections: list[dict]) -> dict | None:
    for conn in connections:
        if conn["name"].lower() in question or conn["id"] in question:
            return conn
    for service in SERVICES:
        if service.name.lower() in question:
            return next(c for c in connections if c["id"] == service.id)
    return None


def _match_skill(question: str, skills: list[dict]) -> dict | None:
    for skill in skills:
        if skill["name"].lower() in question or skill["id"].replace("-", " ") in question:
            return skill
    return None


def _named_projects(question: str, projects: list[dict]) -> list[dict]:
    hits = []
    for project in projects:
        if project["name"].lower() in question or project["id"] in question:
            hits.append(project)
    return hits


def _keyin_phrase(question: str, brain: dict) -> bool:
    q = question.casefold()
    for row in index_for_ask(brain):
        phrase = (row.get("keyin") or "").casefold()
        if phrase and phrase in q:
            return True
    return False


def _keyin_answer(brain: dict, question: str, projects: list[dict]) -> dict | None:
    allowed = {project["id"] for project in projects}
    rows = [row for row in index_for_ask(brain) if row["project_id"] in allowed]
    if not rows:
        return None
    q = question.casefold()
    mentions = re.search(r"key[\s-]?ins?\b", q) is not None
    hits = []
    for row in rows:
        phrase = (row.get("keyin") or "").casefold()
        if phrase and phrase in q:
            hits.append(row)
            continue
        if not mentions:
            continue
        for word in re.findall(r"[A-Za-z0-9]{4,}", row.get("keyin") or ""):
            if re.search(rf"\b{re.escape(word.casefold())}\b", q):
                hits.append(row)
                break
    if not hits and mentions:
        hits = rows[:12]
    if not hits:
        return None
    lines = []
    citations = []
    for row in hits[:8]:
        if row.get("found") and row.get("rel"):
            target = f"{row['rel']}:{row['function']}"
        elif row.get("function"):
            target = f"{row['function']} was not found"
        else:
            target = "no handler"
        lines.append(f"{row['keyin']} is in {row['project_name']} and calls {target}.")
        if row.get("file_id"):
            citations.append(
                {
                    "id": row["file_id"],
                    "label": f"{row['project_name']}/{row['rel'] or row['keyin']}",
                    "kind": "file",
                    "project_id": row["project_id"],
                }
            )
        elif row.get("xml_id"):
            citations.append(
                {
                    "id": row["xml_id"],
                    "label": f"{row['project_name']}/{row['xml']}",
                    "kind": "file",
                    "project_id": row["project_id"],
                }
            )
    return {"answer": "\n".join(lines), "citations": _unique_cites(citations)[:6], "provider": "heuristic"}


def _cite(rec: dict, names: dict[str, str]) -> dict:
    project = names.get(rec["project_id"], rec["project_id"])
    return {
        "id": rec["id"],
        "label": f"{project}/{rec['rel']}",
        "kind": "file",
        "project_id": rec["project_id"],
    }


def _unique_cites(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        out.append(item)
    return out


def _tokens(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", text.lower()) if tok not in _STOP}


def _score(q: set[str], text: str) -> int:
    if not q:
        return 0
    return len(q & _tokens(text))


def _pack(projects: list[dict], files: list[dict], question: str) -> str:
    q = _tokens(question)
    ranked = sorted(
        files,
        key=lambda rec: _score(q, rec["rel"] + " " + rec["summary"] + " " + (rec.get("excerpt") or "")),
        reverse=True,
    )
    chosen = ranked[:8]
    parts = []
    for project in projects[:6]:
        keys = ", ".join(project.get("stats", {}).get("env_keys") or []) or "none"
        block = f"# Folder {project['name']} ({project['id']})\n{project['summary']}\nEnv key names: {keys}"
        report = project.get("microstation") or None
        if report and report.get("keyins"):
            lines = []
            for item in report["keyins"][:12]:
                target = f"{item.get('rel') or 'missing'}:{item.get('function') or 'missing'}"
                lines.append(f"{item.get('keyin')} -> {target}")
            block += "\nKey-ins:\n" + "\n".join(lines)
        parts.append(block)
    for rec in chosen:
        if rec["kind"] == "env":
            parts.append(f"## {rec['project_id']}/{rec['rel']}\nKey names only: {', '.join(rec.get('env_keys') or [])}")
        else:
            parts.append(f"## {rec['project_id']}/{rec['rel']}\n{rec['summary']}\n{(rec.get('excerpt') or '')[:900]}")
    return redact("\n\n".join(parts))[:14000]


def _service_name(sid: str) -> str:
    for service in SERVICES:
        if service.id == sid:
            return service.name
    return sid


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]
