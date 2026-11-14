"""Read-only MicroStation configuration map.

Parses *.cfg, *.ucf, and legacy *.pcf files. Follows %include, %if/%ifdef/%else/%endif,
and %level, and applies =, :, >, <, and + assignments. Files are only opened for
reading. Nothing in this module writes a configuration file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.redact import redact

READ_CAP = 256_000
MAX_INCLUDES = 64
MAX_DEPTH = 24
KEY_VARS = (
    "MS_DEF",
    "MS_RFDIR",
    "MS_ADDINPATH",
    "_USTN_WORKSETROOT",
    "_USTN_WORKSPACEROOT",
    "MS_SEEDFILES",
    "MS_DGNLIBLIST",
)
_KEY_CANON = {name.casefold(): name for name in KEY_VARS}
_DIR_VARS = {name.casefold() for name in KEY_VARS if name != "MS_DGNLIBLIST"}
_LEVELS = {
    "system": "System",
    "application": "Application",
    "organization": "Organization",
    "workspace": "WorkSpace",
    "workset": "WorkSet",
    "role": "Role",
    "user": "User",
    "project": "WorkSet",
}
_RANK = {name: index for index, name in enumerate(
    ["System", "Application", "Organization", "WorkSpace", "WorkSet", "Role", "User"]
)}
_CONFIG_EXT = {".cfg", ".ucf", ".pcf"}
_FILE_EXT = {"dgn", "dgnlib", "dll", "ma", "cfg", "ucf", "pcf", "xml", "py", "cel", "rsc", "txt"}
_ASSIGN_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<op>=|:|>|<|\+)\s*(?P<value>.*)$")
_DIRECTIVE_RE = re.compile(r"^([A-Za-z]+)(.*)$", re.S)
_VAR_REF = re.compile(r"\$[\(\{]\s*([A-Za-z_][A-Za-z0-9_]*)\s*[\)\}]")
_IMM_REF = re.compile(r"\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}")
_LEVEL_SUFFIX = re.compile(r"(?i)\s+level\s+([A-Za-z]+)\s*$")
_USER_PATH = re.compile(r"(?i)[A-Za-z]:[/\\]+Users[/\\]")
_WIN_ABS = re.compile(r"^[A-Za-z]:[/\\]")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_WRITE_RE = re.compile(
    r"(?ix)os\.environ\s*\[\s*(?P<q>['\"])(?P<env>[A-Za-z_][A-Za-z0-9_]*)(?P=q)\s*\]\s*\+?="
    r"|(?:DefineVariable|SetVariable)\s*\(\s*(?P<q2>['\"])(?P<api>[A-Za-z_][A-Za-z0-9_]*)(?P=q2)"
)
_READ_RE = re.compile(
    r"(?ix)\$[\(\{]\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*[\)\}]"
    r"|os\.environ\.get\s*\(\s*(?P<q>['\"])(?P<get>[A-Za-z_][A-Za-z0-9_]*)(?P=q)"
    r"|os\.getenv\s*\(\s*(?P<q2>['\"])(?P<getenv>[A-Za-z_][A-Za-z0-9_]*)(?P=q2)"
    r"|os\.environ\s*\[\s*(?P<q3>['\"])(?P<idx>[A-Za-z_][A-Za-z0-9_]*)(?P=q3)\s*\]"
    r"|(?:GetVariable|DefineVariable|SetVariable)\s*\(\s*(?P<q4>['\"])(?P<api>[A-Za-z_][A-Za-z0-9_]*)(?P=q4)"
)
_TOKEN_RE = re.compile(
    r"\s+|(==|!=|<=|>=|<>|&&|\|\||[()!<>&|])|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*|."
)


@dataclass
class Slot:
    raw: str
    level: str
    file: str
    line: int
    operator: str


@dataclass
class Frame:
    parent_hot: bool
    hot: bool
    taken: bool
    saw_else: bool


@dataclass
class Source:
    rel: str
    path: Path
    text: str
    kind: str
    workspace: str
    set_name: str
    direct: bool
    ext: str
    level_hint: str = "WorkSet"


@dataclass
class ConfigState:
    scan_root: Path
    project_root: Path
    level: str = "WorkSet"
    slots: dict[str, dict[str, Slot]] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    locks: dict[str, tuple[str, int, str]] = field(default_factory=dict)
    faults: list[dict] = field(default_factory=list)
    frames: list[Frame] = field(default_factory=list)
    done: set[Path] = field(default_factory=set)
    stack: list[Path] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    includes: list[dict] = field(default_factory=list)
    current_rel: str = ""
    current_line: int = 0
    stop_file: bool = False
    _seen_faults: set[tuple] = field(default_factory=set)

    def active(self) -> bool:
        return all(frame.hot for frame in self.frames)

    def remember(self, name: str) -> str:
        key = name.casefold()
        if key not in self.names:
            self.names[key] = _KEY_CANON.get(key, name)
        return key

    def display(self, key: str) -> str:
        return self.names.get(key, key)

    def add_fault(self, fault: dict) -> None:
        if not self.active() and fault.get("id") not in {"missing-include", "unresolved-include"}:
            return
        key = (fault.get("id"), fault.get("variable"), fault.get("file"), fault.get("line"), fault.get("detail"))
        if key in self._seen_faults:
            return
        self._seen_faults.add(key)
        fault.setdefault("prompt", _prompt(fault))
        self.faults.append(fault)

    def effective(self, key: str) -> Slot | None:
        levels = self.slots.get(key) or {}
        best: Slot | None = None
        rank = -1
        for level, slot in levels.items():
            current = _RANK.get(level, -1)
            if current >= rank:
                rank = current
                best = slot
        return best

    def effective_raw(self, key: str) -> str | None:
        slot = self.effective(key)
        if slot is None:
            return None
        return slot.raw

    def defined(self, name: str) -> bool:
        return bool(self.slots.get(name.casefold()))

    def expand_all(self, text: str, stack: set[str] | None = None) -> str:
        seen = stack or set()

        def repl(match: re.Match[str]) -> str:
            key = match.group(1).casefold()
            if key in seen:
                return match.group(0)
            raw = self.effective_raw(key)
            if raw is None:
                return ""
            return self.expand_all(raw, seen | {key})

        return _VAR_REF.sub(repl, text or "")

    def expand_immediate(self, text: str) -> str:
        def repl(match: re.Match[str]) -> str:
            key = match.group(1).casefold()
            raw = self.effective_raw(key)
            if raw is None:
                return ""
            return self.expand_all(raw, {key})

        return _IMM_REF.sub(repl, text or "")

    def assign(self, name: str, op: str, value: str) -> None:
        if not self.active():
            return
        key = self.remember(name)
        baked = self.expand_immediate(value)
        defined = bool(self.slots.get(key))
        if op == ":":
            if defined:
                return
            if key in self.locks:
                self._locked(key, op, baked)
                return
            self._store(key, baked, op)
            return
        if key in self.locks:
            self._locked(key, op, baked)
            return
        existing = self.effective_raw(key) or ""
        if op == "=":
            raw = baked
        elif op == "+":
            raw = existing + baked
        elif op == ">":
            raw = _join(existing, baked, False)
        elif op == "<":
            raw = _join(existing, baked, True)
        else:
            return
        self._store(key, raw, op)

    def lock(self, name: str) -> None:
        if not self.active() or not name:
            return
        key = self.remember(name)
        if key in self.locks:
            return
        self.locks[key] = (self.current_rel, self.current_line, self.level)

    def undef(self, name: str) -> None:
        if not self.active() or not name:
            return
        key = self.remember(name)
        if key in self.locks:
            self._locked(key, "%undef", "")
            return
        self.slots.pop(key, None)

    def _store(self, key: str, raw: str, op: str) -> None:
        self.slots.setdefault(key, {})[self.level] = Slot(raw, self.level, self.current_rel, self.current_line, op)

    def _locked(self, key: str, op: str, value: str) -> None:
        lock_file, lock_line, lock_level = self.locks[key]
        name = self.display(key)
        self.add_fault(
            {
                "id": "locked-override",
                "severity": "red",
                "title": f"{name} is locked",
                "detail": (
                    f"{name} is locked at {lock_file}:{lock_line} ({lock_level}). "
                    f"{self.current_rel}:{self.current_line} tries to change it with {op}."
                ),
                "variable": name,
                "file": self.current_rel,
                "line": self.current_line,
                "lock_file": lock_file,
                "lock_line": lock_line,
                "attempt": value,
            }
        )


def evaluate_config(
    scan_root: Path,
    steps: list[tuple[Path, str]],
    project_root: Path | None = None,
) -> dict:
    """Interpret configuration files. Read-only: opens each file with a byte read."""
    scan_root = Path(scan_root).resolve()
    project_root = Path(project_root or scan_root).resolve()
    state = ConfigState(scan_root=scan_root, project_root=project_root)
    for path, level in steps:
        canon = _LEVELS.get((level or "").casefold(), "WorkSet")
        state.level = canon
        state.process_file(Path(path))
    return state.snapshot()


def attach_config(root: Path, projects: list[dict], files: list[dict]) -> dict:
    """Stamp each project with a microstation_config report, or None."""
    report = build_config(root, projects, files)
    by_id = {item["project_id"]: item for item in report["projects"]}
    for project in projects:
        project["microstation_config"] = by_id.get(project["id"])
    return report


def build_config(root: Path, projects: list[dict], files: list[dict]) -> dict:
    root = Path(root)
    grouped: dict[str, list[dict]] = {}
    for rec in files:
        grouped.setdefault(rec.get("project_id") or "", []).append(rec)
    rows = []
    for project in projects:
        item = _project_config(root, project, grouped.get(project["id"], []))
        if item and item["units"]:
            rows.append(_redact_obj(item))
    return {"projects": rows}


def process_file(self: ConfigState, path: Path) -> None:
    try:
        resolved = path.resolve()
    except OSError:
        return
    if resolved in self.stack:
        self.add_fault(_include_fault("unresolved", self.current_rel, self.current_line, resolved.name, "that file includes itself"))
        return
    if len(self.done) >= MAX_INCLUDES and resolved not in self.done:
        self.add_fault(_include_fault("unresolved", self.current_rel, self.current_line, resolved.name, "the include limit was reached"))
        return
    if not _under(resolved, self.scan_root) or not resolved.is_file():
        return
    rel = _display(resolved, self.project_root, self.scan_root)
    parent_rel = self.current_rel
    parent_line = self.current_line
    if parent_rel and parent_rel != rel:
        self.includes.append({"source": parent_rel, "target": rel, "line": parent_line})
    if resolved.suffix.lower() not in _CONFIG_EXT:
        self.add_fault(
            _include_fault("unresolved", parent_rel or rel, parent_line, rel, "only .cfg, .ucf, and .pcf files are read")
        )
        return
    if resolved in self.done:
        return
    self.done.add(resolved)
    self.stack.append(resolved)
    if rel not in self.files:
        self.files.append(rel)
    previous_rel = self.current_rel
    previous_stop = self.stop_file
    depth = len(self.frames)
    self.current_rel = rel
    self.stop_file = False
    try:
        text = _read_text(resolved)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if self.stop_file or len(self.stack) > MAX_DEPTH:
                break
            self.current_line = lineno
            self._handle_line(line)
    finally:
        del self.frames[depth:]
        self.stack.pop()
        self.current_rel = previous_rel
        self.stop_file = previous_stop


def _handle_line(self: ConfigState, line: str) -> None:
    stripped = _strip_comment(line).strip()
    if not stripped:
        return
    if stripped.startswith("%"):
        self._directive(stripped[1:].strip())
        return
    if not self.active():
        return
    match = _ASSIGN_RE.match(stripped)
    if not match:
        return
    self.assign(match.group("name"), match.group("op"), _unquote(match.group("value").strip()))


def _directive(self: ConfigState, body: str) -> None:
    match = _DIRECTIVE_RE.match(body)
    if not match:
        return
    word = match.group(1).casefold()
    rest = match.group(2).strip()
    if word in {"if", "ifdef", "ifndef", "elif", "else", "endif"}:
        self._flow(word, rest)
        return
    if not self.active():
        return
    if word == "include":
        self._include(rest)
    elif word == "level":
        token = rest.split()[0] if rest.split() else ""
        canon = _LEVELS.get(token.casefold())
        if canon:
            self.level = canon
    elif word == "lock":
        for name in self._names(rest):
            self.lock(name)
    elif word == "undef":
        for name in self._names(rest):
            self.undef(name)
    elif word == "error":
        self.add_fault(
            {
                "id": "config-error",
                "severity": "red",
                "title": "Configuration error",
                "detail": self.expand_all(rest)[:240] or "A configuration file raised %error.",
                "variable": "",
                "file": self.current_rel,
                "line": self.current_line,
            }
        )
        self.stop_file = True


def _flow(self: ConfigState, word: str, rest: str) -> None:
    if word == "if":
        cond = self._condition(rest) if self.active() else False
        parent = self.active()
        self.frames.append(Frame(parent, parent and cond, parent and cond, False))
        return
    if word == "ifdef":
        cond = self.defined(self._one_name(rest)) if self.active() else False
        parent = self.active()
        self.frames.append(Frame(parent, parent and cond, parent and cond, False))
        return
    if word == "ifndef":
        cond = (not self.defined(self._one_name(rest))) if self.active() else False
        parent = self.active()
        self.frames.append(Frame(parent, parent and cond, parent and cond, False))
        return
    if word == "endif":
        if self.frames:
            self.frames.pop()
        return
    if not self.frames:
        return
    frame = self.frames[-1]
    if word == "else":
        if frame.saw_else:
            frame.hot = False
            return
        frame.saw_else = True
        frame.hot = frame.parent_hot and not frame.taken
        if frame.hot:
            frame.taken = True
        return
    if word == "elif":
        if frame.saw_else or not frame.parent_hot or frame.taken:
            frame.hot = False
            return
        cond = self._condition(rest)
        frame.hot = cond
        if cond:
            frame.taken = True


def _include(self: ConfigState, rest: str) -> None:
    level_name = ""
    match = _LEVEL_SUFFIX.search(rest)
    if match:
        level_name = match.group(1)
        rest = rest[: match.start()].strip()
    spec = _unquote(rest.strip())
    expanded = self.expand_all(spec).strip()
    expanded = _unquote(expanded)
    paths, problem = self._resolve(expanded, spec)
    if problem:
        why = "the path is outside this scan" if problem == "unresolved" else "the file is not in the scanned folders"
        if not expanded or "$" in expanded:
            why = "the include path did not expand to a file"
        self.add_fault(_include_fault(problem, self.current_rel, self.current_line, spec or expanded, why))
        return
    # A level on %include, or a %level inside the included file, applies only
    # while that file is being read. The calling file keeps its own level.
    previous = self.level
    if level_name:
        canon = _LEVELS.get(level_name.casefold())
        if canon:
            self.level = canon
    try:
        for path in paths:
            self.process_file(path)
    finally:
        self.level = previous


def _resolve(self: ConfigState, expanded: str, original: str) -> tuple[list[Path], str]:
    if not expanded or "$" in expanded:
        return [], "unresolved"
    norm = expanded.replace("\\", "/")
    if "*" in norm or "?" in norm:
        if ".." in norm.split("/"):
            return [], "unresolved"
        matches = self._glob(norm)
        return (matches, "") if matches else ([], "unresolved")
    if _is_absolute(norm):
        candidate = Path(norm)
        if _under(candidate, self.scan_root) and candidate.is_file():
            return [candidate.resolve()], ""
        if _under(candidate, self.scan_root):
            return [], "missing"
        return [], "unresolved"
    bases = [self._current_dir(), self.project_root]
    if self.scan_root != self.project_root:
        bases.append(self.scan_root)
    inside_missing = False
    for base in bases:
        if base is None:
            continue
        try:
            resolved = (base / expanded).resolve()
        except OSError:
            continue
        if not _under(resolved, self.scan_root):
            continue
        if resolved.is_file():
            return [resolved], ""
        inside_missing = True
    if inside_missing:
        return [], "missing"
    if original:
        return [], "unresolved"
    return [], "unresolved"


def _glob(self: ConfigState, pattern: str) -> list[Path]:
    bases = [self._current_dir(), self.project_root]
    if self.scan_root != self.project_root:
        bases.append(self.scan_root)
    found: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        if base is None:
            continue
        try:
            matches = list(base.glob(pattern))
        except (OSError, ValueError):
            continue
        for candidate in matches:
            if len(found) >= 32:
                return found
            try:
                if not candidate.is_file() or candidate.suffix.lower() not in _CONFIG_EXT:
                    continue
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in seen or not _under(resolved, self.scan_root):
                continue
            seen.add(resolved)
            found.append(resolved)
    found.sort()
    return found


def _current_dir(self: ConfigState) -> Path | None:
    if not self.stack:
        return self.project_root
    return self.stack[-1].parent


def _names(self: ConfigState, rest: str) -> list[str]:
    expanded = self.expand_all(rest)
    return _NAME_RE.findall(expanded)


def _one_name(self: ConfigState, rest: str) -> str:
    names = self._names(rest)
    return names[0] if names else ""


def _condition(self: ConfigState, rest: str) -> bool:
    prepared = _prepare_expr(rest, self)
    try:
        value, index = _parse_or(_tokenize(prepared), 0, self)
    except ValueError:
        return False
    if index != len(_tokenize(prepared)):
        return False
    return _truthy(value)


def _assignments(state: ConfigState, key: str) -> list[dict]:
    rows = []
    for level, slot in sorted((state.slots.get(key) or {}).items(), key=lambda item: _RANK.get(item[0], 0)):
        rows.append(
            {
                "level": level,
                "value": state.expand_all(slot.raw) if slot.raw else "",
                "file": slot.file,
                "line": slot.line,
                "operator": slot.operator,
            }
        )
    return rows


def snapshot(self: ConfigState) -> dict:
    variables = []
    keys = set(self.slots) | set(self.locks)
    for key in keys:
        slot = self.effective(key)
        lock = self.locks.get(key)
        raw = slot.raw if slot else ""
        value = self.expand_all(raw) if raw else ""
        variables.append(
            {
                "name": self.display(key),
                "value": value,
                "level": slot.level if slot else (lock[2] if lock else ""),
                "file": slot.file if slot else (lock[0] if lock else ""),
                "line": slot.line if slot else (lock[1] if lock else None),
                "locked": lock is not None,
                "lock_file": lock[0] if lock else "",
                "lock_line": lock[1] if lock else None,
                "operator": slot.operator if slot else ("lock" if lock else ""),
                "references": [],
                "assignments": _assignments(self, key),
            }
        )
    variables.sort(key=lambda item: item["name"])
    _folder_faults(self, variables)
    self.faults.sort(key=lambda item: (str(item.get("file") or ""), item.get("line") or 0, item.get("id") or ""))
    return {
        "variables": variables,
        "faults": list(self.faults),
        "files": list(self.files),
        "includes": list(self.includes),
    }


def _folder_faults(state: ConfigState, variables: list[dict]) -> None:
    for var in variables:
        name = var["name"]
        value = var["value"] or ""
        if not value:
            continue
        if _USER_PATH.search(value):
            state.add_fault(
                {
                    "id": "hard-coded-user",
                    "severity": "amber",
                    "title": f"{name} uses a user folder",
                    "detail": f"{name} is {value}, a hard-coded C:/Users path. It will not travel to another PC.",
                    "variable": name,
                    "file": var["file"],
                    "line": var["line"],
                }
            )
        if name.casefold() not in _DIR_VARS:
            continue
        missing = [part for part in _components(value) if _needs_slash(part)]
        if missing:
            shown = ", ".join(missing[:3])
            state.add_fault(
                {
                    "id": "missing-slash",
                    "severity": "amber",
                    "title": f"{name} is missing a trailing /",
                    "detail": f"{name} is a folder and {shown} does not end with /.",
                    "variable": name,
                    "file": var["file"],
                    "line": var["line"],
                }
            )


def _project_config(root: Path, project: dict, file_recs: list[dict]) -> dict | None:
    project_root = _project_root(root, project)
    sources = _sources(root, project, file_recs)
    if not sources:
        return None
    plans, loose = _plans(sources)
    if not plans and not loose:
        return None
    id_by_rel = {rec.get("rel") or "": rec.get("id") for rec in file_recs}
    mentions = _mentions(root, project, file_recs)
    units = []
    seen_rels: set[str] = set()

    def _one(plan: dict) -> None:
        evaluated = evaluate_config(root, plan["steps"], project_root)
        seen_rels.update(evaluated["files"])
        if plan["kind"] == "pcf":
            evaluated["faults"].append(_pcf_fault(plan, evaluated["variables"]))
        unit = _present(project, plan, evaluated, id_by_rel)
        _attach_mentions(unit, mentions, id_by_rel)
        units.append(unit)

    for plan in plans:
        _one(plan)
    for item in loose:
        if item.rel in seen_rels or item.ext not in {".cfg", ".pcf"}:
            continue
        _one(
            {
                "kind": "config",
                "name": _literal(item.text, "_USTN_WORKSETNAME") or Path(item.rel).stem,
                "workspace": "",
                "entry": item,
                "steps": [(item.path, item.level_hint)],
            }
        )
    units.sort(key=lambda item: ({"workspace": 0, "workset": 1, "pcf": 2, "config": 3, "user": 4}.get(item["kind"], 9), item["name"]))
    graph = build_config_graph(project["id"], project.get("name") or project["id"], units, id_by_rel)
    return {
        "project_id": project["id"],
        "name": project.get("name") or project["id"],
        "units": units,
        "graph": graph,
    }


_BADGE = {
    "missing-slash": "no /",
    "hard-coded-user": "C:/Users",
    "locked-override": "locked",
    "missing-include": "include",
    "unresolved-include": "include",
    "pcf-upgrade": ".pcf",
}


def _graph_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").casefold()).strip("-") or "item"


def _fault_mark(faults: list[dict]) -> tuple[str, str]:
    if any(item.get("severity") == "red" for item in faults):
        severity = "red"
    elif faults:
        severity = "amber"
    else:
        return "", ""
    ranked = sorted(faults, key=lambda item: (0 if item.get("severity") == "red" else 1, item.get("id") or ""))
    return severity, _BADGE.get(ranked[0].get("id") or "", "fault")


def _node(node_id: str, label: str, sub: str, kind: str, project_id: str, file_id: str | None, faults: list[dict]) -> dict:
    severity, badge = _fault_mark(faults)
    return {
        "id": node_id,
        "label": label,
        "sub": sub[:160],
        "kind": kind,
        "project_id": project_id,
        "file_id": file_id,
        "service_id": None,
        "severity": severity,
        "badge": badge,
    }


def _edge(source: str, target: str, label: str) -> dict:
    return {"id": f"e:{source}:{target}:{label or 'link'}", "source": source, "target": target, "label": label}


def build_config_graph(project_id: str, project_name: str, units: list[dict], id_by_rel: dict[str, str | None]) -> dict:
    """Node graph for one project's WorkSpaces, WorkSets, files, and variables."""
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    def add(node: dict) -> None:
        if node["id"] in seen:
            return
        seen.add(node["id"])
        nodes.append(node)

    project_node = f"cfg:{project_id}:project"
    add(_node(project_node, project_name, "project folder", "project", project_id, None, []))
    file_of: dict[str, str] = {}
    for unit in units:
        for rel in unit.get("files") or []:
            if not rel or rel in file_of:
                continue
            faults = [item for item in unit.get("faults") or [] if item.get("file") == rel]
            node_id = f"cfg:{project_id}:file:{_graph_slug(rel)}"
            file_of[rel] = node_id
            add(_node(node_id, Path(rel).name, rel, "cfg", project_id, id_by_rel.get(rel), faults))
    for unit in units:
        for include in unit.get("includes") or []:
            source = file_of.get(include.get("source") or "")
            target = file_of.get(include.get("target") or "")
            if source and target:
                edges.append(_edge(source, target, "includes"))
    unit_of: dict[tuple[str, str], str] = {}
    for unit in units:
        kind = unit.get("kind") or "config"
        node_id = f"cfg:{project_id}:{kind}:{_graph_slug(unit.get('name') or '')}"
        unit_of[(kind, (unit.get("name") or "").casefold())] = node_id
        label = unit.get("name") or kind
        sub = {"workspace": "WorkSpace", "workset": "WorkSet", "pcf": "Legacy .pcf", "user": "User"}.get(kind, "Config")
        if unit.get("workspace") and kind == "workset":
            sub = f"WorkSet · {unit['workspace']}"
        add(_node(node_id, label, sub, kind if kind != "config" else "cfg", project_id, unit.get("file_id"), unit.get("faults") or []))
        if kind in {"workset", "pcf", "config", "user"}:
            edges.append(_edge(node_id, project_node, "in"))
        entry = file_of.get(unit.get("file") or "")
        if entry:
            edges.append(_edge(node_id, entry, "file"))
    for unit in units:
        if unit.get("kind") != "workset":
            continue
        parent = unit_of.get(("workspace", (unit.get("workspace") or "").casefold()))
        child = unit_of.get(("workset", (unit.get("name") or "").casefold()))
        if parent and child:
            edges.append(_edge(parent, child, "workset"))
    for unit in units:
        unit_id = unit_of.get((unit.get("kind") or "config", (unit.get("name") or "").casefold()))
        for var in unit.get("variables") or []:
            faults = [item for item in unit.get("faults") or [] if item.get("variable") == var.get("name")]
            if not var.get("value") and not var.get("locked") and not faults:
                continue
            node_id = f"cfg:{project_id}:{_graph_slug(unit.get('name') or '')}:var:{var.get('name')}"
            level = var.get("level") or "unset"
            value = var.get("value") or "not set"
            add(_node(node_id, var.get("name") or "variable", f"{level} · {value}", "variable", project_id, var.get("file_id"), faults))
            if unit_id:
                edges.append(_edge(unit_id, node_id, "sets"))
            defining = file_of.get(var.get("file") or "")
            if defining:
                edges.append(_edge(node_id, defining, "defined in"))
            for older in var.get("assignments") or []:
                if not older.get("file") or older.get("file") == var.get("file"):
                    continue
                winner = file_of.get(var.get("file") or "")
                previous = file_of.get(older.get("file") or "")
                if winner and previous:
                    edges.append(_edge(winner, previous, "overrides"))
            for fault in faults:
                if fault.get("id") != "locked-override":
                    continue
                other = fault.get("file") or ""
                if not other or other == var.get("file"):
                    continue
                source = file_of.get(other)
                if source is None:
                    source = f"cfg:{project_id}:ref:{_graph_slug(other)}"
                    add(_node(source, Path(other).name, other, "script", project_id, fault.get("file_id"), [fault]))
                if defining:
                    edges.append(_edge(source, defining, "blocked"))
                elif node_id:
                    edges.append(_edge(source, node_id, "blocked"))
    return {"nodes": nodes, "edges": _dedupe_graph(edges)}


