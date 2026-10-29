"""MicroStation Python key-ins and the pitfalls from Bentley's Python guide.

Detection is local. It reads already-scanned .py files and *.commands.xml
tables. It does not read .env values and it does not call a model.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from backend.app.redact import redact

XML_CAP = 256_000
_MSPY_RE = re.compile(r"(?i)\bMSPy[A-Za-z0-9_]*")
_COMMANDS_SUFFIX = ".commands.xml"
_HANDLER_TAG_RE = re.compile(r"<KeyinHandler\b([^>]*)/?>", re.I)
_ATTR_RE = re.compile(r"""([A-Za-z_:][\w:.-]*)\s*=\s*["']([^"']*)["']""")
_DTD_RE = re.compile(r"<!DOCTYPE|<!ENTITY", re.I)

# Names that are stdlib on Windows even when this process is running elsewhere.
_EXTRA_STDLIB = {
    "msvcrt",
    "winreg",
    "nt",
    "posix",
    "pwd",
    "grp",
    "fcntl",
    "resource",
    "syslog",
    "_thread",
    "builtins",
    "parser",
}


def parse_commands_xml(text: str) -> dict:
    """Return key-ins from a commands.xml table. Malformed XML does not raise."""
    raw = text or ""
    truncated = len(raw) > XML_CAP
    raw = raw[:XML_CAP]
    if raw.startswith("\ufeff"):
        raw = raw.lstrip("\ufeff")
    if _DTD_RE.search(raw):
        return {"keyins": [], "error": "DTD skipped", "truncated": truncated}
    handlers = _salvage_handlers(raw)
    tree: list[str] = []
    error = ""
    try:
        root = _xml_root(raw)
    except Exception:
        error = "malformed"
        root = None
    if root is not None:
        try:
            handlers = _merge_handlers(handlers, _handler_elements(root))
            tree = _keyword_paths(root)
        except Exception:
            error = error or "malformed"
    keyins = _combine(handlers, tree)
    return {"keyins": keyins, "error": error, "truncated": truncated}


def attach_microstation(root: Path, projects: list[dict], files: list[dict]) -> dict:
    """Stamp each project with a microstation report, or None."""
    report = build_microstation(root, projects, files)
    by_id = {item["project_id"]: item for item in report["projects"]}
    for project in projects:
        project["microstation"] = by_id.get(project["id"])
    return report


def build_microstation(root: Path, projects: list[dict], files: list[dict]) -> dict:
    root = Path(root)
    grouped: dict[str, list[dict]] = {}
    for rec in files:
        grouped.setdefault(rec.get("project_id") or "", []).append(rec)
    detected = []
    for project in projects:
        group = grouped.get(project["id"], [])
        if _is_microstation(group):
            detected.append((project, group))
    duplicates = _duplicate_names(detected)
    rows = []
    for project, group in detected:
        rows.append(_one(root, project, group, duplicates))
    return {"projects": rows}


def graph_extras(project: dict, chosen_ids: set[str]) -> tuple[list[dict], list[dict]]:
    """Key-in nodes and the handler functions they call."""
    report = project.get("microstation") or None
    if not report:
        return [], []
    nodes: list[dict] = []
    edges: list[dict] = []
    root_id = f"n:{project['id']}:root"
    seen_fn: set[str] = set()
    for index, item in enumerate((report.get("keyins") or [])[:24]):
        slug = re.sub(r"[^a-z0-9]+", "-", (item.get("keyin") or "keyin").lower()).strip("-") or "keyin"
        kid = f"n:{project['id']}:keyin:{slug}:{index}"
        if item.get("found") and item.get("rel") and item.get("function"):
            sub = f"{item['rel']}:{item['function']}"
        elif item.get("function"):
            sub = "handler not found"
        else:
            sub = "no handler"
        nodes.append(
            {
                "id": kid,
                "label": item.get("keyin") or "key-in",
                "sub": sub,
                "kind": "keyin",
                "project_id": project["id"],
                "file_id": item.get("file_id"),
                "service_id": None,
            }
        )
        edges.append({"id": f"e:{kid}:root", "source": root_id, "target": kid, "label": "key-in"})
        if not (item.get("found") and item.get("function")):
            continue
        fid = f"n:{project['id']}:fn:{item.get('file_id') or slug}:{item['function']}"
        if fid not in seen_fn:
            seen_fn.add(fid)
            nodes.append(
                {
                    "id": fid,
                    "label": item["function"],
                    "sub": item.get("rel") or "function",
                    "kind": "function",
                    "project_id": project["id"],
                    "file_id": item.get("file_id"),
                    "service_id": None,
                }
            )
            file_node = f"n:{item['file_id']}" if item.get("file_id") else ""
            if file_node and item.get("file_id") in chosen_ids:
                edges.append({"id": f"e:{fid}:file", "source": fid, "target": file_node, "label": "in"})
        edges.append({"id": f"e:{kid}:{fid}", "source": kid, "target": fid, "label": "calls"})
    return nodes, edges


def index_for_ask(brain: dict) -> list[dict]:
    rows = []
    for project in brain.get("projects") or []:
        report = project.get("microstation") or None
        if not report:
            continue
        for item in report.get("keyins") or []:
            rows.append(
                {
                    "project_id": project["id"],
                    "project_name": project.get("name") or project["id"],
                    "keyin": item.get("keyin") or "",
                    "rel": item.get("rel") or "",
                    "function": item.get("function") or "",
                    "found": bool(item.get("found")),
                    "file_id": item.get("file_id"),
                    "xml": item.get("xml") or "",
                    "xml_id": item.get("xml_id"),
                }
            )
    return rows


def _one(root: Path, project: dict, files: list[dict], duplicates: dict[str, list[dict]]) -> dict:
    py = [rec for rec in files if rec.get("kind") == "python"]
    tables = [rec for rec in files if _is_commands_name(rec.get("name") or "")]
    local_stems = {_stem(rec) for rec in py}
    third_party = _third_party(py, local_stems)
    keyins = []
    for rec in tables:
        text = _read_table(root, project, rec)
        parsed = parse_commands_xml(text)
        for item in parsed["keyins"]:
            resolved = _resolve(item, py)
            keyins.append(
                {
                    "keyin": redact(item["keyin"]),
                    "handler": redact(item.get("handler") or ""),
                    "module": item.get("module") or "",
                    "function": item.get("function") or "",
                    "xml": rec.get("rel") or "",
                    "xml_id": rec.get("id"),
                    "found": resolved["found"],
                    "rel": resolved["rel"],
                    "file_id": resolved["file_id"],
                    "source": item.get("source") or "handler",
                }
            )
    pitfalls = _pitfalls(project, py, tables, keyins, third_party, duplicates)
    return {
        "project_id": project["id"],
        "name": project.get("name") or project["id"],
        "keyins": keyins,
        "commands": [rec.get("rel") or "" for rec in tables],
        "scripts": [rec.get("rel") or "" for rec in py],
        "third_party": third_party,
        "pitfalls": pitfalls,
    }


def _is_microstation(files: list[dict]) -> bool:
    for rec in files:
        if _is_commands_name(rec.get("name") or ""):
            return True
        if rec.get("kind") != "python":
            continue
        for name in rec.get("imports_top") or []:
            if str(name).lower().startswith("mspy"):
                return True
        blob = f"{rec.get('excerpt') or ''}\n{rec.get('summary') or ''}"
        if _MSPY_RE.search(blob):
            return True
    return False


def _is_commands_name(name: str) -> bool:
    return name.lower().endswith(_COMMANDS_SUFFIX)


def _duplicate_names(detected: list[tuple[dict, list[dict]]]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for project, files in detected:
        for rec in files:
            if rec.get("kind") != "python":
                continue
            base = (rec.get("name") or "").casefold()
            if not base:
                continue
            grouped.setdefault(base, []).append(
                {
                    "project_id": project["id"],
                    "name": project.get("name") or project["id"],
                    "rel": rec.get("rel") or rec.get("name") or "",
                    "file": rec.get("name") or "",
                }
            )
    return {base: rows for base, rows in grouped.items() if len(rows) > 1}


def _third_party(py_files: list[dict], local_stems: set[str]) -> list[str]:
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | _EXTRA_STDLIB
    local = {stem.casefold() for stem in local_stems if stem}
    found: list[str] = []
    for rec in py_files:
        for name in rec.get("imports_top") or []:
            top = str(name).split(".")[0].strip()
            if not top or top.startswith("_"):
                continue
            folded = top.casefold()
            if folded.startswith("mspy") or folded in local or top in stdlib or folded in stdlib:
                continue
            if top not in found:
                found.append(top)
    return found


def _pitfalls(
    project: dict,
    py_files: list[dict],
    tables: list[dict],
    keyins: list[dict],
    third_party: list[str],
    duplicates: dict[str, list[dict]],
) -> list[dict]:
    name = project.get("name") or project["id"]
    pitfalls = []
    seen_bases: set[str] = set()
    for rec in py_files:
        base = (rec.get("name") or "").casefold()
        rows = duplicates.get(base) or []
        if not rows or base in seen_bases:
            continue
        seen_bases.add(base)
        paths = [f"{row['name']}/{row['rel']}" for row in rows]
        shown = ", ".join(paths[:4])
        file_name = rows[0]["file"]
        pitfalls.append(
            {
                "id": "duplicate-filename",
                "severity": "red",
                "title": f"Duplicate {file_name}",
                "detail": f"{file_name} is loaded more than once ({shown}). Bentley says that breaks key-ins.",
                "prompt": redact(
                    f"In the MicroStation Python projects, the script filename {file_name} is not unique ({shown}). "
                    "Bentley's guide says the Python filename has to be unique across every script loaded into "
                    "MicroStation or the key-ins stop working. Rename the copies so each basename is unique, and "
                    "update any KeyinHandler Function module that pointed at the old name. Do not read .env values."
                ),
            }
        )
    missing = [item for item in keyins if item.get("handler") and not item.get("found")]
    tree_only = [item for item in keyins if not item.get("handler")]
    if missing or tree_only:
        bits = []
        for item in (missing + tree_only)[:4]:
            target = item.get("handler") or "no KeyinHandler"
            bits.append(f"{item['keyin']} ({target})")
        pitfalls.append(
            {
                "id": "missing-handler",
                "severity": "red",
                "title": "Handler missing",
                "detail": "No Python function was found for " + "; ".join(bits) + ".",
                "prompt": redact(
                    "These MicroStation key-ins in "
                    + name
                    + " do not resolve to a function: "
                    + "; ".join(bits)
                    + ". Add a no-argument def whose name matches the KeyinHandler Function attribute "
                    "(read any extra arguments from sys.argv). Point Function at module.function where module is the .py filename. "
                    "Do not read .env values."
                ),
            }
        )
    if third_party:
        listed = ", ".join(third_party[:8])
        pitfalls.append(
            {
                "id": "third-party",
                "severity": "amber",
                "title": "Needs MS_PYTHON",
                "detail": f"{listed} is not shipped with MicroStation. Point MS_PYTHON at a matching Python install.",
                "prompt": redact(
                    f"The MicroStation Python project {name} imports {listed}. "
                    "Those are not part of the Python that ships with MicroStation. "
                    "Install the same Python version MicroStation was built against, pip install "
                    f"{listed} there, and set the MS_PYTHON configuration variable to that install's root. "
                    "Do not point MS_PYTHON at a virtualenv, and do not read .env values."
                ),
            }
        )
    stems = {_stem(rec).casefold() for rec in py_files}
    for rec in tables:
        rel = rec.get("rel") or ""
        stem = _commands_stem(rec.get("name") or "").casefold()
        file_modules = {
            (item.get("module") or "").casefold()
            for item in keyins
            if item.get("xml") == rel and item.get("module")
        }
        if (stem and stem in stems) or bool(file_modules & stems):
            continue
        rel = rec.get("rel") or rec.get("name") or "commands.xml"
        pitfalls.append(
            {
                "id": "orphan-commands",
                "severity": "amber",
                "title": "commands.xml without a script",
                "detail": f"{rel} has no matching .py to load the key-in table.",
                "prompt": redact(
                    f"{rel} in {name} is a MicroStation commands.xml table, but no Python file next to it loads it. "
                    "Add a uniquely named .py that calls PythonKeyinManager.GetManager().LoadCommandTableFromXml "
                    f"with this file, and point each KeyinHandler at a function in that module. Do not read .env values."
                ),
            }
        )
    return pitfalls


def _resolve(item: dict, py_files: list[dict]) -> dict:
    function = item.get("function") or ""
    module = (item.get("module") or "").casefold()
    if not function:
        return {"found": False, "rel": "", "file_id": None}
    matches = []
    for rec in py_files:
        names = {sym.get("name") for sym in rec.get("symbols") or [] if sym.get("kind") != "class"}
        if function not in names:
            continue
        matches.append(rec)
    if module:
        scoped = [rec for rec in matches if _stem(rec).casefold() == module]
        if scoped:
            matches = scoped
        else:
            return {"found": False, "rel": "", "file_id": None}
    if not matches:
        return {"found": False, "rel": "", "file_id": None}
    matches.sort(key=lambda rec: (len(rec.get("rel") or ""), rec.get("rel") or ""))
    chosen = matches[0]
    return {"found": True, "rel": chosen.get("rel") or "", "file_id": chosen.get("id")}


def _read_table(root: Path, project: dict, rec: dict) -> str:
    rel = rec.get("rel") or ""
    project_rel = project.get("rel") or ""
    base = root if not project_rel or project_rel == "." else root / project_rel
    candidate = (base / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return rec.get("excerpt") or ""
    if not candidate.is_file() or candidate.suffix.lower() != ".xml":
        return rec.get("excerpt") or ""
    try:
        data = candidate.read_bytes()[: XML_CAP + 1]
    except OSError:
        return rec.get("excerpt") or ""
    return data.decode("utf-8-sig", errors="replace")


def _xml_root(text: str):
    parser_mod = _parser_module()
    if not text.strip():
        raise ValueError("empty")
    return parser_mod.fromstring(text)


def _parser_module():
    try:
        import defusedxml.ElementTree as defused

        return defused
    except ImportError:
        import xml.etree.ElementTree as element_tree

        return element_tree


def _local(tag: str) -> str:
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _attr(elem, name: str) -> str:
    want = name.lower()
    for key, value in elem.attrib.items():
        if _local(str(key)).lower() == want:
            return str(value).strip()
    return ""


def _handler_elements(root) -> list[dict]:
    found = []
    for elem in root.iter():
        if _local(elem.tag).lower() != "keyinhandler":
            continue
        keyin = _norm(_attr(elem, "Keyin"))
        function = _attr(elem, "Function")
        if keyin:
            found.append(_handler_row(keyin, function, "handler"))
    return found


def _keyword_paths(root) -> list[str]:
    found: list[str] = []

    def walk(elem, prefix: list[str]) -> bool:
        tag = _local(elem.tag)
        words = prefix
        if tag.lower() == "keyword":
            word = _attr(elem, "CommandWord") or _attr(elem, "SubString")
            if word:
                words = prefix + [word.strip()]
        child_hit = False
        for child in list(elem):
            if walk(child, words):
                child_hit = True
        if tag.lower() == "keyword" and words and not child_hit:
            found.append(_norm(" ".join(words)))
            return True
        return child_hit

    walk(root, [])
    return [item for item in found if item]


def _salvage_handlers(text: str) -> list[dict]:
    found = []
    for match in _HANDLER_TAG_RE.finditer(text):
        attrs = {key.split("}")[-1].lower(): value.strip() for key, value in _ATTR_RE.findall(match.group(1))}
        keyin = _norm(attrs.get("keyin", ""))
        if not keyin:
            continue
        found.append(_handler_row(keyin, attrs.get("function", ""), "handler"))
    return found


def _handler_row(keyin: str, function: str, source: str) -> dict:
    function = (function or "").strip()
    module = ""
    name = function
    if "." in function:
        module, name = function.split(".", 1)
        name = name.split(".")[-1] or name
    return {
        "keyin": keyin,
        "handler": function,
        "module": module,
        "function": name,
        "source": source,
    }


def _combine(handlers: list[dict], tree: list[str]) -> list[dict]:
    by_key: dict[str, dict] = {}
    ordered: list[dict] = []
    for item in handlers:
        key = item["keyin"].casefold()
        if not key or key in by_key:
            continue
        by_key[key] = item
        ordered.append(item)
    for phrase in tree:
        key = phrase.casefold()
        if not key or key in by_key:
            continue
        row = _handler_row(phrase, "", "tree")
        by_key[key] = row
        ordered.append(row)
    return ordered


def _merge_handlers(salvaged: list[dict], parsed: list[dict]) -> list[dict]:
    if parsed:
        return parsed
    return salvaged


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _stem(rec: dict) -> str:
    name = rec.get("name") or Path(rec.get("rel") or "").name
    return Path(name).stem


def _commands_stem(name: str) -> str:
    lower = name.lower()
    if lower.endswith(_COMMANDS_SUFFIX):
        return name[: -len(_COMMANDS_SUFFIX)]
    return Path(name).stem
