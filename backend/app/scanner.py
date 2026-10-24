"""Walk a folder of messy projects and build the brain document.

Each immediate subfolder is a project. A folder with no subfolders is one
project. .env files contribute key names only — the characters after '=' are
never stored.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from backend.app.catalog import CATEGORY_ORDER, SKILLS, SERVICES, ServiceDef
from backend.app.redact import redact

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    ".brain",
    ".idea",
    ".vs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "site-packages",
    "coverage",
    "htmlcov",
    "bower_components",
    ".nuget",
    ".gradle",
    ".m2",
    "target",
    "obj",
    ".cache",
    ".parcel-cache",
    ".turbo",
    ".eggs",
    # OneDrive / cloud-sync caches. The OneDrive folder itself is not skipped.
    "onedrivetemp",
    ".tmp.driveupload",
    ".tmp.drivedownload",
    "filecoauth",
    "$recycle.bin",
    "system volume information",
}
SKIP_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".7z", ".rar", ".iso", ".dmg", ".msi", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp4", ".mp3", ".wav", ".avi", ".mov", ".mkv", ".flac", ".ogg",
    ".pyc", ".exe", ".dll", ".bin", ".so", ".dylib", ".pdb", ".obj", ".o", ".a", ".lib",
    ".class", ".jar", ".whl", ".pt", ".onnx", ".safetensors", ".parquet", ".sqlite", ".db",
    ".lock", ".svg", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
    ".npy", ".npz", ".h5", ".hdf5", ".pkl", ".pickle", ".gguf", ".wasm",
}
SKIP_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
}
# FILE_ATTRIBUTE_* values. Present on Windows stat results; zero elsewhere.
_ATTR_REPARSE = 0x400
_ATTR_OFFLINE = 0x1000
_ATTR_RECALL_ON_OPEN = 0x00040000
_ATTR_RECALL_ON_DATA = 0x00400000
_ATTR_SKIP_FILE = _ATTR_REPARSE | _ATTR_OFFLINE | _ATTR_RECALL_ON_OPEN | _ATTR_RECALL_ON_DATA
MAX_FILE_BYTES = 350_000
HUGE_FILE_BYTES = 8_000_000
MAX_FILES = 2000
PER_PROJECT = 250
EXCERPT = 900
ProgressFn = Callable[[dict], None]

_KEY_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_TODO_RE = re.compile(
    r"(?im)^\s*(?:[-*+]|\d+[.)])?\s*(?:#|//|<!--)?\s*(TODO|FIXME|HACK|XXX)\b[:\s-]*(.{0,140})"
)
_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.M)


def ignored_dir_name(name: str) -> bool:
    return name.casefold() in {item.casefold() for item in IGNORE_DIRS}


def build_brain(root: Path, progress: ProgressFn | None = None) -> dict:
    root = root.expanduser().resolve()
    _emit(progress, message="Finding folders", projects=0, files=0, current=str(root))
    projects_spec = _detect_projects(root)
    projects: list[dict] = []
    files: list[dict] = []
    truncated = False
    used_ids: set[str] = set()
    for index, (name, path, shallow) in enumerate(projects_spec):
        remaining = MAX_FILES - len(files)
        if remaining <= 0:
            truncated = True
            break
        _emit(
            progress,
            message=f"Reading {name}",
            projects=index,
            files=len(files),
            current=str(path),
        )
        shell = _project_shell(name, path, root)
        shell["id"] = _unique_slug(name, used_ids)
        budget = min(PER_PROJECT, remaining)

        def _on_file(file_path: Path, seen: int, _name: str = name, _base: int = len(files), _index: int = index) -> None:
            if seen % 20 != 0:
                return
            _emit(
                progress,
                message=f"Reading {_name}",
                projects=_index,
                files=_base + seen,
                current=str(file_path),
            )

        proj_files, hit_cap = _scan_project(shell["id"], path, shallow, budget, _on_file)
        for rec in proj_files:
            rec["project_rel"] = shell["rel"]
        files.extend(proj_files)
        projects.append(shell)
        if hit_cap:
            truncated = True
            if len(proj_files) >= remaining:
                break

    _resolve_imports(files)
    skills = _aggregate_skills(files)
    connections = _aggregate_services(files)
    for project in projects:
        pf = [f for f in files if f["project_id"] == project["id"]]
        _fill_project(project, pf, skills)
    architecture = {
        "corpus": _corpus_graph(projects, files, connections),
        "projects": {p["id"]: _project_graph(p, files, connections) for p in projects},
    }
    stats = {
        "projects": len(projects),
        "files": len(files),
        "skills": len(skills),
        "lines": sum(f["lines"] for f in files),
        "todos": sum(len(f["todos"]) for f in files),
        "connections_live": sum(1 for c in connections if c["status"] == "connected"),
        "connections_referenced": sum(1 for c in connections if c["status"] == "referenced"),
    }
    return {
        "root": str(root),
        "root_name": root.name,
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "truncated": truncated,
        "projects": projects,
        "files": files,
        "skills": skills,
        "categories": _categories(skills),
        "connections": connections,
        "architecture": architecture,
        "suggestions": _suggestions(projects, skills, connections),
        "stats": stats,
        "summaries": "heuristic",
    }


def signature(root: Path, progress: ProgressFn | None = None) -> str:
    """Cheap change token: relative path, size, mtime. Not file contents."""
    root = root.expanduser().resolve()
    h = hashlib.sha256(b"brain-v3")
    if not root.exists():
        h.update(b"missing")
        return h.hexdigest()
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        _prune_dirs(dirnames, dirpath)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if not _interesting(path) or _blocked_file(path):
                continue
            try:
                st = path.lstat()
            except OSError:
                continue
            rel = path.relative_to(root).as_posix()
            h.update(rel.encode())
            h.update(str(st.st_size).encode())
            h.update(str(int(st.st_mtime_ns)).encode())
            seen += 1
            if progress and seen % 100 == 0:
                _emit(progress, message="Checking what changed", files=seen, projects=0, current=rel)
    return h.hexdigest()


def file_excerpt(root: Path, file_rec: dict) -> dict:
    """Re-read one indexed file for the drawer. Env files stay key-names-only."""
    if file_rec.get("env_class"):
        keys = ", ".join(file_rec.get("env_keys") or []) or "none"
        return {
            "id": file_rec["id"],
            "rel": file_rec["rel"],
            "kind": "env",
            "excerpt": f"Key names only: {keys}. Values are never loaded.",
            "env_keys": file_rec.get("env_keys") or [],
        }
    path = _resolve_under_root(root, file_rec)
    if path is None or not path.is_file():
        return {"id": file_rec["id"], "rel": file_rec["rel"], "excerpt": file_rec.get("excerpt") or ""}
    text = _read_text(path)
    if text is None:
        return {"id": file_rec["id"], "rel": file_rec["rel"], "excerpt": "Could not read this file."}
    return {
        "id": file_rec["id"],
        "rel": file_rec["rel"],
        "kind": file_rec["kind"],
        "excerpt": redact(text)[:4000],
    }


def _resolve_under_root(root: Path, file_rec: dict) -> Path | None:
    root = root.resolve()
    project_rel = file_rec.get("project_rel") or ""
    base = root if not project_rel or project_rel == "." else (root / project_rel)
    candidate = (base / file_rec["rel"]).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _emit(progress: ProgressFn | None, **fields: object) -> None:
    if progress:
        progress(fields)


def _detect_projects(root: Path) -> list[tuple[str, Path, bool]]:
    subdirs = [
        p for p in sorted(root.iterdir(), key=lambda p: p.name.lower())
        if p.is_dir() and not p.name.startswith(".") and not ignored_dir_name(p.name) and not _is_reparse(p)
    ]
    loose = [p for p in root.iterdir() if p.is_file() and _interesting(p)]
    if subdirs:
        specs = [(p.name, p, False) for p in subdirs]
        if loose:
            specs.append(("(loose files)", root, True))
        return specs
    return [(root.name, root, False)]


def _project_shell(name: str, path: Path, root: Path) -> dict:
    if path.resolve() == root.resolve():
        rel = "."
    else:
        rel = path.relative_to(root).as_posix()
    return {
        "id": "",
        "name": name,
        "rel": rel,
        "summary": "",
        "summary_source": "heuristic",
        "skills": [],
        "services": [],
        "entries": [],
        "stats": {},
    }


def _scan_project(
    pid: str,
    path: Path,
    shallow: bool,
    budget: int,
    on_file: Callable[[Path, int], None] | None = None,
) -> tuple[list[dict], bool]:
    found: list[dict] = []
    hit_cap = False
    seen = 0
    for file_path in _iter_files(path, shallow):
        seen += 1
        if on_file:
            on_file(file_path, seen)
        if len(found) >= budget:
            hit_cap = True
            break
        rec = _scan_file(pid, path, file_path)
        if rec:
            found.append(rec)
    return found, hit_cap


def _iter_files(path: Path, shallow: bool):
    if shallow:
        for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
            if child.is_file() and _interesting(child) and not _blocked_file(child):
                yield child
        return
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
        _prune_dirs(dirnames, dirpath)
        for name in sorted(filenames):
            file_path = Path(dirpath) / name
            if _interesting(file_path) and not _blocked_file(file_path):
                yield file_path


def _prune_dirs(dirnames: list[str], parent: str) -> None:
    parent_path = Path(parent)
    kept: list[str] = []
    for name in dirnames:
        if ignored_dir_name(name):
            continue
        if _is_reparse(parent_path / name):
            continue
        kept.append(name)
    dirnames[:] = sorted(kept)


def _file_attrs(path: Path) -> int:
    try:
        st = path.lstat()
    except OSError:
        return 0
    return int(getattr(st, "st_file_attributes", 0) or 0)


def _is_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
    except OSError:
        return True
    return bool(_file_attrs(path) & _ATTR_REPARSE)


def _blocked_file(path: Path) -> bool:
    """Cloud-only placeholders and reparse files block on read. Leave them out."""
    try:
        st = path.lstat()
    except OSError:
        return True
    attrs = int(getattr(st, "st_file_attributes", 0) or 0)
    if attrs & _ATTR_SKIP_FILE:
        return True
    if st.st_size > HUGE_FILE_BYTES:
        return True
    return False


def blocked_by_attrs(attrs: int, size: int) -> bool:
    """Test hook for the Windows offline / reparse / huge-file rules."""
    if attrs & _ATTR_SKIP_FILE:
        return True
    return size > HUGE_FILE_BYTES


def _interesting(path: Path) -> bool:
    lower = path.name.lower()
    if lower in SKIP_NAMES or lower.startswith("~$") or lower.endswith(".tmp"):
        return False
    if path.suffix.lower() in SKIP_EXT:
        return False
    if path.name.startswith(".") and _env_class(path.name) is None and path.name not in {".gitignore", ".editorconfig"}:
        return False
    return True


def _env_class(name: str) -> str | None:
    lower = name.lower()
    if lower == ".env" or lower.startswith(".env."):
        if any(token in lower for token in ("example", "sample", "template")):
            return "template"
        return "live"
    return None


def _scan_file(project_id: str, project_root: Path, path: Path) -> dict | None:
    if _blocked_file(path):
        return None
    rel = path.relative_to(project_root).as_posix()
    env_class = _env_class(path.name)
    kind = _kind(path, env_class)
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_FILE_BYTES)
    except OSError:
        return None
    if b"\x00" in raw[:1024]:
        return _attach(path, _base_record(project_id, rel, path.name, "binary", 0, "Binary file, skipped.", "", [], None, [], False, []))
    text = raw.decode("utf-8", errors="replace")
    lines = text.count("\n") + (1 if text else 0)
    if env_class:
        keys = _env_key_names(text)
        # Drop the raw text immediately. Only names remain.
        summary = (
            f"Example env template. Key names only: {', '.join(keys) or 'none'}."
            if env_class == "template"
            else f"Local env file. Key names only: {', '.join(keys) or 'none'}. Values are not loaded."
        )
        analysis_text = "\n".join(keys)
        skills = _match_skills(rel, analysis_text, "env")
        rec = _base_record(
            project_id, rel, path.name, "env", lines, summary, "", skills, env_class, keys, False, []
        )
        rec["service_how"] = _service_how_for_env(keys, env_class)
        return _attach(path, rec)
    safe = redact(text)
    todos = _todos(safe)
    symbols: list[dict] = []
    local_imports: list[str] = []
    entry = False
    doc = ""
    intro = ""
    if kind == "python":
        parsed = _analyze_python(safe)
        symbols = parsed["symbols"]
        local_imports = parsed["imports"]
        entry = parsed["entry"]
        doc = parsed["doc"]
    if kind == "markdown":
        title, intro = _markdown_bits(safe)
    summary = _summarize_file(path.name, kind, doc, intro, symbols, safe)
    skills = _match_skills(rel, safe, kind)
    excerpt = safe.strip()[:EXCERPT]
    rec = _base_record(project_id, rel, path.name, kind, lines, summary, excerpt, skills, None, [], entry, todos)
    rec["symbols"] = symbols[:24]
    rec["import_names"] = local_imports
    rec["intro"] = (intro or doc or "")[:400]
    rec["title"] = _title(path.name, kind, safe)
    rec["service_how"] = _service_how_for_text(rel, safe)
    return _attach(path, rec, local_imports)


def _base_record(
    project_id, rel, name, kind, lines, summary, excerpt, skills, env_class, env_keys, entry, todos
) -> dict:
    return {
        "id": f"{project_id}:{rel}",
        "project_id": project_id,
        "rel": rel,
        "name": name,
        "kind": kind,
        "lines": lines,
        "summary": summary,
        "excerpt": excerpt,
        "skills": skills,
        "env_class": env_class,
        "env_keys": env_keys,
        "entry": entry,
        "todos": todos,
        "symbols": [],
        "import_names": [],
        "intro": "",
        "title": name,
        "project_rel": "",
        "service_how": {},
        "mtime": None,
        "imports_top": [],
    }


def _attach(path: Path, rec: dict, imports: list[str] | None = None) -> dict:
    """Record mtime and top-level imports. Never stores raw env values."""
    try:
        rec["mtime"] = int(path.lstat().st_mtime)
    except OSError:
        rec["mtime"] = None
    found: list[str] = []
    for name in imports or []:
        top = name.split(".")[0].strip()
        if not top or top.startswith("_") or top in found:
            continue
        found.append(top)
    rec["imports_top"] = found[:32]
    return rec


def _kind(path: Path, env_class: str | None) -> str:
    if env_class:
        return "env"
    if path.name.lower() in {"requirements.txt", "requirements-dev.txt", "pipfile"}:
        return "config"
    ext = path.suffix.lower()
    if ext == ".py":
        return "python"
    if ext in {".md", ".markdown", ".txt", ".rst"}:
        return "markdown"
    if ext in {".json", ".yml", ".yaml", ".toml", ".ini", ".cfg"}:
        return "config"
    if ext in {".sh", ".ps1", ".bat", ".cmd"}:
        return "shell"
    if ext == ".ipynb":
        return "notebook"
    return "other"


def _env_key_names(text: str) -> list[str]:
    keys: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _KEY_RE.match(stripped)
        if match:
            keys.append(match.group(1))
    return keys


def _todos(text: str) -> list[dict]:
    found = []
    for i, line in enumerate(text.splitlines(), start=1):
        match = _TODO_RE.search(line)
        if match:
            found.append({"line": i, "text": redact(line.strip())[:180]})
    return found[:20]


def _analyze_python(text: str) -> dict:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {
            "symbols": [],
            "imports": [],
            "doc": "",
            "entry": "__main__" in text or "argparse" in text,
        }
    doc = ast.get_docstring(tree) or ""
    symbols = []
    imports = []
    has_main = False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(
                {
                    "name": node.name,
                    "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                    "decision": _is_decision(node),
                }
            )
        elif isinstance(node, ast.If) and _is_main_guard(node):
            has_main = True
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.extend(_import_names(node))
    entry = has_main or "argparse" in text
    return {"symbols": symbols, "imports": imports, "doc": doc.strip(), "entry": entry}


def _is_decision(node: ast.AST) -> bool:
    name = getattr(node, "name", "").lower()
    if any(token in name for token in ("route", "classify", "decide", "choose", "dispatch", "bucket", "triage")):
        return True
    ifs = [n for n in ast.walk(node) if isinstance(n, ast.If)]
    return len(ifs) >= 2


def _is_main_guard(node: ast.If) -> bool:
    src = ast.dump(node.test)
    return "__name__" in src and "__main__" in src


def _import_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        base = node.module or ""
        names = [alias.name for alias in node.names]
        if base:
            return [base, *[f"{base}.{n}" for n in names]]
        return names
    return []


def _markdown_bits(text: str) -> tuple[str, str]:
    title = ""
    heading = _HEADING_RE.search(text)
    if heading:
        title = heading.group(1).strip()
    paragraph: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith("#") or stripped.startswith("```") or stripped.startswith("---"):
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    intro = " ".join(paragraph)[:500]
    return title, intro


def _title(name: str, kind: str, text: str) -> str:
    if kind == "markdown":
        heading = _HEADING_RE.search(text)
        if heading:
            return heading.group(1).strip()[:80]
    return name


def _summarize_file(name: str, kind: str, doc: str, intro: str, symbols: list[dict], text: str) -> str:
    if kind == "python":
        if doc:
            return doc.splitlines()[0][:240]
        names = [s["name"] for s in symbols[:4]]
        if names:
            return f"Python script defining {', '.join(names)}."
        return "Python script."
    if kind == "markdown":
        return (intro or f"Notes in {name}.")[:240]
    if kind == "config":
        return f"Configuration file {name}."
    if kind == "shell":
        return f"Shell helper {name}."
    if kind == "notebook":
        return f"Notebook {name}."
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return (first or name)[:240]


def _match_skills(rel: str, text: str, kind: str) -> list[str]:
    blob = f"{rel}\n{text}".lower()
    hits: list[str] = []
    for skill in SKILLS:
        if skill.special == "lab-notes":
            if kind == "markdown" and "prompt" not in rel.lower():
                hits.append(skill.id)
            continue
        if any(needle in blob for needle in skill.needles):
            hits.append(skill.id)
    return hits


def _resolve_imports(files: list[dict]) -> None:
    """Point local imports at other files in the same project."""
    by_project: dict[str, list[dict]] = {}
    for rec in files:
        by_project.setdefault(rec["project_id"], []).append(rec)
    for group in by_project.values():
        index = _import_index(group)
        for rec in group:
            rec["imports_local"] = []
            for name in rec.get("import_names") or []:
                target = index.get(name) or index.get(name.split(".")[-1])
                if target and target != rec["id"] and target not in rec["imports_local"]:
                    rec["imports_local"].append(target)
            rec.pop("import_names", None)


def _import_index(files: list[dict]) -> dict[str, str]:
    index: dict[str, str] = {}
    for rec in files:
        if rec["kind"] != "python":
            continue
        rel = Path(rec["rel"])
        stem_path = rel.with_suffix("")
        index[stem_path.as_posix()] = rec["id"]
        index[stem_path.as_posix().replace("/", ".")] = rec["id"]
        index[rel.stem] = rec["id"]
        if rel.name == "__init__.py" and rel.parent.name:
            index[rel.parent.as_posix()] = rec["id"]
            index[rel.parent.as_posix().replace("/", ".")] = rec["id"]
            index[rel.parent.name] = rec["id"]
    return index


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "project"


def _unique_slug(name: str, used: set[str]) -> str:
    base = _slug(name)
    pid = base
    n = 2
    while pid in used:
        pid = f"{base}-{n}"
        n += 1
    used.add(pid)
    return pid


def _service_how_for_env(keys: list[str], env_class: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for service in SERVICES:
        matched = [key for key in keys if key in service.env]
        if not matched:
            continue
        prefix = "env key" if env_class == "live" else "template key"
        found[service.id] = f"{prefix} {matched[0]}"
    return found


def _service_how_for_text(rel: str, text: str) -> dict[str, str]:
    blob = f"{rel}\n{text}".lower()
    found: dict[str, str] = {}
    for service in SERVICES:
        if not any(needle in blob for needle in service.needles):
            continue
        line = _evidence_line(f"{rel}\n{text}", service.needles)
        found[service.id] = line or f"mentioned in {rel}"
    return found


def _evidence_line(text: str, needles: tuple[str, ...]) -> str:
    for line in text.splitlines():
        low = line.lower()
        if any(needle in low for needle in needles):
            cleaned = redact(line.strip())
            return cleaned[:180]
    return ""


def _aggregate_services(files: list[dict]) -> list[dict]:
    connections = []
    for service in SERVICES:
        evidence = []
        for rec in files:
            how = _service_hit(rec, service)
            if not how:
                continue
            evidence.append(
                {
                    "project_id": rec["project_id"],
                    "file_id": rec["id"],
                    "rel": rec["rel"],
                    "how": how,
                }
            )
        if any(item["how"].startswith("env key") for item in evidence):
            status = "connected"
        elif evidence:
            status = "referenced"
        else:
            status = "absent"
        projects = []
        live_projects = []
        for item in evidence:
            if item["project_id"] not in projects:
                projects.append(item["project_id"])
            if item["how"].startswith("env key") and item["project_id"] not in live_projects:
                live_projects.append(item["project_id"])
        connections.append(
            {
                "id": service.id,
                "name": service.name,
                "category": service.category,
                "description": service.description,
                "status": status,
                "projects": projects,
                "live_projects": live_projects,
                "evidence": evidence[:24],
            }
        )
    rank = {"connected": 0, "referenced": 1, "absent": 2}
    connections.sort(key=lambda c: (rank[c["status"]], c["category"], c["name"]))
    return connections


def _service_hit(rec: dict, service: ServiceDef) -> str:
    return (rec.get("service_how") or {}).get(service.id, "")


def _aggregate_skills(files: list[dict]) -> list[dict]:
    by_id = {s.id: s for s in SKILLS}
    bucket: dict[str, list[dict]] = {s.id: [] for s in SKILLS}
    for rec in files:
        for sid in rec["skills"]:
            if sid not in bucket:
                continue
            skill = by_id[sid]
            line = ""
            if skill.needles:
                line = _evidence_line(f"{rec['rel']}\n{rec.get('excerpt') or ''}", skill.needles)
            bucket[sid].append(
                {
                    "project_id": rec["project_id"],
                    "file_id": rec["id"],
                    "rel": rec["rel"],
                    "line": line,
                }
            )
    skills = []
    for skill in SKILLS:
        evidence = bucket[skill.id]
        if not evidence:
            continue
        projects = []
        for item in evidence:
            if item["project_id"] not in projects:
                projects.append(item["project_id"])
        skills.append(
            {
                "id": skill.id,
                "name": skill.name,
                "category": skill.category,
                "blurb": skill.blurb,
                "score": len(evidence),
                "projects": projects,
                "files": evidence[:30],
            }
        )
    order = {name: i for i, name in enumerate(CATEGORY_ORDER)}
    skills.sort(key=lambda s: (order.get(s["category"], 99), -s["score"], s["name"]))
    return skills


def _categories(skills: list[dict]) -> list[dict]:
    grouped: dict[str, list[str]] = {}
    for skill in skills:
        grouped.setdefault(skill["category"], []).append(skill["id"])
    cats = []
    for name in CATEGORY_ORDER:
        if name in grouped:
            cats.append({"id": _slug(name), "name": name, "skills": grouped[name]})
    return cats


def _fill_project(project: dict, files: list[dict], skills: list[dict]) -> None:
    skill_ids = []
    for skill in skills:
        if project["id"] in skill["projects"] and skill["id"] not in skill_ids:
            skill_ids.append(skill["id"])
    service_ids = []
    live_keys: list[str] = []
    for rec in files:
        if rec.get("env_class") == "live":
            for key in rec["env_keys"]:
                if key not in live_keys:
                    live_keys.append(key)
    # services filled later? We need service evidence per project. Compute from file hits.
    for service in SERVICES:
        if any(_service_hit(rec, service) for rec in files):
            service_ids.append(service.id)
    entries = [rec["rel"] for rec in files if rec.get("entry")]
    readme = next((rec for rec in files if rec["name"].lower() == "readme.md"), None)
    py = sum(1 for rec in files if rec["kind"] == "python")
    md = sum(1 for rec in files if rec["kind"] == "markdown")
    todos = [item for rec in files for item in rec["todos"]]
    bits = []
    if readme and readme.get("intro"):
        intro = readme["intro"].strip()
        if intro[-1:] not in ".!?":
            intro += "."
        bits.append(intro)
    bits.append(f"Holds {py} Python file{'s' if py != 1 else ''} and {md} note{'s' if md != 1 else ''}.")
    if entries:
        bits.append(f"Likely entry: {entries[0]}.")
    if service_ids:
        names = [next(s.name for s in SERVICES if s.id == sid) for sid in service_ids[:5]]
        bits.append("Touches " + _join(names) + ".")
    if skill_ids:
        names = [next(s["name"] for s in skills if s["id"] == sid) for sid in skill_ids[:6]]
        bits.append("Skills: " + ", ".join(names) + ".")
    if todos:
        bits.append(f"{len(todos)} unfinished marker{'s' if len(todos) != 1 else ''}.")
    project["summary"] = " ".join(bits)
    project["summary_source"] = "heuristic"
    project["skills"] = skill_ids
    project["services"] = service_ids
    project["entries"] = entries
    project["stats"] = {
        "files": len(files),
        "python": py,
        "markdown": md,
        "lines": sum(rec["lines"] for rec in files),
        "todos": len(todos),
        "env_keys": live_keys,
    }
    for rec in files:
        rec.pop("service_how", None)


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _node_kind(rec: dict) -> str:
    rel = rec["rel"].lower()
    if rec["kind"] in {"env", "config"}:
        return "config"
    if rec["kind"] == "markdown" and "prompt" in rel:
        return "model"
    if rec["kind"] == "markdown":
        return "note"
    if "memory" in rel or "store" in rel:
        return "store"
    if rel.startswith("tools/") or "/tools/" in rel:
        return "tool"
    if rec.get("entry"):
        return "entry"
    if rec["kind"] == "shell":
        return "script"
    if rec["kind"] == "python":
        return "script"
    return "note"


def _file_sub(rec: dict) -> str:
    if rec["kind"] == "python":
        n = len(rec.get("symbols") or [])
        role = "entry" if rec.get("entry") else "python"
        return f"{role} · {n} symbol{'s' if n != 1 else ''}"
    if rec["kind"] == "markdown":
        return "notes"
    if rec["kind"] == "env":
        return "key names only"
    if rec["kind"] == "shell":
        return "shell"
    return rec["kind"]


def _project_graph(project: dict, files: list[dict], connections: list[dict]) -> dict:
    group = [rec for rec in files if rec["project_id"] == project["id"]]
    nodes = []
    edges = []
    root_id = f"n:{project['id']}:root"
    nodes.append(
        {
            "id": root_id,
            "label": project["name"],
            "sub": f"{project['stats'].get('files', 0)} files",
            "kind": "project",
            "project_id": project["id"],
            "file_id": None,
            "service_id": None,
        }
    )
    py = [rec for rec in group if rec["kind"] == "python"]
    py.sort(key=lambda rec: (not rec.get("entry"), -rec["lines"]))
    notes = [rec for rec in group if rec["kind"] == "markdown"]
    notes.sort(key=lambda rec: -rec["lines"])
    other = [rec for rec in group if rec["kind"] in {"shell", "config", "notebook"}]
    env = [rec for rec in group if rec["kind"] == "env"]
    chosen = py[:16] + notes[:6] + other[:4] + env[:2]
    chosen_ids = {rec["id"] for rec in chosen}
    for rec in chosen:
        nodes.append(
            {
                "id": f"n:{rec['id']}",
                "label": rec["title"] if rec["kind"] == "markdown" and rec.get("title") else rec["name"],
                "sub": _file_sub(rec),
                "kind": _node_kind(rec),
                "project_id": project["id"],
                "file_id": rec["id"],
                "service_id": None,
            }
        )
        edges.append({"id": f"e:{root_id}:{rec['id']}", "source": root_id, "target": f"n:{rec['id']}", "label": ""})
        for target in rec.get("imports_local") or []:
            if target in chosen_ids:
                edges.append(
                    {
                        "id": f"e:imp:{rec['id']}:{target}",
                        "source": f"n:{rec['id']}",
                        "target": f"n:{target}",
                        "label": "imports",
                    }
                )
        decisions = [s for s in rec.get("symbols") or [] if s.get("decision")][:3]
        for symbol in decisions:
            did = f"n:{project['id']}:dec:{rec['id']}:{symbol['name']}"
            nodes.append(
                {
                    "id": did,
                    "label": symbol["name"],
                    "sub": "decision",
                    "kind": "decision",
                    "project_id": project["id"],
                    "file_id": rec["id"],
                    "service_id": None,
                }
            )
            edges.append(
                {
                    "id": f"e:dec:{rec['id']}:{symbol['name']}",
                    "source": f"n:{rec['id']}",
                    "target": did,
                    "label": "",
                }
            )
    for conn in connections:
        if conn["id"] == "copilot":
            continue
        if conn["status"] == "absent" or project["id"] not in conn["projects"]:
            continue
        sid = f"n:{project['id']}:svc:{conn['id']}"
        nodes.append(
            {
                "id": sid,
                "label": conn["name"],
                "sub": conn["status"],
                "kind": "service",
                "project_id": project["id"],
                "file_id": None,
                "service_id": conn["id"],
            }
        )
        linked = False
        for item in conn["evidence"]:
            if item["project_id"] != project["id"]:
                continue
            if item["file_id"] in chosen_ids:
                edges.append(
                    {
                        "id": f"e:svc:{item['file_id']}:{conn['id']}",
                        "source": f"n:{item['file_id']}",
                        "target": sid,
                        "label": "",
                    }
                )
                linked = True
        if not linked:
            edges.append({"id": f"e:svcroot:{project['id']}:{conn['id']}", "source": root_id, "target": sid, "label": ""})
    return {"nodes": nodes, "edges": _dedupe_edges(edges)}


def _corpus_graph(projects: list[dict], files: list[dict], connections: list[dict]) -> dict:
    nodes = []
    edges = []
    blobs = {}
    for project in projects:
        nodes.append(
            {
                "id": f"c:{project['id']}",
                "label": project["name"],
                "sub": f"{project['stats'].get('files', 0)} files · {project['stats'].get('lines', 0)} lines",
                "kind": "project",
                "project_id": project["id"],
                "file_id": None,
                "service_id": None,
            }
        )
        blob_parts = [project["name"], project.get("summary") or ""]
        for rec in files:
            if rec["project_id"] == project["id"]:
                blob_parts.append(rec.get("excerpt") or "")
                blob_parts.append(rec.get("intro") or "")
        blobs[project["id"]] = "\n".join(blob_parts)
    for conn in connections:
        if conn["id"] == "copilot":
            continue
        if conn["status"] == "absent" or not conn["projects"]:
            continue
        nid = f"c:svc:{conn['id']}"
        nodes.append(
            {
                "id": nid,
                "label": conn["name"],
                "sub": conn["status"],
                "kind": "service",
                "project_id": None,
                "file_id": None,
                "service_id": conn["id"],
            }
        )
        for pid in conn["projects"]:
            edges.append(
                {
                    "id": f"e:c:{pid}:{conn['id']}",
                    "source": f"c:{pid}",
                    "target": nid,
                    "label": "uses" if conn["status"] == "connected" else "mentions",
                }
            )
    for left in projects:
        if len(left["name"]) < 4:
            continue
        pattern = re.compile(rf"\b{re.escape(left['name'])}\b", re.I)
        for right in projects:
            if left["id"] == right["id"]:
                continue
            if pattern.search(blobs.get(right["id"]) or ""):
                edges.append(
                    {
                        "id": f"e:mention:{right['id']}:{left['id']}",
                        "source": f"c:{right['id']}",
                        "target": f"c:{left['id']}",
                        "label": "mentions",
                    }
                )
    return {"nodes": nodes, "edges": _dedupe_edges(edges)}


def _dedupe_edges(edges: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for edge in edges:
        key = (edge["source"], edge["target"], edge.get("label") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(edge)
    return out


def _suggestions(projects: list[dict], skills: list[dict], connections: list[dict]) -> list[str]:
    out: list[str] = []
    if projects:
        richest = max(projects, key=lambda p: p["stats"].get("lines", 0))
        out.append(f"What does {richest['name']} actually do?")
        out.append(f"How is {richest['name']} wired?")
    live = [c for c in connections if c["status"] == "connected"]
    if live:
        out.append(f"Which folders talk to {live[0]['name']}?")
    out.append("What is still unfinished?")
    specific = [s for s in skills if s["id"] not in {"lab-notes", "copilot", "cli", "prompt-craft"}]
    if specific:
        top = max(specific, key=lambda s: s["score"])
        out.append(f"Where does {top['name']} show up?")
    # Preserve order, drop duplicates.
    deduped = []
    for item in out:
        if item not in deduped:
            deduped.append(item)
    return deduped[:5]


def read_text_for_prompt(root: Path, file_rec: dict, limit: int = 1800) -> str:
    """Redacted text for model context. Env files return key names only."""
    if file_rec.get("env_class"):
        keys = ", ".join(file_rec.get("env_keys") or []) or "none"
        return f"Key names only: {keys}."
    path = _resolve_under_root(root, file_rec)
    if path is None or not path.is_file():
        return file_rec.get("excerpt") or ""
    text = _read_text(path)
    if text is None:
        return file_rec.get("excerpt") or ""
    return redact(text)[:limit]


def _read_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()[:MAX_FILE_BYTES]
    except OSError:
        return None
    if b"\x00" in raw[:1024]:
        return None
    return raw.decode("utf-8", errors="replace")