def brain_graph_extras(project: dict, chosen_ids: set[str]) -> tuple[list[dict], list[dict]]:
    """WorkSet, WorkSpace, and variable nodes for the project blueprint."""
    report = project.get("microstation_config") or None
    if not report:
        return [], []
    nodes: list[dict] = []
    edges: list[dict] = []
    root_id = f"n:{project['id']}:root"
    seen: set[str] = set()

    def add(node: dict) -> None:
        if node["id"] in seen:
            return
        seen.add(node["id"])
        nodes.append(node)

    file_node = {rel: f"n:{file_id}" for rel, file_id in _rel_ids(report).items() if file_id and file_id in chosen_ids}
    for unit in report.get("units") or []:
        if unit.get("kind") not in {"workspace", "workset", "pcf"}:
            continue
        node_id = f"n:{project['id']}:cfg:{unit['kind']}:{_graph_slug(unit.get('name') or '')}"
        sub = {"workspace": "WorkSpace", "workset": "WorkSet", "pcf": "Legacy .pcf"}.get(unit["kind"], "Config")
        faults = unit.get("faults") or []
        if faults:
            sub = f"{sub} · {len(faults)} fault{'s' if len(faults) != 1 else ''}"
        add(_node(node_id, unit.get("name") or sub, sub, unit["kind"], project["id"], unit.get("file_id"), faults))
        edges.append(_edge(root_id, node_id, unit["kind"]))
        if unit.get("kind") == "workset":
            parent = f"n:{project['id']}:cfg:workspace:{_graph_slug(unit.get('workspace') or '')}"
            if parent in seen:
                edges.append(_edge(parent, node_id, "workset"))
        entry = file_node.get(unit.get("file") or "")
        if entry:
            edges.append(_edge(node_id, entry, "file"))
        linked = 0
        for var in unit.get("variables") or []:
            if linked >= 7:
                break
            if var.get("name") not in KEY_VARS:
                continue
            if not var.get("value") and not var.get("locked"):
                continue
            var_id = f"{node_id}:var:{var['name']}"
            faults = [item for item in unit.get("faults") or [] if item.get("variable") == var.get("name")]
            add(
                _node(
                    var_id,
                    var["name"],
                    f"{var.get('level') or 'unset'} · {var.get('value') or 'not set'}"[:160],
                    "variable",
                    project["id"],
                    var.get("file_id"),
                    faults,
                )
            )
            edges.append(_edge(node_id, var_id, "sets"))
            defining = file_node.get(var.get("file") or "")
            if defining:
                edges.append(_edge(var_id, defining, "defined in"))
            for ref in (var.get("references") or [])[:4]:
                file_id = ref.get("file_id")
                if file_id and file_id in chosen_ids:
                    edges.append(_edge(var_id, f"n:{file_id}", ref.get("how") or "reads"))
            linked += 1
    return nodes, edges


