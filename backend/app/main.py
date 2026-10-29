"""FastAPI surface for the local AI Brain dashboard."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.app.activity import build_cards, build_timeline, narrate_cards, narrate_timeline, window_days
from backend.app.brief import build_brief, build_briefs, save_handoff
from backend.app.copilot_chats import load_chats, merge_chats
from backend.app.digest import build_digest, digest_mode, export_digest, write_scheduled
from backend.app.ask import answer
from backend.app.engine import Engine, Hub
from backend.app.llm import resolve_provider
from backend.app.microstation import build_microstation
from backend.app.scanner import file_excerpt

log = logging.getLogger("brain")
REPO = Path(__file__).resolve().parents[2]
DIST = REPO / "frontend" / "dist"
DEFAULT_ROOT = REPO / "demo-projects"

MISSING_UI = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>AI Brain</title>
<style>
body { margin: 0; background: #070807; color: #e7f6ee; font: 16px/1.5 Segoe UI, sans-serif; }
main { max-width: 38rem; margin: 12vh auto; padding: 0 1.5rem; }
h1 { font-weight: 600; letter-spacing: -0.04em; }
code { color: #3dff9a; }
</style></head>
<body><main>
<h1>AI Brain</h1>
<p>The API is up, and the UI has not been built yet.</p>
<p>From the repo root run <code>npm install</code> and <code>npm run build</code> inside <code>frontend</code>, then refresh. On Windows, <code>start.bat</code> does this.</p>
</main></body></html>"""


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    project_id: str | None = None


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        hub = Hub()
        hub.bind(asyncio.get_running_loop())
        raw = os.environ.get("BRAIN_ROOT", "").strip()
        root = Path(raw).expanduser() if raw else DEFAULT_ROOT
        engine = Engine(root, hub)
        app.state.engine = engine
        app.state.hub = hub
        engine.open()
        log.info("serving %s while the folder scan runs", engine.root)
        digest_task = asyncio.create_task(_digest_scheduler(engine))
        yield
        digest_task.cancel()
        engine.close()

    app = FastAPI(title="AI Brain", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        engine: Engine = app.state.engine
        return engine.status()

    @app.get("/api/brain")
    def get_brain():
        return _require_brain(app.state.engine)

    @app.get("/api/timeline")
    def timeline(days: int = 7):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        payload = build_timeline(engine.root, brain, window_days(days))
        provider = resolve_provider()
        if provider:
            payload = narrate_timeline(provider, payload)
        return merge_chats(payload, load_chats(engine.root, brain))

    @app.get("/api/chats")
    def chats():
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        return load_chats(engine.root, brain)

    @app.get("/api/briefs")
    def briefs():
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        return build_briefs(engine.root, brain, load_chats(engine.root, brain))

    @app.get("/api/brief/{project_id}")
    def brief(project_id: str):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return build_brief(engine.root, brain, project_id, load_chats(engine.root, brain))
        except KeyError:
            raise HTTPException(status_code=404, detail="Folder is not in the scan") from None

    @app.post("/api/brief/{project_id}/handoff")
    def handoff(project_id: str):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return save_handoff(engine.root, brain, project_id, load_chats(engine.root, brain))
        except KeyError:
            raise HTTPException(status_code=404, detail="Folder is not in the scan") from None
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Could not write BRAIN_HANDOFF.md") from exc

    @app.get("/api/digest")
    def digest(period: str = "week"):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return build_digest(engine.root, brain, period, load_chats(engine.root, brain))
        except ValueError:
            raise HTTPException(status_code=400, detail="period must be day or week") from None

    @app.post("/api/digest/export")
    def digest_export(period: str = "week"):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return export_digest(engine.root, brain, period, load_chats(engine.root, brain))
        except ValueError:
            raise HTTPException(status_code=400, detail="period must be day or week") from None
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Could not write the digest") from exc

    @app.get("/api/microstation")
    def microstation_index():
        engine: Engine = app.state.engine
        return _microstation_board(engine)

    @app.get("/api/microstation/{project_id}")
    def microstation_project(project_id: str):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        known = {project["id"] for project in brain.get("projects") or []}
        if project_id not in known:
            raise HTTPException(status_code=404, detail="Folder is not in the scan")
        board = _microstation_board(engine)
        match = next((item for item in board["projects"] if item["project_id"] == project_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail="Not a MicroStation Python project")
        return match

    @app.get("/api/cards")
    def cards():
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        payload = build_cards(engine.root, brain)
        provider = resolve_provider()
        if provider:
            payload = narrate_cards(provider, payload)
        return payload

    @app.post("/api/rescan")
    def rescan():
        engine: Engine = app.state.engine
        try:
            return JSONResponse(engine.request_scan(force=True), status_code=202)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=engine.error or "Folder does not exist") from None

    @app.post("/api/ask")
    def ask(body: AskBody):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        return answer(brain, body.question, body.project_id, resolve_provider())

    @app.get("/api/file")
    def read_file(file_id: str):
        engine: Engine = app.state.engine
        _require_brain(engine)
        rec = next((item for item in engine.brain["files"] if item["id"] == file_id), None)
        if rec is None:
            raise HTTPException(status_code=404, detail="File is not in the index")
        payload = file_excerpt(engine.root, rec)
        payload["summary"] = rec["summary"]
        payload["skills"] = rec["skills"]
        payload["todos"] = rec["todos"]
        payload["env_keys"] = rec["env_keys"]
        return payload

    @app.get("/api/events")
    async def events(request: Request):
        hub: Hub = app.state.hub
        queue: asyncio.Queue = asyncio.Queue(maxsize=20)
        hub.add(queue)

        async def gen():
            try:
                yield "data: {\"type\":\"hello\"}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    yield f"data: {message}\n\n"
            finally:
                hub.remove(queue)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/")
    def index():
        return _spa("")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        return _spa(full_path)

    return app


async def _digest_scheduler(engine: Engine) -> None:
    if digest_mode() is None:
        return
    try:
        while True:
            if engine.brain:
                try:
                    written = write_scheduled(engine.root, engine.brain)
                    if written:
                        log.info("wrote scheduled digest %s", written)
                except Exception:
                    log.exception("scheduled digest failed")
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        return


def _microstation_board(engine: Engine) -> dict:
    brain = _require_brain(engine)
    projects = brain.get("projects") or []
    if projects and all("microstation" in project for project in projects):
        return {"projects": [project["microstation"] for project in projects if project.get("microstation")]}
    return build_microstation(engine.root, projects, brain.get("files") or [])


def _require_brain(engine: Engine) -> dict:
    if engine.brain:
        return engine.brain
    if engine.phase in {"scanning", "starting"}:
        raise HTTPException(status_code=503, detail="Still scanning this folder.")
    raise HTTPException(status_code=404, detail=engine.error or "Not scanned")


def _spa(full_path: str):
    if not DIST.exists():
        return HTMLResponse(MISSING_UI, status_code=503)
    if full_path:
        candidate = (DIST / full_path).resolve()
        try:
            candidate.relative_to(DIST.resolve())
        except ValueError:
            raise HTTPException(status_code=404) from None
        if candidate.is_file():
            return FileResponse(candidate)
    index = DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return HTMLResponse(MISSING_UI, status_code=503)


app = create_app()
