"""Minimal MCP JSON-RPC for stdio and for POST /mcp.

Copilot only needs initialize, tools/list, tools/call, resources/list, and
resources/read. Notifications are accepted and not answered.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.app.mcp_tools import cap_text, latest_digest, load_index, log_call, run_tool, tool_specs
from backend.app.mcp_tools import REPO

PROTOCOL = "2024-11-05"
RESOURCE = "brain://digest/latest"


def dispatch(message: dict, root: Path, engine=None) -> dict | None:
    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid request")
    method = str(message.get("method") or "")
    mid = message.get("id", None)
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if mid is None:
        return None
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}, "resources": {"listChanged": False}},
            "serverInfo": {"name": "AI Brain", "version": "0.2.0"},
            "instructions": "Read-only tools over the local AI Brain index. .env values are never returned.",
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_specs()}
    elif method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        called = run_tool(name, arguments, load_index(root, engine))
        result = {"content": [{"type": "text", "text": called["text"]}], "isError": called["is_error"]}
    elif method == "resources/list":
        result = {
            "resources": [
                {
                    "uri": RESOURCE,
                    "name": "Latest daily digest",
                    "description": "The latest daily AI Brain digest markdown.",
                    "mimeType": "text/markdown",
                }
            ]
        }
    elif method == "resources/read":
        uri = str(params.get("uri") or "")
        if uri != RESOURCE:
            return _error(mid, -32002, "Unknown resource")
        index = load_index(root, engine)
        text, _truncated = cap_text(latest_digest(index))
        log_call(index["root"], "digest", "uri=brain://digest/latest", len(text.encode("utf-8")), 0, _truncated)
        result = {"contents": [{"uri": RESOURCE, "mimeType": "text/markdown", "text": text}]}
    elif method.startswith("notifications/"):
        return None
    else:
        return _error(mid, -32601, f"Method not found: {method}")
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve_stdio() -> None:
    root = _stdio_root()
    stdin = sys.stdin
    while True:
        line = stdin.readline()
        if line == "":
            break
        if line.lower().startswith("content-length:"):
            try:
                length = int(line.split(":", 1)[1].strip())
            except ValueError:
                continue
            while True:
                extra = stdin.readline()
                if extra in ("", "\n", "\r\n"):
                    break
            raw = stdin.read(length)
        else:
            if not line.strip():
                continue
            raw = line
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            continue
        response = dispatch(message, root, None)
        if response is None:
            continue
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _stdio_root() -> Path:
    import os

    raw = os.environ.get("BRAIN_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (REPO / "demo-projects").resolve()


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}