def corpus_config_links(projects: list[dict]) -> tuple[list[dict], list[dict]]:
    """WorkSet nodes on the corpus graph, plus path edges to other project folders."""
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()
    for project in projects:
        report = project.get("microstation_config") or None
        if not report:
            continue
        for unit in report.get("units") or []:
            if unit.get("kind") not in {"workspace", "workset", "pcf"}:
                continue
            node_id = f"c:{project['id']}:cfg:{unit['kind']}:{_graph_slug(unit.get('name') or '')}"
            if node_id in seen:
                continue
            seen.add(node_id)
            faults = unit.get("faults") or []
            sub = {"workspace": "WorkSpace", "workset": "WorkSet", "pcf": "Legacy .pcf"}.get(unit["kind"], "Config")
            nodes.append(_node(node_id, unit.get("name") or sub, sub, unit["kind"], project["id"], unit.get("file_id"), faults))
            edges.append(_edge(f"c:{project['id']}", node_id, unit["kind"]))
            for other in projects:
                if other["id"] == project["id"]:
                    continue
                if _unit_matches_project(unit, other):
                    edges.append(_edge(node_id, f"c:{other['id']}", "path"))
                    break
    return nodes, edges


def config_search_rows(projects: list[dict]) -> list[dict]:
    """Flat rows stored with the brain so config values can be searched from the cache."""
    rows = []
    for project in projects:
        report = project.get("microstation_config") or None
        if not report:
            continue
        for unit in report.get("units") or []:
            for var in unit.get("variables") or []:
                if not var.get("value") and not var.get("locked"):
                    continue
                text = " ".join(
                    [
                        unit.get("kind") or "",
                        unit.get("name") or "",
                        unit.get("workspace") or "",
                        var.get("name") or "",
                        var.get("level") or "",
                        var.get("value") or "",
                        var.get("file") or "",
                    ]
                )
                rows.append(
                    {
                        "project_id": project["id"],
                        "project": project.get("name") or project["id"],
                        "file": var.get("file") or unit.get("file") or "",
                        "file_id": var.get("file_id") or unit.get("file_id"),
                        "text": text,
                        "snippet": (
                            f"{unit.get('kind') or 'config'} {unit.get('name') or ''}: "
                            f"{var.get('name')} = {var.get('value') or 'unset'} ({var.get('level') or 'unset'})"
                        )[:400],
                    }
                )
    return rows


