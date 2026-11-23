"""FastAPI surface for the local AI Brain dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend.app.activity import build_cards, build_timeline, narrate_cards, narrate_timeline, window_days
from backend.app.brief import build_brief, build_briefs, save_handoff
from backend.app.copilot_chats import load_chats, merge_chats
from backend.app.digest import build_digest, digest_mode, export_digest, write_scheduled
from backend.app.ask import answer
from backend.app.engine import Engine, Hub
from backend.app.llm import resolve_provider
from backend.app import agent_history, clips, deliverables, evidence, external_notes, knowledge, living_questions, meetings, obsidian, old_ideas, project_records, recall, scan_replay, voice, webhooks
from backend.app import capture, review_links
from backend.app.product import cad_matches_scan, legacy_cad_enabled
from backend.app.mcp_rpc import dispatch
from backend.app.mcp_tools import doctor_report, usage_report
from backend.app.privacy import active as private_folders_active, policy as privacy_policy
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
    project_ids: list[str] | None = Field(default=None, max_length=200)


class QuestionScope(BaseModel):
    question: str = Field(min_length=1, max_length=1600)
    project_ids: list[str] = Field(min_length=1, max_length=200)


class FollowQuestion(QuestionScope):
    challenge: str = Field(default="", max_length=280)


class QuestionChange(BaseModel):
    action: Literal["check", "accept", "snooze", "resume", "unfollow"]
    revision: int = Field(ge=1)


class OldIdeaFeedback(QuestionScope):
    id: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["keep", "dismiss", "snooze"]


class PageBody(BaseModel):
    content: str = Field(min_length=3, max_length=30000)
    expected_revision: str | None = None
    expected_sources: dict[str, str]
    topic: str | None = Field(default=None, max_length=80)
    source_ids: list[str] | None = Field(default=None, max_length=20)


class SkillBody(BaseModel):
    project_id: str
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=2, max_length=250)
    steps: str = Field(min_length=3, max_length=10000)


class AnswerPassage(BaseModel):
    id: str = Field(max_length=1000)
    excerpt: str = Field(max_length=400)
    page: int | None = Field(default=None, ge=1)


class AnswerBody(BaseModel):
    project_id: str
    title: str = Field(min_length=2, max_length=120)
    answer: str = Field(min_length=2, max_length=10000)
    source_ids: list[str] = Field(min_length=1, max_length=8)
    passages: list[AnswerPassage] = Field(default_factory=list, max_length=8)


class MeetingBody(BaseModel):
    notes: str = Field(min_length=1, max_length=50_000)


class MeetingEdit(BaseModel):
    line: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=500)
    owner: str | None = Field(default=None, max_length=120)
    due: str | None = Field(default=None, max_length=120)


class MeetingApproval(MeetingBody):
    source_name: str = Field(default="Pasted meeting notes", max_length=120)
    source_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: list[MeetingEdit] = Field(min_length=1, max_length=50)


class ClipBody(BaseModel):
    filename: str = Field(min_length=1, max_length=160)
    markdown: str = Field(min_length=1, max_length=40_000)


class ClipApproval(ClipBody):
    expected_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClipState(BaseModel):
    active: bool


class CaptureStage(BaseModel):
    filename: str = Field(max_length=160)
    text: str = Field(min_length=1, max_length=40_000)
    kind: Literal["note", "link", "clip"]


class CaptureChange(BaseModel):
    action: Literal["approve", "undo", "remove"]
    tags: str = Field(default="", max_length=200)
    filing: str = Field(default="", max_length=150)


class CaptureImage(BaseModel):
    filename: str = Field(max_length=160)
    data: str = Field(min_length=1, max_length=1_398_104)


class LinkReview(BaseModel):
    state: Literal["kept", "dismissed"]


class GroupRefresh(BaseModel):
    source_id: str = Field(min_length=1, max_length=1000)
    page_ids: list[str] = Field(min_length=1, max_length=8)


class GroupApproval(GroupRefresh):
    token: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_targets: dict[str, str] = Field(max_length=8)


class DeliverableBody(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    content: str = Field(min_length=1, max_length=80_000)
    page_ids: list[str] = Field(min_length=1, max_length=12)


class DeliverableExport(DeliverableBody):
    token: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeliverableAck(BaseModel):
    snapshot: str = Field(pattern=r"^[0-9a-f]{64}$")


class WorkflowPreview(BaseModel):
    type: str = Field(max_length=32)


class WorkflowPayload(WorkflowPreview):
    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    project_key: str = Field(max_length=40)
    created_at: str = Field(max_length=40)


class WorkflowSend(BaseModel):
    payload: WorkflowPayload
    expires: int
    confirmation: str = Field(pattern=r"^[0-9a-f]{64}$")


class VoiceEdit(BaseModel):
    segment: int = Field(ge=0, lt=160)
    kind: Literal["observation", "action"]
    text: str = Field(min_length=1, max_length=600)


class VoiceApproval(BaseModel):
    items: list[VoiceEdit] = Field(min_length=1, max_length=160)


class ObsidianExport(BaseModel):
    export_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    token: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProjectRecordBody(BaseModel):
    kind: Literal["decision", "constraint", "gotcha", "failed attempt", "fact", "handoff"]
    state: Literal["confirmed", "inferred", "unknown"] | None = None
    title: str = Field(min_length=1, max_length=140)
    text: str = Field(min_length=1, max_length=3000)
    next_step: str = Field(default="", max_length=1200)
    intended: str = Field(default="", max_length=120)
    source_ids: list[str] = Field(default_factory=list, max_length=12)
    memory_ids: list[str] = Field(default_factory=list, max_length=8)
    session_id: str | None = Field(default=None, max_length=256)
    expected_revision: int | None = Field(default=None, ge=1)


class ProjectRecordTransition(BaseModel):
    action: Literal["claim", "complete", "cancel"]
    actor: str = Field(min_length=1, max_length=120)
    expected_revision: int = Field(ge=1)


class RecallStartup(BaseModel):
    cwd: str = Field(min_length=1, max_length=2048)
    session: str = Field(default="", max_length=100)


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
        allow_origins=[] if private_folders_active() else ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        engine: Engine = app.state.engine
        return engine.status()

    @app.get("/api/brain")
    def get_brain():
        brain = _require_brain(app.state.engine)
        if not brain.get("private_policy"):
            return brain
        return {**{key: value for key, value in brain.items() if key not in {"private_policy", "signature"}},
                "privacy": "invalid" if brain["private_policy"] == "invalid" else "active"}

    @app.get("/api/timeline")
    def timeline(days: int = 7):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        payload = build_timeline(engine.root, brain, window_days(days))
        provider = resolve_provider()
        if provider:
            payload = narrate_timeline(provider, payload)
        payload = merge_chats(payload, load_chats(engine.root, brain))
        agent_sessions, warning = agent_history.load(brain)
        if agent_sessions:
            payload = merge_chats(payload, {"enabled": True, "sessions": agent_sessions})
        if warning:
            payload["agent_history_warning"] = warning
        return payload

    @app.get("/api/scan-replay")
    def replay(frame: int | None = Query(default=None, ge=1), project_id: str | None = None):
        engine: Engine = app.state.engine
        _require_brain(engine)
        try:
            return scan_replay.frames(engine.root, frame, project_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="This scan is no longer in the replay history") from None

    @app.get("/api/chats")
    def chats():
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        return load_chats(engine.root, brain)

    @app.get("/api/briefs")
    def briefs():
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        board = build_briefs(engine.root, brain, load_chats(engine.root, brain))
        if not private_folders_active():
            projects = {project["id"]: project for project in brain["projects"]}
            for entry in board["briefs"]:
                entry["reviewed_memory"] = project_records.brief_memory(engine.root, brain, projects[entry["project_id"]])
        return board

    @app.get("/api/brief/{project_id}")
    def brief(project_id: str):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            result = build_brief(engine.root, brain, project_id, load_chats(engine.root, brain))
            if not private_folders_active():
                project = next(project for project in brain["projects"] if project["id"] == project_id)
                result["reviewed_memory"] = project_records.brief_memory(engine.root, brain, project)
            return result
        except KeyError:
            raise HTTPException(status_code=404, detail="Folder is not in the scan") from None

    @app.post("/api/brief/{project_id}/handoff")
    def handoff(project_id: str):
        _require_sharing_enabled()
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
        _require_sharing_enabled()
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return export_digest(engine.root, brain, period, load_chats(engine.root, brain))
        except ValueError:
            raise HTTPException(status_code=400, detail="period must be day or week") from None
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Could not write the digest") from exc

    @app.get("/api/microstation/config")
    def microstation_config_index():
        _require_legacy_cad()
        engine: Engine = app.state.engine
        return _config_board(engine)

    @app.get("/api/microstation/config/{project_id}")
    def microstation_config_project(project_id: str):
        _require_legacy_cad()
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        known = {project["id"] for project in brain.get("projects") or []}
        if project_id not in known:
            raise HTTPException(status_code=404, detail="Folder is not in the scan")
        board = _config_board(engine)
        match = next((item for item in board["projects"] if item["project_id"] == project_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail="No MicroStation configuration in this folder")
        return match

    @app.get("/api/microstation")
    def microstation_index():
        _require_legacy_cad()
        engine: Engine = app.state.engine
        return _microstation_board(engine)

    @app.get("/api/microstation/{project_id}")
    def microstation_project(project_id: str):
        _require_legacy_cad()
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

    @app.get("/api/mcp/usage")
    def mcp_usage():
        _require_sharing_enabled()
        engine: Engine = app.state.engine
        return usage_report(engine.root, engine)

    @app.get("/api/mcp/doctor")
    def mcp_doctor():
        _require_sharing_enabled()
        engine: Engine = app.state.engine
        return doctor_report(engine.root, engine)

    @app.api_route("/mcp", methods=["GET", "POST"])
    async def mcp_endpoint(request: Request):
        engine: Engine = app.state.engine
        if request.method == "GET":
            return {
                "name": "AI Brain",
                "transport": "json-rpc",
                "protocolVersion": "2024-11-05",
                "note": "POST a JSON-RPC message. Tools are read-only and use the cached index.",
            }
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="MCP request must be JSON") from None
        if isinstance(body, list):
            answers = [item for item in (dispatch(message, engine.root, engine) for message in body) if item is not None]
            return JSONResponse(answers)
        answer = dispatch(body, engine.root, engine)
        if answer is None:
            return JSONResponse({"ok": True}, status_code=202)
        return JSONResponse(answer)

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
        if body.project_id and body.project_id not in {"all", "corpus"} and body.project_id not in {p["id"] for p in brain["projects"]}:
            raise HTTPException(status_code=404, detail="Folder is not in the scan")
        if body.project_ids is not None and any(pid not in {p["id"] for p in brain["projects"]} for pid in body.project_ids):
            raise HTTPException(status_code=404, detail="A selected folder is not in the scan")
        approved_clips = []
        scope = {body.project_id} if body.project_id not in {None, "all", "corpus"} else set(body.project_ids or ())
        projects = [project for project in brain["projects"] if not scope or project["id"] in scope]
        if not private_folders_active():
            for project in projects:
                try:
                    approved_clips.extend({**clip, "project_id": project["id"]}
                                          for clip in clips.list_clips(engine.root, project) if clip["active"])
                except (ValueError, OSError):
                    continue
                if len(approved_clips) >= 200:
                    break
        vault, warnings = external_notes.collect(projects) if body.question.strip() else ([], [])
        result = answer(brain, body.question, body.project_id, resolve_provider(), knowledge.pages(engine.root, brain),
                        knowledge.answers(engine.root, brain), body.project_ids, approved_clips[:200], vault,
                        origins=evidence.confirmed_origins(engine.root) if not private_folders_active() else None)
        if warnings:
            result["external_note_warnings"] = warnings
        return result

    def question_context() -> tuple[Engine, dict]:
        if private_folders_active():
            raise HTTPException(status_code=403, detail="Question tracking and old-idea review are off while private-folder exclusions are enabled")
        engine: Engine = app.state.engine
        return engine, _require_brain(engine)

    @app.get("/api/living-questions")
    def get_living_questions():
        engine, _ = question_context()
        try:
            return {"items": living_questions.list_questions(engine.root)}
        except (ValueError, sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Local question storage is unavailable") from None

    @app.post("/api/living-questions")
    def follow_question(body: FollowQuestion, request: Request):
        _require_local_origin(request)
        engine, brain = question_context()
        try:
            return living_questions.follow(engine.root, brain, body.question, body.project_ids, body.challenge)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except (sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Could not save this question locally") from None

    @app.post("/api/living-questions/{identifier}")
    def change_question(identifier: str, body: QuestionChange, request: Request):
        _require_local_origin(request)
        engine, brain = question_context()
        try:
            return living_questions.change(engine.root, brain, identifier, body.action, body.revision)
        except KeyError:
            raise HTTPException(status_code=404, detail="Followed question not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except (sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Could not update this question locally") from None

    @app.get("/api/old-ideas")
    def kept_ideas():
        engine, brain = question_context()
        try:
            return {"items": old_ideas.kept(engine.root, brain)}
        except (ValueError, sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Local idea storage is unavailable") from None

    @app.post("/api/old-ideas/preview")
    def preview_old_idea(body: QuestionScope, request: Request):
        _require_local_origin(request)
        engine, brain = question_context()
        try:
            scope = living_questions.scope_for(brain, body.project_ids)
            return {"idea": old_ideas.suggest(engine.root, brain, body.question, scope)}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except (sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Could not check the local notes") from None

    @app.post("/api/old-ideas/feedback")
    def old_idea_feedback(body: OldIdeaFeedback, request: Request):
        _require_local_origin(request)
        engine, brain = question_context()
        try:
            scope = living_questions.scope_for(brain, body.project_ids)
            item = old_ideas.suggest(engine.root, brain, body.question, scope)
            if not item or item["id"] != body.id:
                raise ValueError("The suggestion changed; check again before recording feedback")
            old_ideas.remember(engine.root, item, body.action)
            return {"ok": True}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except (sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Could not record feedback locally") from None

    @app.get("/api/knowledge")
    def knowledge_index():
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        pages = knowledge.pages(engine.root, brain)
        answers = knowledge.answers(engine.root, brain)
        available_clips = []
        if not private_folders_active():
            for project in brain["projects"]:
                try:
                    available_clips.extend({"id": clips.reference(project["id"], clip["id"]), "title": clip["title"],
                                            "project_id": project["id"]}
                                           for clip in clips.list_clips(engine.root, project) if clip["active"])
                except (ValueError, OSError):
                    continue
        return {"pages": pages, "answers": answers, "available_clips": available_clips,
                 "source_impact": knowledge.source_impact(engine.root, brain, pages, answers),
                 "findings": knowledge.lint(engine.root, brain),
                 "workflow_candidates": knowledge.workflow_candidates(brain, load_chats(engine.root, brain), agent_history.load(brain)[0])}

    def inbox_project(project_id: str) -> tuple[Engine, dict]:
        if private_folders_active():
            raise HTTPException(status_code=403, detail="Imports are unavailable while private-folder exclusions are enabled")
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        project = next((item for item in brain["projects"] if item["id"] == project_id), None)
        if not project:
            raise HTTPException(status_code=404, detail="Folder is not in the scan")
        return engine, project

    @app.get("/api/source-review/{project_id}")
    def source_review(project_id: str):
        engine, project = inbox_project(project_id)
        brain = _require_brain(engine)
        try:
            decisions = [{**row, "project_id": project_id} for row in project_records.board(engine.root, brain, project)["items"]
                         if row["kind"] == "decision" and row["state"] == "reviewed"]
            impacts = knowledge.source_impact(engine.root, brain, knowledge.pages(engine.root, brain),
                knowledge.answers(engine.root, brain), decisions, living_questions.list_questions(engine.root))
            return {"items": [row for row in impacts if any(item["project_id"] == project_id for item in row["affected"])],
                    "limited": bool(brain.get("truncated") or brain.get("coverage", {}).get("issues"))}
        except (ValueError, sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Could not read all local review records") from None

    @app.get("/api/link-review/{project_id}")
    def link_suggestions(project_id: str):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return review_links.listing(engine.root, brain, knowledge._project(brain, project_id))
        except (ValueError, sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Could not read link suggestions for this project") from None

    @app.post("/api/source-review/{project_id}/preview")
    def preview_group(project_id: str, body: GroupRefresh, request: Request):
        _require_local_origin(request)
        engine, _ = inbox_project(project_id)
        try:
            return knowledge.grouped_refresh(engine.root, _require_brain(engine), project_id, body.source_id, body.page_ids)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except OSError:
            raise HTTPException(status_code=409, detail="Could not read the selected pages") from None

    @app.post("/api/source-review/{project_id}/approve")
    def approve_group(project_id: str, body: GroupApproval, request: Request):
        _require_local_origin(request)
        engine, _ = inbox_project(project_id)
        try:
            return knowledge.grouped_refresh(engine.root, _require_brain(engine), project_id, body.source_id, body.page_ids,
                                             body.token, body.expected_targets)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except OSError:
            raise HTTPException(status_code=409, detail="Could not save the selected revisions; the approved group was not changed") from None

    @app.post("/api/link-review/{project_id}/{identifier}")
    def review_link(project_id: str, identifier: str, body: LinkReview, request: Request):
        _require_local_origin(request)
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return review_links.review(engine.root, brain, knowledge._project(brain, project_id), identifier, body.state)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except (sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Could not save your link review") from None

    @app.get("/api/captures/{project_id}")
    def captures(project_id: str):
        engine, project = inbox_project(project_id)
        try:
            return {"items": capture.listing(engine.root, project)}
        except (ValueError, sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Could not read the capture queue") from None

    @app.post("/api/captures/{project_id}")
    def stage_capture(project_id: str, body: CaptureStage, request: Request):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        try:
            return capture.stage(engine.root, project, body.text, body.filename, body.kind)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except (sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Capture storage is unavailable") from None

    @app.post("/api/captures/{project_id}/{identifier}")
    def change_capture(project_id: str, identifier: str, body: CaptureChange, request: Request):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        try:
            return capture.change(engine.root, project, identifier, body.action, body.tags, body.filing)
        except KeyError:
            raise HTTPException(status_code=404, detail="Capture or referenced clip not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except (sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Could not update the capture") from None

    @app.post("/api/capture-images/{project_id}")
    def stage_capture_image(project_id: str, body: CaptureImage, request: Request):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        try:
            return capture.stage_image(engine.root, project, body.data, body.filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except (sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Capture storage is unavailable") from None

    @app.get("/api/captures/{project_id}/{identifier}/image")
    def capture_image(project_id: str, identifier: str):
        engine, project = inbox_project(project_id)
        try:
            return Response(capture.read_image(engine.root, project, identifier), media_type="image/png",
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                     "Cross-Origin-Resource-Policy": "same-origin"})
        except (KeyError, ValueError):
            raise HTTPException(status_code=404, detail="Capture image unavailable") from None
        except (sqlite3.Error, OSError):
            raise HTTPException(status_code=409, detail="Could not read the capture") from None

    @app.get("/api/meetings/{project_id}")
    def meeting_items(project_id: str):
        engine, project = inbox_project(project_id)
        try:
            return {"items": meetings.list_items(engine.root, project)}
        except (ValueError, OSError):
            raise HTTPException(status_code=409, detail="Meeting storage is not available") from None

    @app.post("/api/meetings/{project_id}/preview")
    def meeting_preview(project_id: str, body: MeetingBody, request: Request):
        _require_local_origin(request)
        inbox_project(project_id)
        return meetings.draft(body.notes)

    @app.post("/api/meetings/{project_id}/approve")
    def meeting_approve(project_id: str, body: MeetingApproval, request: Request):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        try:
            return meetings.approve(engine.root, project, body.notes, body.source_name,
                                    body.source_id, [item.model_dump() for item in body.items])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except OSError:
            raise HTTPException(status_code=500, detail="Could not save meeting items") from None

    @app.get("/api/web-clips/{project_id}")
    def clip_list(project_id: str):
        engine, project = inbox_project(project_id)
        try:
            return {"items": clips.list_clips(engine.root, project)}
        except (ValueError, OSError):
            raise HTTPException(status_code=409, detail="Web clip storage is not available") from None

    @app.post("/api/web-clips/{project_id}/preview")
    def clip_preview(project_id: str, body: ClipBody, request: Request):
        _require_local_origin(request)
        inbox_project(project_id)
        try:
            return clips.preview(body.markdown, body.filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/api/web-clips/{project_id}/approve")
    def clip_approve(project_id: str, body: ClipApproval, request: Request):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        try:
            clip, created = clips.import_clip(engine.root, project, body.markdown, body.filename, body.expected_id)
            return {"clip": clip, "created": created}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except OSError:
            raise HTTPException(status_code=500, detail="Could not save web clip") from None

    @app.post("/api/web-clips/{project_id}/{clip_id}/state")
    def clip_state(project_id: str, clip_id: str, body: ClipState, request: Request):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        try:
            return clips.set_active(engine.root, project, clip_id, body.active)
        except KeyError:
            raise HTTPException(status_code=404, detail="Clip not found") from None
        except (ValueError, OSError):
            raise HTTPException(status_code=400, detail="Could not change clip state") from None

    @app.get("/api/deliverables/{project_id}")
    def deliverable_list(project_id: str):
        _require_sharing_enabled()
        engine, project = inbox_project(project_id)
        try:
            return {"items": deliverables.list_exports(engine.root, _require_brain(engine), project)}
        except (ValueError, OSError):
            raise HTTPException(status_code=409, detail="Deliverable storage is not available") from None

    @app.post("/api/deliverables/{project_id}/preview")
    def deliverable_preview(project_id: str, body: DeliverableBody, request: Request):
        _require_local_origin(request)
        _require_sharing_enabled()
        engine, project = inbox_project(project_id)
        try:
            return deliverables.preview(engine.root, _require_brain(engine), project, body.title, body.content, body.page_ids)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

    @app.post("/api/deliverables/{project_id}/export")
    def deliverable_export(project_id: str, body: DeliverableExport, request: Request):
        _require_local_origin(request)
        _require_sharing_enabled()
        engine, project = inbox_project(project_id)
        try:
            return deliverables.export(engine.root, _require_brain(engine), project, body.title, body.content, body.page_ids, body.token)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except OSError:
            raise HTTPException(status_code=500, detail="Could not write the deliverable and evidence record") from None

    @app.post("/api/deliverables/{project_id}/{identifier}/acknowledge")
    def deliverable_acknowledge(project_id: str, identifier: str, body: DeliverableAck, request: Request):
        _require_local_origin(request)
        _require_sharing_enabled()
        engine, project = inbox_project(project_id)
        try:
            return deliverables.acknowledge(engine.root, _require_brain(engine), project, identifier, body.snapshot)
        except KeyError:
            raise HTTPException(status_code=404, detail="Deliverable not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except OSError:
            raise HTTPException(status_code=500, detail="Could not record review") from None

    @app.get("/api/workflow-events/{project_id}")
    def workflow_events(project_id: str):
        _require_sharing_enabled()
        engine, project = inbox_project(project_id)
        try:
            return webhooks.list_events(engine.root, project)
        except (ValueError, OSError):
            raise HTTPException(status_code=409, detail="Workflow event history is not available") from None

    @app.post("/api/workflow-events/{project_id}/preview")
    def workflow_preview(project_id: str, body: WorkflowPreview, request: Request):
        _require_local_origin(request)
        _require_sharing_enabled()
        _, project = inbox_project(project_id)
        try:
            return webhooks.preview(project, body.type)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

    @app.post("/api/workflow-events/{project_id}/send")
    def workflow_send(project_id: str, body: WorkflowSend, request: Request):
        _require_local_origin(request)
        _require_sharing_enabled()
        engine, project = inbox_project(project_id)
        try:
            return webhooks.send(engine.root, project, body.payload.model_dump(), body.expires, body.confirmation)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except OSError:
            raise HTTPException(status_code=500, detail="Could not persist delivery; do not assume the event was sent") from None

    @app.post("/api/workflow-events/{project_id}/{event_id}/retry")
    def workflow_retry(project_id: str, event_id: str, request: Request):
        _require_local_origin(request)
        _require_sharing_enabled()
        engine, project = inbox_project(project_id)
        try:
            return webhooks.retry(engine.root, project, event_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Workflow event not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except OSError:
            raise HTTPException(status_code=500, detail="Could not persist delivery; do not assume the event was sent") from None

    @app.get("/api/voice-notes/{project_id}")
    def voice_list(project_id: str):
        engine, project = inbox_project(project_id)
        try:
            return {"available": voice.available(), "items": voice.items(engine.root, project)}
        except (ValueError, OSError):
            raise HTTPException(status_code=409, detail="Voice-note storage is not available") from None

    @app.post("/api/voice-notes/{project_id}/preview")
    async def voice_preview(project_id: str, request: Request, filename: str = Query(default="Voice memo.wav", max_length=160)):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        if not voice.available():
            raise HTTPException(status_code=409, detail="Local speech recognition is not configured; no cloud fallback is available")
        if request.headers.get("content-type", "").split(";", 1)[0] != "audio/wav":
            raise HTTPException(status_code=415, detail="Choose a valid WAV audio file")
        audio = bytearray()
        async for part in request.stream():
            if len(audio) + len(part) > voice.MAX_BYTES:
                raise HTTPException(status_code=413, detail="File exceeds the 24 MiB audio limit")
            audio.extend(part)
        try:
            return await run_in_threadpool(voice.draft, engine.root, project, bytes(audio), filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/api/voice-notes/{project_id}/{identifier}/approve")
    def voice_approve(project_id: str, identifier: str, body: VoiceApproval, request: Request):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        try:
            return voice.approve(engine.root, project, identifier, [item.model_dump() for item in body.items])
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except OSError:
            raise HTTPException(status_code=500, detail="Could not save the selected notes and original audio") from None

    @app.post("/api/voice-notes/{project_id}/{identifier}/discard")
    def voice_discard(project_id: str, identifier: str, request: Request):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        voice.discard(engine.root, project, identifier)
        return {"ok": True}

    @app.get("/api/voice-notes/{project_id}/{identifier}/audio")
    def voice_audio(project_id: str, identifier: str):
        engine, project = inbox_project(project_id)
        try:
            return FileResponse(voice.audio_path(engine.root, project, identifier), media_type="audio/wav",
                                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        except (ValueError, OSError):
            raise HTTPException(status_code=404, detail="Approved original audio not found") from None

    @app.get("/api/obsidian/{project_id}/preview")
    def obsidian_preview(project_id: str):
        _require_sharing_enabled()
        engine, project = inbox_project(project_id)
        return obsidian.preview(engine.root, _require_brain(engine), project)

    @app.post("/api/obsidian/{project_id}/download")
    def obsidian_download(project_id: str, body: ObsidianExport, request: Request):
        _require_local_origin(request)
        _require_sharing_enabled()
        engine, project = inbox_project(project_id)
        try:
            name, content = obsidian.archive(engine.root, _require_brain(engine), project, body.export_id, body.token)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return Response(content, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                                         "Cache-Control": "no-store"})

    @app.get("/api/project-records/{project_id}")
    def project_record_list(project_id: str):
        engine, project = inbox_project(project_id)
        try:
            return project_records.board(engine.root, _require_brain(engine), project)
        except (ValueError, OSError):
            raise HTTPException(status_code=409, detail="Project record storage is unavailable") from None

    @app.get("/api/project-records/{project_id}/sessions")
    def project_record_sessions(project_id: str):
        engine, project = inbox_project(project_id)
        brain = _require_brain(engine)
        chat_index = load_chats(engine.root, brain)
        exports, warning = agent_history.load(brain)
        return {"items": [{key: session.get(key) for key in ("id", "title", "when")}
                          for session in [*chat_index["sessions"], *exports] if session.get("project_id") == project["id"]][:40],
                "incomplete": not chat_index["enabled"] or chat_index["truncated"] or bool(warning)}

    @app.get("/api/project-records/{project_id}/recall")
    def project_recall_preview(project_id: str, layer: str = "recent", budget: int = 600,
                               record_ids: list[str] | None = Query(default=None, max_length=20)):
        engine, project = inbox_project(project_id)
        if not recall.enabled():
            return {"enabled": False, "payload": None, "receipts": []}
        try:
            payload = recall.pack(engine.root, _require_brain(engine), project, layer, budget, record_ids)
            return {"enabled": True, "payload": payload, "receipts": project_records.receipts(engine.root, project)}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

    @app.post("/api/project-records/{project_id}/session-start")
    def project_recall_startup(project_id: str, body: RecallStartup, request: Request):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        if not recall.startup_allowed(engine.root, project, body.cwd):
            return {}
        context = recall.response(engine.root, _require_brain(engine), project, "recent", 600, [], body.session,
                                  integration="Copilot sessionStart")
        if not context["items"]:
            return {}
        return {"additionalContext": json.dumps(context, ensure_ascii=False)}

    def save_project_record(project_id: str, body: ProjectRecordBody, request: Request, identifier: str | None = None):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        brain = _require_brain(engine)
        payload = body.model_dump()
        if body.session_id is not None and body.kind == "handoff":
            available = (agent_history.load(brain)[0] if body.session_id.startswith("agent-export:") else
                         load_chats(engine.root, brain)["sessions"])
            session = next((row for row in available if row.get("id") == body.session_id and row.get("project_id") == project_id), None)
            if not session:
                raise HTTPException(status_code=409, detail="Session evidence is unavailable; leave it unset to save a manual handoff")
            payload["session"] = {key: session.get(key) for key in ("id", "title", "when")}
        try:
            return project_records.save(engine.root, brain, project, payload, identifier, body.expected_revision)
        except KeyError:
            raise HTTPException(status_code=404, detail="Project record or selected memory was not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

    @app.post("/api/project-records/{project_id}")
    def project_record_add(project_id: str, body: ProjectRecordBody, request: Request):
        return save_project_record(project_id, body, request)

    @app.post("/api/project-records/{project_id}/{identifier}/edit")
    def project_record_edit(project_id: str, identifier: str, body: ProjectRecordBody, request: Request):
        return save_project_record(project_id, body, request, identifier)

    @app.post("/api/project-records/{project_id}/{identifier}/transition")
    def project_record_transition(project_id: str, identifier: str, body: ProjectRecordTransition, request: Request):
        _require_local_origin(request)
        engine, project = inbox_project(project_id)
        try:
            return project_records.transition(engine.root, project, identifier, body.action, body.actor, body.expected_revision)
        except KeyError:
            raise HTTPException(status_code=404, detail="Handoff was not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

    @app.post("/api/answers")
    def save_reviewed_answer(body: AnswerBody, request: Request):
        _require_local_origin(request)
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return knowledge.save_answer(engine.root, brain, body.project_id, body.title, body.answer, body.source_ids,
                                         [item.model_dump() for item in body.passages])
        except StopIteration:
            raise HTTPException(status_code=404, detail="Folder is not in the scan") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except FileExistsError:
            raise HTTPException(status_code=409, detail="Saved answer already exists; nothing was overwritten") from None

    @app.get("/api/knowledge/{project_id}/preview")
    def knowledge_preview(project_id: str, topic: str | None = None, source_ids: list[str] | None = Query(default=None)):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return knowledge.preview(engine.root, brain, project_id, topic, source_ids)
        except StopIteration:
            raise HTTPException(status_code=404, detail="Folder is not in the scan") from None

    @app.post("/api/knowledge/{project_id}/review")
    def knowledge_review(project_id: str, body: PageBody, request: Request):
        _require_local_origin(request)
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return knowledge.review_report(engine.root, brain, project_id, body.content, body.expected_revision,
                                           body.expected_sources, body.topic, body.source_ids)
        except StopIteration:
            raise HTTPException(status_code=404, detail="Folder is not in the scan") from None

    @app.post("/api/knowledge/{project_id}/approve")
    def knowledge_approve(project_id: str, body: PageBody, request: Request):
        _require_local_origin(request)
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return knowledge.approve(engine.root, brain, project_id, body.content, body.expected_revision, body.expected_sources,
                                     body.topic, body.source_ids)
        except StopIteration:
            raise HTTPException(status_code=404, detail="Folder is not in the scan") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Could not save the reviewed page") from exc

    @app.post("/api/skills/reviewed")
    def reviewed_skill(body: SkillBody, request: Request):
        _require_local_origin(request)
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        try:
            return knowledge.save_skill(engine.root, brain, body.project_id, body.name, body.description, body.steps)
        except StopIteration:
            raise HTTPException(status_code=404, detail="Folder is not in the scan") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except FileExistsError:
            raise HTTPException(status_code=409, detail="Skill already exists; existing content was not replaced") from None

    @app.get("/api/file")
    def read_file(file_id: str):
        engine: Engine = app.state.engine
        brain = _require_brain(engine)
        rec = next((item for item in brain["files"] if item["id"] == file_id), None)
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
    if private_folders_active() or digest_mode() is None:
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


def _config_board(engine: Engine) -> dict:
    brain = _require_brain(engine)
    if private_folders_active():
        return {"projects": []}
    projects = brain.get("projects") or []
    if projects and all("microstation_config" in project for project in projects):
        return {"projects": [project["microstation_config"] for project in projects if project.get("microstation_config")]}
    from backend.app.microstation_config import build_config

    return build_config(engine.root, projects, brain.get("files") or [])


def _microstation_board(engine: Engine) -> dict:
    brain = _require_brain(engine)
    if private_folders_active():
        return {"projects": []}
    projects = brain.get("projects") or []
    if projects and all("microstation" in project for project in projects):
        return {"projects": [project["microstation"] for project in projects if project.get("microstation")]}
    from backend.app.microstation import build_microstation

    return build_microstation(engine.root, projects, brain.get("files") or [])


def _require_brain(engine: Engine) -> dict:
    brain = engine.brain
    token = privacy_policy(engine.root).token
    if brain and brain.get("private_policy") == token and cad_matches_scan(brain, token):
        return brain
    if engine.phase in {"scanning", "starting"}:
        raise HTTPException(status_code=503, detail="Still scanning this folder.")
    raise HTTPException(status_code=404, detail=engine.error or "Not scanned")


def _require_legacy_cad() -> None:
    if not legacy_cad_enabled() or private_folders_active():
        raise HTTPException(status_code=404, detail="MicroStation tools belong in MicroStationBot; legacy compatibility is off")


def _require_sharing_enabled() -> None:
    if private_folders_active():
        raise HTTPException(status_code=403, detail="Sharing is unavailable while private-folder exclusions are enabled")


def _require_local_origin(request: Request) -> None:
    """Block cross-site browser writes to the local, unauthenticated server."""
    origin = request.headers.get("origin")
    if not origin:
        return  # local CLI and same-origin requests that omit Origin
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=403, detail="Knowledge writes require a local page")


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
