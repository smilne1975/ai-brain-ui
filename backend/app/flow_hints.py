"""Conservative static hints from bounded Python source; never execute a workflow."""

import ast
from pathlib import PurePosixPath, PureWindowsPath


def _literal(value: ast.AST | None) -> str | None:
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "Path" and len(value.args) == 1:
        value = value.args[0]
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        return None
    raw = value.value
    if not raw or len(raw) > 400 or any(ord(char) < 32 or char in ":<>|?*" for char in raw):
        return None
    path = PureWindowsPath(raw)
    if path.anchor or not path.parts or ".." in path.parts or any(part.startswith(".") for part in path.parts):
        return None
    return path.as_posix()


def detect(tree: ast.AST) -> list[dict]:
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        candidate = None
        direction = None
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            candidate = node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg == "file"), None)
            mode = node.args[1] if len(node.args) > 1 else next((kw.value for kw in node.keywords if kw.arg == "mode"), None)
            value = "r" if mode is None else mode.value if isinstance(mode, ast.Constant) else None
            if isinstance(value, str) and value and set(value) <= set("rwaxbt") and sum(c in value for c in "rwax") == 1:
                direction = "read" if "r" in value else "write"
        elif isinstance(func, ast.Attribute):
            if func.attr in {"read_text", "read_bytes", "write_text", "write_bytes"}:
                candidate = func.value if isinstance(func.value, ast.Call) else None
                direction = "read" if func.attr.startswith("read") else "write"
            elif func.attr in {"read_csv", "read_json", "read_parquet", "read_excel", "to_csv", "to_json", "to_parquet", "to_excel"} and node.args:
                candidate = node.args[0]
                direction = "read" if func.attr.startswith("read") else "write"
        if direction and (path := _literal(candidate)):
            hint = {"rel": path, "direction": direction, "line": node.lineno}
            if hint not in found:
                found.append(hint)
                if len(found) >= 24:
                    break
    return sorted(found, key=lambda hint: hint["line"])


def resolve(files: list[dict]) -> None:
    """Export only references to visible indexed files in the script's project."""
    indexed = {(row["project_id"], row["rel"]): row["id"] for row in files if row["kind"] != "env"}
    for row in files:
        hints = row.pop("flow_hints", [])
        links = []
        for hint in hints:
            path = PurePosixPath(hint["rel"])
            paths = {path, PurePosixPath(row["rel"]).parent / path}
            targets = {indexed[(row["project_id"], item.as_posix())] for item in paths
                       if (row["project_id"], item.as_posix()) in indexed}
            if len(targets) == 1 and (target := next(iter(targets))) != row["id"]:
                links.append({"file_id": target, "direction": hint["direction"], "line": hint["line"]})
        if links:
            row["workflow_refs"] = links