def _rel_ids(report: dict) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for unit in report.get("units") or []:
        if unit.get("file"):
            found.setdefault(unit["file"], unit.get("file_id"))
        for var in unit.get("variables") or []:
            if var.get("file"):
                found.setdefault(var["file"], var.get("file_id"))
        for ref in _all_refs(unit):
            if ref.get("rel"):
                found.setdefault(ref["rel"], ref.get("file_id"))
    return found


def _all_refs(unit: dict) -> list[dict]:
    refs = []
    for var in unit.get("variables") or []:
        refs.extend(var.get("references") or [])
    return refs


def _unit_matches_project(unit: dict, project: dict) -> bool:
    for name in ("_USTN_WORKSETROOT", "_USTN_WORKSPACEROOT", "MS_DEF"):
        var = next((item for item in unit.get("variables") or [] if item.get("name") == name), None)
        if var and _path_matches(var.get("value") or "", project):
            return True
    return False


def _path_matches(value: str, project: dict) -> bool:
    norm = _norm_path(value)
    if not norm or "$" in norm or "/" not in norm:
        return False
    rel = _norm_path(project.get("rel") or "")
    name = (project.get("name") or "").casefold()
    pid = (project.get("id") or "").casefold()
    if rel and rel not in {"", "."} and (norm == rel or norm.endswith("/" + rel)):
        return True
    tail = norm.split("/")[-1]
    return bool(tail) and tail in {name, pid}


