"""Scan lifecycle: cache, file watcher, optional model summaries."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path

from backend.app.llm import public_provider, resolve_provider, summarize_projects
from backend.app.scanner import build_brain, ignored_dir_name, signature
from backend.app import store

log = logging.getLogger("brain")


class Hub:
    """Fan-out for server-sent events, safe to call from watcher threads."""

    def __init__(self) -> None:
        self.queues: list[asyncio.Queue] = []
        self.loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def add(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self.queues.append(queue)

    def remove(self, queue: asyncio.Queue) -> None:
        with self._lock:
            if queue in self.queues:
                self.queues.remove(queue)

    def publish(self, message: str) -> None:
        loop = self.loop
        if loop is None:
            return

        def fan() -> None:
            with self._lock:
                queues = list(self.queues)
            for queue in queues:
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    pass

        loop.call_soon_threadsafe(fan)


class Engine:
    def __init__(self, root: Path, hub: Hub) -> None:
        self.root = root.expanduser().resolve()
        self.hub = hub
        self.brain: dict | None = None
        self.error: str | None = None
        self.phase = "starting"
        self.lock = threading.Lock()
        self.observer = None
        self._timer: threading.Timer | None = None
        self._timer_lock = threading.Lock()
        self._generation = 0
        self._rescan_pending = False
        self._pending_force = False
        self._worker_alive = False
        self._last_publish = 0.0
        self.progress: dict = {
            "phase": "starting",
            "root": str(self.root),
            "root_name": self.root.name,
            "message": "Starting",
            "files": 0,
            "projects": 0,
            "current": "",
            "generation": 0,
        }

    def open(self) -> None:
        try:
            self.request_scan(force=False)
        except FileNotFoundError:
            log.warning(self.error)
            return
        if os.getenv("BRAIN_DISABLE_WATCH") != "1":
            self._start_watch()

    def close(self) -> None:
        with self.lock:
            self._generation += 1
        with self._timer_lock:
            if self._timer:
                self._timer.cancel()
        if self.observer is not None:
            self.observer.stop()
            self.observer.join(timeout=2)
            self.observer = None

    def request_scan(self, force: bool) -> dict:
        """Start a scan on a background thread and return immediately."""
        if not self.root.exists() or not self.root.is_dir():
            message = f"Folder does not exist: {self.root}"
            with self.lock:
                self.error = message
                self.phase = "error"
                self.progress.update(phase="error", message=message, current="")
                snapshot = self._status_unlocked()
            self.hub.publish(json.dumps({"type": "progress", **self._public_progress(snapshot)}))
            raise FileNotFoundError(self.root)
        with self.lock:
            if self._worker_alive:
                self._rescan_pending = True
                self._pending_force = self._pending_force or force
                return self._status_unlocked()
            self._generation += 1
            generation = self._generation
            self._worker_alive = True
            self._rescan_pending = False
            self._pending_force = False
            self.error = None
            self.phase = "scanning"
            self.progress.update(
                phase="scanning",
                root=str(self.root),
                root_name=self.root.name,
                message="Starting scan",
                files=0,
                projects=0,
                current="",
                generation=generation,
            )
            snapshot = self._status_unlocked()
        threading.Thread(
            target=self._scan_worker,
            args=(force, generation),
            daemon=True,
            name="brain-scan",
        ).start()
        return snapshot

    def status(self) -> dict:
        with self.lock:
            return self._status_unlocked()

    def _status_unlocked(self) -> dict:
        progress = dict(self.progress)
        phase = self.phase
        payload = {
            "ok": phase == "ready" and self.brain is not None,
            "phase": phase,
            "root": progress.get("root") or str(self.root),
            "root_name": progress.get("root_name") or self.root.name,
            "message": self.error or progress.get("message") or "",
            "files": progress.get("files") or 0,
            "projects": progress.get("projects") or 0,
            "current": progress.get("current") or "",
            "generation": self._generation,
            "truncated": False,
        }
        if self.error:
            payload["error"] = self.error
        brain = self.brain
        if brain and phase == "ready":
            payload.update(
                {
                    "root": brain["root"],
                    "root_name": brain["root_name"],
                    "provider": brain["provider"],
                    "summaries": brain.get("summaries"),
                    "projects": brain["stats"]["projects"],
                    "files": brain["stats"]["files"],
                    "scanned_at": brain["scanned_at"],
                    "truncated": bool(brain.get("truncated")),
                    "message": "Mapped",
                }
            )
        return payload

    def _public_progress(self, snapshot: dict) -> dict:
        return {
            "phase": snapshot["phase"],
            "root": snapshot["root"],
            "root_name": snapshot["root_name"],
            "message": snapshot["message"],
            "files": snapshot["files"],
            "projects": snapshot["projects"],
            "current": snapshot["current"],
            "generation": snapshot["generation"],
        }

    def _report(self, generation: int, info: dict) -> None:
        with self.lock:
            if generation != self._generation:
                return
            for key in ("message", "files", "projects", "current"):
                if key in info:
                    self.progress[key] = info[key]
            self.progress["phase"] = "scanning"
            snapshot = self._status_unlocked()
            now = time.monotonic()
            if now - self._last_publish < 0.3:
                return
            self._last_publish = now
        self.hub.publish(json.dumps({"type": "progress", **self._public_progress(snapshot)}))

    def _scan_worker(self, force: bool, generation: int) -> None:
        follow_up: bool | None = None
        try:
            brain = self._load_or_scan(force, lambda info: self._report(generation, info))
        except FileNotFoundError:
            message = f"Folder does not exist: {self.root}"
            with self.lock:
                if generation != self._generation:
                    self._worker_alive = False
                    return
                self.error = message
                self.phase = "error"
                self.progress.update(phase="error", message=message)
                self._worker_alive = False
                snapshot = self._status_unlocked()
            self.hub.publish(json.dumps({"type": "progress", **self._public_progress(snapshot)}))
            return
        except Exception:
            log.exception("scan failed")
            with self.lock:
                if generation != self._generation:
                    self._worker_alive = False
                    return
                self.error = "The folder could not be scanned."
                self.phase = "error"
                self.progress.update(phase="error", message=self.error)
                self._worker_alive = False
                snapshot = self._status_unlocked()
            self.hub.publish(json.dumps({"type": "progress", **self._public_progress(snapshot)}))
            return
        with self.lock:
            if generation != self._generation:
                self._worker_alive = False
                return
            self.brain = brain
            self.error = None
            self.phase = "ready"
            self.progress.update(
                phase="ready",
                root=brain["root"],
                root_name=brain["root_name"],
                message="Mapped",
                files=brain["stats"]["files"],
                projects=brain["stats"]["projects"],
                current="",
            )
            self._worker_alive = False
            if self._rescan_pending:
                follow_up = self._pending_force
                self._rescan_pending = False
                self._pending_force = False
        stats = brain["stats"]
        log.info(
            "mapped %s — %s folders, %s files, %s",
            self.root,
            stats["projects"],
            stats["files"],
            brain["provider"]["label"],
        )
        self.hub.publish(json.dumps({"type": "updated"}))
        self._kick_enrich(brain.get("signature"))
        if follow_up is not None:
            try:
                self.request_scan(follow_up)
            except FileNotFoundError:
                log.warning(self.error)

    def _load_or_scan(self, force: bool, progress) -> dict:
        if not self.root.exists() or not self.root.is_dir():
            raise FileNotFoundError(self.root)
        progress({"message": "Checking what changed", "files": 0, "projects": 0, "current": str(self.root)})
        sig = signature(self.root, progress)
        if not force:
            cached = store.load_scan(self.root, sig)
            if cached:
                cached["provider"] = public_provider()
                cached["signature"] = sig
                progress(
                    {
                        "message": "Loaded the saved map",
                        "files": cached["stats"]["files"],
                        "projects": cached["stats"]["projects"],
                        "current": "",
                    }
                )
                return cached
        brain = build_brain(self.root, progress)
        brain["signature"] = sig
        brain["provider"] = public_provider()
        self._apply_cached_summaries(brain)
        store.save_scan(self.root, sig, brain)
        return brain

    def _apply_cached_summaries(self, brain: dict) -> None:
        raw = store.load_llm(self._summary_key(brain))
        if not raw:
            return
        try:
            summaries = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(summaries, dict):
            return
        applied = False
        for project in brain["projects"]:
            text = summaries.get(project["id"])
            if isinstance(text, str) and text.strip():
                project["summary"] = text.strip()
                project["summary_source"] = "model"
                applied = True
        if applied:
            brain["summaries"] = "model"

    def _summary_key(self, brain: dict) -> str:
        h = hashlib.sha256()
        provider = brain.get("provider") or {}
        h.update(str(provider.get("model") or "heuristic").encode())
        for project in brain["projects"]:
            h.update(project["id"].encode())
            h.update((project.get("summary") or "").encode())
        for rec in brain["files"]:
            h.update(rec["id"].encode())
            h.update((rec.get("excerpt") or "")[:240].encode())
        return h.hexdigest()

    def _kick_enrich(self, signature_value: str | None) -> None:
        if os.getenv("BRAIN_DISABLE_LLM") == "1" or not signature_value:
            return
        threading.Thread(target=self._enrich, args=(signature_value,), daemon=True).start()

    def _enrich(self, signature_value: str) -> None:
        provider = resolve_provider()
        if not provider:
            return
        with self.lock:
            brain = self.brain
            if not brain or brain.get("signature") != signature_value:
                return
            if brain.get("summaries") == "model":
                return
            snapshot = json.loads(json.dumps(brain))
            key = self._summary_key(snapshot)
        try:
            summaries = summarize_projects(provider, snapshot)
        except Exception:
            log.exception("model summary failed")
            return
        if not summaries:
            return
        store.save_llm(key, json.dumps(summaries))
        with self.lock:
            if not self.brain or self.brain.get("signature") != signature_value:
                return
            applied = False
            for project in self.brain["projects"]:
                text = summaries.get(project["id"])
                if text:
                    project["summary"] = text
                    project["summary_source"] = "model"
                    applied = True
            if applied:
                self.brain["summaries"] = "model"
                self.brain["provider"] = public_provider()
                store.save_scan(self.root, signature_value, self.brain)
        if applied:
            log.info("model summaries updated for %s folders", len(summaries))
            self.hub.publish(json.dumps({"type": "updated"}))

    def _start_watch(self) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            log.warning("watchdog is not installed; live updates are off")
            return

        engine = self

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                engine._queue_event(event)

            def on_modified(self, event):
                engine._queue_event(event)

            def on_deleted(self, event):
                engine._queue_event(event)

            def on_moved(self, event):
                engine._queue_event(event)

        observer = Observer()
        observer.schedule(Handler(), str(self.root), recursive=True)
        observer.daemon = True
        observer.start()
        self.observer = observer
        log.info("watching %s", self.root)

    def _queue_event(self, event) -> None:
        # Opening files during a scan emits watchdog "opened"/"closed" events.
        # Those are ignored by only subscribing to create/modify/delete/move.
        if getattr(event, "is_directory", False) and event.event_type not in {"deleted", "moved"}:
            return
        path = str(getattr(event, "dest_path", "") or getattr(event, "src_path", ""))
        if _ignored(path):
            return
        self._schedule()

    def _schedule(self) -> None:
        with self._timer_lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(1.2, self._watch_rescan)
            self._timer.daemon = True
            self._timer.start()

    def _watch_rescan(self) -> None:
        try:
            self.request_scan(force=True)
        except FileNotFoundError:
            log.warning(self.error)
        except Exception:
            log.exception("watch rescan failed")


def _ignored(path: str) -> bool:
    if any(ignored_dir_name(part) for part in Path(path).parts):
        return True
    name = Path(path).name
    if name.endswith(("~", ".swp", ".swx", ".tmp")):
        return True
    return False
