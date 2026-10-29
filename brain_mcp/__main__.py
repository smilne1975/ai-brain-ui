"""python -m brain_mcp

Speaks MCP JSON-RPC on stdin/stdout. Uses BRAIN_ROOT and BRAIN_CACHE, and
does not start a scan.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.mcp_rpc import serve_stdio


def main() -> None:
    serve_stdio()


if __name__ == "__main__":
    main()
