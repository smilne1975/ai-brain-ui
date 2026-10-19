"""python -m backend.app --root C:\\path\\to\\projects"""

from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Start AI Brain UI")
    parser.add_argument("--root", help="Folder of projects to scan")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("BRAIN_PORT", "8741")))
    args = parser.parse_args()
    if args.root:
        os.environ["BRAIN_ROOT"] = args.root
    uvicorn.run("backend.app.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
