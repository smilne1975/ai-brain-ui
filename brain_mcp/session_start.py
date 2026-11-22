"""Optional GitHub Copilot sessionStart hook; talks only to AI Brain on loopback."""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
from urllib.parse import quote


def startup_event(event: object) -> dict | None:
    if not isinstance(event, dict) or event.get("source") not in ("startup", "resume", "new"):
        return None
    if event.get("hook_event_name", "SessionStart") != "SessionStart":
        return None
    cwd, session = event.get("cwd"), event.get("sessionId", event.get("session_id", ""))
    if not isinstance(cwd, str) or not 1 <= len(cwd) <= 2048 or not isinstance(session, str):
        return None
    # Never forward the initial prompt or any other event fields.
    return {"cwd": cwd, "session": session[:100]}


def request_context(event: object, project: str, port: int = 8741) -> dict:
    payload = startup_event(event)
    if not payload or not (1 <= port <= 65535) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", project):
        return {}
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        conn.request("POST", f"/api/project-records/{quote(project, safe='')}/session-start", json.dumps(payload),
                     {"Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status != 200:  # no redirects or remote fallback
            return {}
        body = response.read(12_001)
        if len(body) > 12_000:
            return {}
        received = json.loads(body)
        context = received.get("additionalContext") if isinstance(received, dict) else None
        return {"additionalContext": context} if isinstance(context, str) and context.strip() else {}
    except (OSError, ValueError, http.client.HTTPException):
        return {}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--port", type=int, default=8741)
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(64_001)
        event = json.loads(raw) if len(raw) <= 64_000 else None
    except (ValueError, OSError):
        event = None
    print(json.dumps(request_context(event, args.project, args.port)))


if __name__ == "__main__":
    main()