def _norm_path(value: str) -> str:
    text = (value or "").replace("\\", "/").strip()
    while text.endswith("/"):
        text = text[:-1]
    return text.casefold()


def _dedupe_graph(edges: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for edge in edges:
        key = (edge["source"], edge["target"], edge.get("label") or "")
        if key in seen or edge["source"] == edge["target"]:
            continue
        seen.add(key)
        out.append(edge)
    return out


def _plans(sources: list[Source]) -> tuple[list[dict], list[Source]]:
    workspaces: dict[str, list[Source]] = {}
    worksets: dict[tuple[str, str], list[Source]] = {}
    bases = [item for item in sources if item.kind == "base"]
    roles = [item for item in sources if item.kind == "role"]
    users = [item for item in sources if item.kind == "user"]
    pcfs = [item for item in sources if item.kind == "pcf"]
    loose = [item for item in sources if item.kind == "loose"]
    for item in sources:
        if item.kind == "workspace" and item.workspace:
            workspaces.setdefault(item.workspace, []).append(item)
        elif item.kind == "workset" and item.set_name:
            worksets.setdefault((item.workspace, item.set_name), []).append(item)
    ws_entry = {name: _pick(group, name) for name, group in workspaces.items()}
    plans = []
    for name, entry in sorted(ws_entry.items()):
        if entry is None:
            continue
        label = _literal(entry.text, "_USTN_WORKSPACENAME") or name
        plans.append(
            {
                "kind": "workspace",
                "name": label,
                "workspace": label,
                "entry": entry,
                "steps": _chain(bases, None, entry, _roles_for(roles, name), _users_for(users, name, ""), "WorkSpace"),
            }
        )
    for (ws_name, set_name), group in sorted(worksets.items()):
        entry = _pick(group, set_name)
        if entry is None:
            continue
        parent = ws_entry.get(ws_name)
        label = _literal(entry.text, "_USTN_WORKSETNAME") or set_name
        ws_label = _literal(parent.text, "_USTN_WORKSPACENAME") if parent else ws_name
        plans.append(
            {
                "kind": "workset",
                "name": label,
                "workspace": ws_label or ws_name,
                "entry": entry,
                "steps": _chain(bases, parent, entry, _roles_for(roles, ws_name), _users_for(users, ws_name, set_name), "WorkSet"),
            }
        )
    for item in pcfs:
        label = _literal(item.text, "_USTN_PROJECTNAME") or _literal(item.text, "_USTN_WORKSETNAME") or Path(item.rel).stem
        plans.append({"kind": "pcf", "name": label, "workspace": "", "entry": item, "steps": [(item.path, "WorkSet")]})
    if not plans:
        for item in bases:
            plans.append({"kind": "config", "name": Path(item.rel).stem, "workspace": "", "entry": item, "steps": [(item.path, item.level_hint)]})
        for item in users:
            plans.append({"kind": "user", "name": Path(item.rel).stem, "workspace": "", "entry": item, "steps": [(item.path, "User")]})
    return plans, loose


def _chain(
    bases: list[Source],
    workspace: Source | None,
    entry: Source,
    roles: list[Source],
    users: list[Source],
    entry_level: str,
) -> list[tuple[Path, str]]:
    steps: list[tuple[Path, str]] = []
    for item in bases:
        steps.append((item.path, item.level_hint))
    if workspace is not None and workspace.path != entry.path:
        steps.append((workspace.path, "WorkSpace"))
    steps.append((entry.path, entry_level))
    for item in roles:
        steps.append((item.path, "Role"))
    for item in users:
        steps.append((item.path, "User"))
    return steps


def _present(project: dict, plan: dict, evaluated: dict, id_by_rel: dict[str, str | None]) -> dict:
    entry: Source = plan["entry"]
    by_name = {item["name"].casefold(): item for item in evaluated["variables"]}
    fault_names = {str(item.get("variable") or "").casefold() for item in evaluated["faults"]}
    locked_names = {item["name"].casefold() for item in evaluated["variables"] if item.get("locked")}
    rows = []
    for name in KEY_VARS:
        rows.append(by_name.get(name.casefold()) or _empty_var(name))
    extras = [
        item
        for item in evaluated["variables"]
        if item["name"].casefold() not in _KEY_CANON
        and (item["name"].casefold() in fault_names or item["name"].casefold() in locked_names)
    ]
    extras.sort(key=lambda item: item["name"])
    variables = rows + extras
    for item in variables:
        item["file_id"] = id_by_rel.get(item["file"]) if item.get("file") else None
        item["references"] = []
    faults = []
    for fault in evaluated["faults"]:
        fault = dict(fault)
        fault.pop("attempt", None)
        fault["file_id"] = id_by_rel.get(fault.get("file") or "")
        fault.setdefault("prompt", _prompt(fault))
        faults.append(fault)
    return {
        "id": _unit_id(project["id"], plan["kind"], plan.get("workspace") or "", plan["name"]),
        "kind": plan["kind"],
        "name": plan["name"],
        "workspace": plan.get("workspace") or "",
        "project_id": project["id"],
        "file": entry.rel,
        "file_id": id_by_rel.get(entry.rel),
        "files": evaluated["files"],
        "variables": variables,
        "faults": faults,
        "includes": evaluated.get("includes") or [],
        "_all": by_name,
    }


def _attach_mentions(unit: dict, mentions: dict, id_by_rel: dict[str, str | None]) -> None:
    full: dict[str, dict] = unit.pop("_all", {})
    visible: dict[str, dict] = {item["name"].casefold(): item for item in unit["variables"]}
    addin_dirs = _addin_dirs((visible.get("ms_addinpath") or full.get("ms_addinpath") or {}).get("value") or "")
    seen: set[tuple] = set()

    def row_for(name: str) -> dict | None:
        key = name.casefold()
        if key not in full and key not in _KEY_CANON:
            return None
        if key not in visible:
            source = full.get(key) or _empty_var(_KEY_CANON.get(key, name))
            visible[key] = source
            source["file_id"] = id_by_rel.get(source.get("file") or "")
            source.setdefault("references", [])
            unit["variables"].append(source)
        return visible[key]

    def add(name: str, ref: dict) -> None:
        row = row_for(name)
        if row is None:
            return
        marker = (row["name"].casefold(), ref.get("rel"), ref.get("line"), ref.get("how"))
        if marker in seen or len(row["references"]) >= 8:
            return
        seen.add(marker)
        row["references"].append(ref)

    for key, refs in mentions["refs"].items():
        for ref in refs:
            add(mentions["names"].get(key, key), ref)
    for key, writes in mentions["writes"].items():
        row = row_for(mentions["names"].get(key, key))
        if row is None:
            continue
        for ref in writes:
            add(row["name"], ref)
            if not row.get("locked"):
                continue
            unit["faults"].append(
                {
                    "id": "locked-override",
                    "severity": "red",
                    "title": f"{row['name']} is locked",
                    "detail": (
                        f"{row['name']} is locked at {row.get('lock_file') or row.get('file')}:{row.get('lock_line') or row.get('line')}. "
                        f"{ref['rel']}:{ref.get('line')} tries to change it."
                    ),
                    "prompt": "",
                    "variable": row["name"],
                    "file": ref["rel"],
                    "file_id": ref.get("file_id"),
                    "line": ref.get("line"),
                }
            )
            unit["faults"][-1]["prompt"] = _prompt(unit["faults"][-1])
    if addin_dirs and row_for("MS_ADDINPATH") is not None:
        for ref in mentions["files"]:
            if any(_under_rel(ref["rel"], directory) for directory in addin_dirs):
                add("MS_ADDINPATH", {**ref, "kind": "addin", "how": "folder", "line": ref.get("line")})
    keyed = [item for item in unit["variables"] if item["name"].casefold() in _KEY_CANON]
    rest = [item for item in unit["variables"] if item["name"].casefold() not in _KEY_CANON]
    rest.sort(key=lambda item: item["name"])
    unit["variables"] = keyed + rest[:24]
    for fault in unit["faults"]:
        fault.pop("attempt", None)
        fault.setdefault("prompt", _prompt(fault))


def _mentions(root: Path, project: dict, file_recs: list[dict]) -> dict:
    report = project.get("microstation") or {}
    scripts = set(report.get("scripts") or [])
    refs: dict[str, list[dict]] = {}
    writes: dict[str, list[dict]] = {}
    names: dict[str, str] = {}
    files = []
    for rec in file_recs:
        rel = rec.get("rel") or ""
        suffix = Path(rel).suffix.lower()
        if suffix in _CONFIG_EXT:
            continue
        if suffix not in {".py", ".xml"} and not rel.lower().endswith(".commands.xml"):
            if suffix in {".ma"}:
                files.append({"rel": rel, "file_id": rec.get("id"), "line": None, "kind": "addin", "how": "folder"})
            continue
        text = _safe_text(root, project, rel)
        kind = "keyin" if rel.lower().endswith(".commands.xml") else "script"
        if rel in scripts:
            kind = "script"
        for lineno, line in enumerate(text.splitlines(), start=1):
            written: set[str] = set()
            for match in _WRITE_RE.finditer(line):
                name = match.group("env") or match.group("api") or ""
                if not name:
                    continue
                key = name.casefold()
                written.add(key)
                names.setdefault(key, _KEY_CANON.get(key, name))
                writes.setdefault(key, []).append(
                    {"rel": rel, "file_id": rec.get("id"), "line": lineno, "kind": kind, "how": "assigns"}
                )
            for match in _READ_RE.finditer(line):
                name = next((match.group(group) for group in ("var", "get", "getenv", "idx", "api") if match.groupdict().get(group)), "")
                if not name or name.casefold() in written:
                    continue
                key = name.casefold()
                names.setdefault(key, _KEY_CANON.get(key, name))
                refs.setdefault(key, []).append(
                    {"rel": rel, "file_id": rec.get("id"), "line": lineno, "kind": kind, "how": "reads"}
                )
        if suffix == ".py" or rel.lower().endswith(".xml"):
            files.append({"rel": rel, "file_id": rec.get("id"), "line": None, "kind": kind, "how": "folder"})
    return {"refs": refs, "writes": writes, "names": names, "files": files}


def _addin_dirs(value: str) -> list[str]:
    found = []
    for part in _components(value):
        if _is_absolute(part) or part.startswith("$"):
            continue
        cleaned = part.replace("\\", "/").rstrip("/")
        if cleaned and "*" not in cleaned and "?" not in cleaned:
            found.append(cleaned)
    return found


def _sources(root: Path, project: dict, file_recs: list[dict]) -> list[Source]:
    found = []
    for rec in file_recs:
        rel = rec.get("rel") or ""
        ext = Path(rel).suffix.lower()
        if ext not in _CONFIG_EXT:
            continue
        path = _safe_path(root, project.get("rel") or "", rel)
        if path is None:
            continue
        text = _read_text(path)
        found.append(_classify(rel, path, text))
    found.sort(key=lambda item: item.rel)
    return found


def _classify(rel: str, path: Path, text: str) -> Source:
    parts = rel.split("/")
    folders = [part.casefold() for part in parts[:-1]]
    parent = parts[-2].casefold() if len(parts) > 1 else ""
    workspace = ""
    set_name = ""
    if "workspaces" in folders:
        workspace = parts[folders.index("workspaces") + 1]
    ext = Path(rel).suffix.lower()
    kind = "loose"
    if ext == ".pcf":
        kind = "pcf"
    elif ext == ".ucf":
        kind = "user"
    elif "worksets" in folders:
        index = folders.index("worksets")
        if index + 1 < len(parts) - 1:
            set_name = parts[index + 1]
            kind = "workset"
    elif any(part in {"role", "roles"} for part in folders):
        kind = "role"
    elif "workspaces" in folders and workspace:
        kind = "workspace"
    elif any(part in {"organization", "system", "application"} for part in folders):
        kind = "base"
    if kind in {"user", "pcf", "workset"} and "worksets" in folders:
        index = folders.index("worksets")
        if index + 1 < len(parts) - 1:
            set_name = parts[index + 1]
    level_hint = "WorkSet"
    if kind == "base":
        if "system" in folders:
            level_hint = "System"
        elif "application" in folders:
            level_hint = "Application"
        else:
            level_hint = "Organization"
    elif kind == "user":
        level_hint = "User"
    elif kind == "role":
        level_hint = "Role"
    elif kind == "workspace":
        level_hint = "WorkSpace"
    direct = False
    if kind == "workset":
        direct = parent == set_name.casefold()
    elif kind == "workspace":
        direct = parent == workspace.casefold()
    return Source(rel, path, text, kind, workspace, set_name, direct, Path(rel).suffix.lower(), level_hint)


def _pick(group: list[Source], name: str) -> Source | None:
    pool = [item for item in group if item.direct and item.ext == ".cfg"]
    if not pool:
        pool = [item for item in group if item.ext == ".cfg"]
    if not pool:
        return None

    def score(item: Source) -> tuple:
        stem = Path(item.rel).stem.casefold()
        rank = 0 if stem == name.casefold() else 1 if stem in {"workset", "workspace"} else 2
        return (rank, len(item.rel), item.rel)

    return min(pool, key=score)


def _roles_for(roles: list[Source], workspace: str) -> list[Source]:
    return [item for item in roles if not item.workspace or item.workspace.casefold() == (workspace or "").casefold()]


def _users_for(users: list[Source], workspace: str, workset: str) -> list[Source]:
    picked = []
    for item in users:
        if item.set_name and item.set_name.casefold() != workset.casefold():
            continue
        if item.workspace and workspace and item.workspace.casefold() != workspace.casefold():
            continue
        if item.set_name and not workset:
            continue
        picked.append(item)
    return picked


def _literal(text: str, var: str) -> str:
    match = re.search(rf"(?im)^\s*{re.escape(var)}\s*=\s*([^#\n]+)", text or "")
    if not match:
        return ""
    value = _unquote(match.group(1).strip())
    if not value or "$" in value or ";" in value:
        return ""
    return value.strip()


def _pcf_fault(plan: dict, variables: list[dict]) -> dict:
    names = {item["name"].casefold() for item in variables}
    detail = f"{plan['entry'].rel} is a legacy project configuration (.pcf). Upgrade it to a WorkSet .cfg."
    if names & {"_ustn_projectdata", "_ustn_projectname", "_ustn_projectdescr"}:
        detail += " Rename PROJECT variables to WORKSET. _USTN_PROJECTDATA becomes _USTN_WORKSETROOT."
    fault = {
        "id": "pcf-upgrade",
        "severity": "amber",
        "title": "Project needs a WorkSet",
        "detail": detail,
        "variable": "",
        "file": plan["entry"].rel,
        "line": 1,
    }
    fault["prompt"] = _prompt(fault)
    return fault


def _include_fault(kind: str, file: str, line: int, spec: str, why: str) -> dict:
    missing = kind == "missing"
    fault = {
        "id": "missing-include" if missing else "unresolved-include",
        "severity": "red",
        "title": "Include file is missing" if missing else "Include can't be resolved",
        "detail": f"{file}:{line} includes {spec}. {why}.".strip(),
        "variable": "",
        "file": file,
        "line": line,
    }
    fault["prompt"] = _prompt(fault)
    return fault


def _prompt(fault: dict) -> str:
    name = fault.get("variable") or "the variable"
    file = fault.get("file") or "the configuration file"
    line = fault.get("line") or ""
    where = f"{file}:{line}" if line else file
    ident = fault.get("id")
    if ident == "missing-slash":
        text = (
            f"In {where}, {name} is a folder value and is missing the trailing /. "
            "MicroStation concatenates folder variables, so add the slash. Do not read .env values."
        )
    elif ident == "hard-coded-user":
        text = (
            f"In {where}, {name} points at a C:/Users path. "
            "Replace it with a configuration variable such as $(_USTN_WORKSETROOT) so the WorkSet opens on another PC. "
            "Do not read .env values."
        )
    elif ident == "locked-override":
        text = (
            f"{name} is locked, and {where} tries to change it. "
            "Remove the later assignment, or change the lock in the file that set it. Do not read .env values."
        )
    elif ident == "missing-include":
        text = f"{where} includes a configuration file that is not in the scan. Add the file or correct the path. Do not read .env values."
    elif ident == "unresolved-include":
        text = f"{where} has an %include that did not resolve inside the scan. Check the variable expansion and keep the path inside the project. Do not read .env values."
    elif ident == "pcf-upgrade":
        text = (
            f"{file} is a legacy .pcf. Copy it into the WorkSpace WorkSets folder, rename it to .cfg, "
            "and replace PROJECT with WORKSET (_USTN_PROJECTDATA becomes _USTN_WORKSETROOT). "
            "The key-in is PROJECT UPGRADEALLTOWORKSETS. Do not read .env values."
        )
    else:
        text = f"Fix the MicroStation configuration fault at {where}. Do not read .env values."
    return redact(text)


def _empty_var(name: str) -> dict:
    return {
        "name": name,
        "value": "",
        "level": "",
        "file": "",
        "file_id": None,
        "line": None,
        "locked": False,
        "lock_file": "",
        "lock_line": None,
        "operator": "",
        "references": [],
    }


def _unit_id(project_id: str, kind: str, workspace: str, name: str) -> str:
    raw = f"{kind}-{workspace}-{name}".casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-") or kind
    return f"{project_id}:{slug}"


def _components(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def _needs_slash(part: str) -> bool:
    if re.search(r"[*?]", part):
        return False
    if part.endswith("/") or part.endswith("\\"):
        return False
    tail = part.rstrip("/\\").replace("\\", "/").split("/")[-1]
    if "." in tail and tail.rsplit(".", 1)[-1].lower() in _FILE_EXT:
        return False
    return True


def _join(existing: str, operand: str, prepend: bool) -> str:
    if not existing:
        return operand
    if not operand:
        return existing
    if prepend:
        if existing.startswith(";") or operand.endswith(";"):
            return operand + existing
        return operand + ";" + existing
    if existing.endswith(";") or operand.startswith(";"):
        return existing + operand
    return existing + ";" + operand


def _strip_comment(line: str) -> str:
    out: list[str] = []
    quote = ""
    for char in line:
        if quote:
            out.append(char)
            if char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
            out.append(char)
            continue
        if char == "#":
            break
        out.append(char)
    return "".join(out)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _is_absolute(spec: str) -> bool:
    if spec.startswith("\\\\") or spec.startswith("//"):
        return True
    if _WIN_ABS.match(spec):
        return True
    return Path(spec).is_absolute()


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _under_rel(rel: str, directory: str) -> bool:
    rel_norm = rel.replace("\\", "/").strip("/")
    directory_norm = directory.replace("\\", "/").strip("/")
    return bool(directory_norm) and (rel_norm == directory_norm or rel_norm.startswith(directory_norm + "/"))


def _display(path: Path, project_root: Path, scan_root: Path) -> str:
    resolved = path.resolve()
    for base in (project_root, scan_root):
        try:
            return resolved.relative_to(base.resolve()).as_posix()
        except ValueError:
            continue
    return path.name


def _decode(data: bytes) -> str:
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def _read_text(path: Path) -> str:
    try:
        data = path.read_bytes()[: READ_CAP + 1]
    except OSError:
        return ""
    return _decode(data[:READ_CAP])


def _project_root(root: Path, project: dict) -> Path:
    rel = project.get("rel") or ""
    if not rel or rel == ".":
        return Path(root).resolve()
    return (Path(root) / rel).resolve()


def _safe_path(root: Path, project_rel: str, rel: str) -> Path | None:
    base = Path(root) if not project_rel or project_rel == "." else Path(root) / project_rel
    try:
        candidate = (base / rel).resolve()
        candidate.relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return None
    if not candidate.is_file():
        return None
    return candidate


def _safe_text(root: Path, project: dict, rel: str) -> str:
    path = _safe_path(root, project.get("rel") or "", rel)
    if path is None:
        return ""
    return _read_text(path)


def _redact_obj(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_redact_obj(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_obj(item) for key, item in value.items()}
    return value


def _prepare_expr(expr: str, state: ConfigState) -> str:
    def repl(match: re.Match[str]) -> str:
        return _quote(state.expand_all(match.group(0)))

    return _VAR_REF.sub(repl, expr or "")


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _tokenize(expr: str) -> list[str]:
    tokens = []
    for match in _TOKEN_RE.finditer(expr or ""):
        token = match.group(0)
        if token.strip() == "" and token != token.strip():
            continue
        if token.isspace():
            continue
        tokens.append(token)
    return tokens


def _parse_or(tokens: list[str], index: int, state: ConfigState):
    value, index = _parse_and(tokens, index, state)
    while index < len(tokens) and tokens[index].casefold() in {"or", "||", "|"}:
        right, index = _parse_and(tokens, index + 1, state)
        value = _truthy(value) or _truthy(right)
    return value, index


def _parse_and(tokens: list[str], index: int, state: ConfigState):
    value, index = _parse_not(tokens, index, state)
    while index < len(tokens) and tokens[index].casefold() in {"and", "&&", "&"}:
        right, index = _parse_not(tokens, index + 1, state)
        value = _truthy(value) and _truthy(right)
    return value, index


def _parse_not(tokens: list[str], index: int, state: ConfigState):
    if index < len(tokens) and tokens[index].casefold() in {"!", "not"}:
        value, index = _parse_not(tokens, index + 1, state)
        return not _truthy(value), index
    return _parse_cmp(tokens, index, state)


def _parse_cmp(tokens: list[str], index: int, state: ConfigState):
    left, index = _parse_primary(tokens, index, state)
    if index < len(tokens) and tokens[index] in {"==", "!=", "<", ">", "<=", ">=", "<>"}:
        op = tokens[index]
        right, index = _parse_primary(tokens, index + 1, state)
        return _compare(left, op, right), index
    return left, index


def _parse_primary(tokens: list[str], index: int, state: ConfigState):
    if index >= len(tokens):
        raise ValueError("empty")
    token = tokens[index]
    if token == "(":
        value, index = _parse_or(tokens, index + 1, state)
        if index >= len(tokens) or tokens[index] != ")":
            raise ValueError("paren")
        return value, index + 1
    word = token.casefold()
    if word == "defined":
        name, index = _parse_called_name(tokens, index + 1)
        return state.defined(name), index
    if word in {"exists", "exist"}:
        spec, index = _parse_called_name(tokens, index + 1)
        return _exists(spec, state), index
    if token[0] in {'"', "'"}:
        return _unescape(token[1:-1]), index + 1
    return token, index + 1


def _parse_called_name(tokens: list[str], index: int) -> tuple[str, int]:
    if index < len(tokens) and tokens[index] == "(":
        if index + 1 >= len(tokens):
            raise ValueError("call")
        name = _unescape(tokens[index + 1][1:-1]) if tokens[index + 1][0] in {'"', "'"} else tokens[index + 1]
        if index + 2 >= len(tokens) or tokens[index + 2] != ")":
            raise ValueError("call")
        return name, index + 3
    if index >= len(tokens):
        raise ValueError("name")
    token = tokens[index]
    if token[0] in {'"', "'"}:
        return _unescape(token[1:-1]), index + 1
    return token, index + 1


def _exists(spec: str, state: ConfigState) -> bool:
    spec = _unquote(spec.strip())
    if not spec:
        return False
    if _is_absolute(spec):
        try:
            return Path(spec).exists()
        except OSError:
            return False
    bases = [state._current_dir(), state.project_root, state.scan_root]
    for base in bases:
        if base is None:
            continue
        try:
            if (base / spec).exists():
                return True
        except OSError:
            continue
    return False


def _compare(left, op: str, right) -> bool:
    if _number(left) is not None and _number(right) is not None:
        left_n = _number(left)
        right_n = _number(right)
        assert left_n is not None and right_n is not None
        if op == "==":
            return left_n == right_n
        if op in {"!=", "<>"}:
            return left_n != right_n
        if op == "<":
            return left_n < right_n
        if op == ">":
            return left_n > right_n
        if op == "<=":
            return left_n <= right_n
        if op == ">=":
            return left_n >= right_n
    left_s = str(left)
    right_s = str(right)
    if op == "==":
        return left_s == right_s
    if op in {"!=", "<>"}:
        return left_s != right_s
    if op == "<":
        return left_s < right_s
    if op == ">":
        return left_s > right_s
    if op == "<=":
        return left_s <= right_s
    if op == ">=":
        return left_s >= right_s
    return False


def _number(value) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    return text not in {"", "0", "false", "no"}


def _unescape(text: str) -> str:
    return text.replace('\\"', '"').replace("\\\\", "\\")


# Bind the helpers that were defined after the class body.
ConfigState.process_file = process_file  # type: ignore[attr-defined]
ConfigState.snapshot = snapshot  # type: ignore[attr-defined]
ConfigState._handle_line = _handle_line  # type: ignore[attr-defined]
ConfigState._directive = _directive  # type: ignore[attr-defined]
ConfigState._flow = _flow  # type: ignore[attr-defined]
ConfigState._include = _include  # type: ignore[attr-defined]
ConfigState._resolve = _resolve  # type: ignore[attr-defined]
ConfigState._glob = _glob  # type: ignore[attr-defined]
ConfigState._current_dir = _current_dir  # type: ignore[attr-defined]
ConfigState._names = _names  # type: ignore[attr-defined]
ConfigState._one_name = _one_name  # type: ignore[attr-defined]
ConfigState._condition = _condition  # type: ignore[attr-defined]
