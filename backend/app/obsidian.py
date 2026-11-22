"""Preview and download a portable Markdown/JSON Canvas project package."""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from backend.app import knowledge
from backend.app.redact import redact


def _handle(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _label(value: str) -> str:
    return redact(re.sub(r"[\[\]\\\r\n]", " ", value))[:160]


def _bundle(root: Path, brain: dict, project: dict, export_id: str) -> tuple[dict, dict[str, str]]:
    if not re.fullmatch(r"[0-9a-f]{24}", export_id):
        raise ValueError("Invalid export preview")
    prefix = f"AI-Brain-{export_id}"
    graph = brain["architecture"]["projects"].get(project["id"], {"nodes": [], "edges": []})
    visible = {rec["id"] for rec in brain["files"] if rec["project_id"] == project["id"] and not rec.get("env_class")}
    nodes, edges = [], []
    ids = set()
    root_id = None
    evidence_file_nodes: dict[str, str] = {}
    for node in graph["nodes"]:
        if node["id"] in ids or not (node["kind"] in {"project", "service"} or node.get("file_id") in visible):
            continue
        ids.add(node["id"])
        if node["kind"] == "project":
            root_id = node["id"]
        if node.get("file_id") and node["kind"] != "decision":
            evidence_file_nodes[node["file_id"]] = node["id"]
        index = len(nodes)
        nodes.append({"id": node["id"], "type": "text", "x": (index % 5) * 340, "y": (index // 5) * 180,
                      "width": 300, "height": 140, "text": f"**{_label(node['label'])}**\n\n{_label(node.get('sub') or '')}"})
    seen_edges = set()
    for edge in graph["edges"]:
        if edge["id"] in seen_edges or edge["source"] not in ids or edge["target"] not in ids:
            continue
        seen_edges.add(edge["id"])
        label = _label(edge.get("label") or "")
        if edge["id"].startswith(("e:svc:", "e:svcroot:")):
            label = "Inferred service reference"
        edges.append({"id": edge["id"], "fromNode": edge["source"], "toNode": edge["target"],
                      "label": label or "Indexed relationship"})

    pages = [page for page in knowledge.pages(root, brain) if page["project_id"] == project["id"]]
    usable = [page for page in pages if not page["stale_sources"] and page["content"]][:40]
    by_title: dict[str, list[str]] = {}
    paths = {page["page_id"]: f"pages/page-{_handle(page['page_id'])}.md" for page in usable}
    for page in usable:
        by_title.setdefault(page["title"].casefold(), []).append(paths[page["page_id"]])
    unresolved = set()
    files = {}
    summary = [f"# {_label(project['name'])}", "", "Open `Project Map.canvas` in Obsidian for the project map.", "",
               "The map shows indexed relationships, not a complete dependency audit. Source files are not copied.", ""]
    for page in usable:
        path = paths[page["page_id"]]

        def link(match: re.Match) -> str:
            target, alias = match.group(1).strip(), match.group(2)
            matches = by_title.get(target.casefold(), [])
            if len(matches) != 1:
                unresolved.add(target)
                # Do not let an unresolved title accidentally bind to a different vault note.
                return f"{_label(alias or target)} (unresolved link)"
            return f"[{_label(alias or target)}]({Path(matches[0]).name})"

        # Preserve fenced code blocks as written; only relink wiki links in narrative text.
        blocks = re.split(r"(^```[^\n]*\n.*?^```[^\n]*$|^~~~[^\n]*\n.*?^~~~[^\n]*$)", page["content"], flags=re.M | re.S)
        body = "".join(block if i % 2 else re.sub(r"(?<!!)\[\[([^|#\]\n]+)(?:\|([^\]\n]+))?\]\]", link, block)
                       for i, block in enumerate(blocks))
        files[path] = body
        summary.append(f"- [{_label(page['title'])}]({path})")
        node_id = f"export-page-{_handle(page['page_id'])}"
        index = len(nodes)
        nodes.append({"id": node_id, "type": "file", "x": (index % 5) * 340, "y": (index // 5) * 180,
                     "width": 300, "height": 140, "file": f"{prefix}/{path}"})
        if root_id:
            edges.append({"id": f"export-edge-{_handle(node_id)}", "fromNode": root_id, "toNode": node_id, "label": "Reviewed page"})
        for source in page["sources"]:
            if file_node := evidence_file_nodes.get(source["id"]):
                edges.append({"id": f"export-citation-{_handle(node_id + file_node)}", "fromNode": node_id,
                              "toNode": file_node, "label": "Cites indexed source"})
    if len(usable) < len(pages):
        summary += ["", f"{len(pages) - len(usable)} page(s) omitted because they were stale, unreadable, or beyond the 40-page limit."]
    if unresolved:
        summary += ["", "## Unresolved or ambiguous note links", *[f"- {_label(item)}" for item in sorted(unresolved)]]
    files["Index.md"] = "\n".join(summary) + "\n"
    files["Project Map.canvas"] = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False, indent=2)
    digest = hashlib.sha256(json.dumps(files, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {"export_id": export_id, "folder": prefix, "paths": [f"{prefix}/{name}" for name in sorted(files)],
            "node_count": len(nodes), "edge_count": len(edges), "omitted_pages": len(pages) - len(usable),
            "unresolved_count": len(unresolved), "token": digest}, files


def preview(root: Path, brain: dict, project: dict) -> dict:
    result, _ = _bundle(root, brain, project, uuid4().hex[:24])
    return result


def archive(root: Path, brain: dict, project: dict, export_id: str, token: str) -> tuple[str, bytes]:
    details, files = _bundle(root, brain, project, export_id)
    if details["token"] != token:
        raise ValueError("The pages or project map changed; preview the export again")
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as zip_file:
        for name, content in files.items():
            zip_file.writestr(f"{details['folder']}/{name}", content)
    return details["folder"] + ".zip", output.getvalue()
