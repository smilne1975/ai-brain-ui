# AI Brain

A local mission-control view of a messy folder of AI and coding projects: markdown notes, Python scripts, configs, and half-finished Copilot experiments. It scans the folder on your machine, then draws how the work connects.

Four views:

- **Skills** — radial map of capabilities detected in the files
- **Blueprint** — flowchart of each folder (and of the whole corpus), with an ask bar
- **System** — circular meters, one bar per file
- **Connections** — services and APIs the files mention, and whether a key *name* is present

Nothing is uploaded. The app binds to `127.0.0.1`.

## Windows — one command

Install [Python 3.11+](https://www.python.org/downloads/) (check “Add python.exe to PATH”) and [Node.js 20+](https://nodejs.org/). Node is only required the first time, to build the UI.

Downloaded `start.ps1` files are blocked by the default execution policy. Use `start.bat` or `start.cmd` instead. Both call PowerShell with `-ExecutionPolicy Bypass` and pass arguments through:

```bat
start.bat
start.bat -Projects "C:\Users\me\Documents" -Port 8742
```

`start.cmd` is the same wrapper. Double-click either one to open the demo.

The page is served as soon as the process is listening. A large folder (Documents, a OneDrive tree) keeps scanning in the background, and the sidebar shows that path plus live progress. You do not have to wait on “Waiting for application startup”.

If port 8741 is already taken by a previous AI Brain, the script asks whether to stop that process or pick the next free port, then prints the URL it will actually open. It will not kill an unrelated program. `-Replace` stops the old AI Brain without asking. `-Port` chooses the first port to try.

```bat
start.bat -Projects "D:\notes\ai-projects" -Port 8750 -Replace
```

Calling the script directly still works after you allow it:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Projects "D:\notes\ai-projects" -Port 8741
```

macOS and Linux: `./start.sh` or `PORT=8742 ./start.sh /path/to/projects`. A busy port moves to the next free one.

Each immediate subfolder is treated as one project. A folder with no subfolders is one project. The scanner skips `.git`, `node_modules`, virtualenvs, build output, OneDrive cache folders (not your OneDrive itself), Office and other binary files, and cloud-only placeholders that would hang on read. Each project contributes at most 250 files, and a scan stops at 2000 files.

## Model keys (optional)

With no keys, summaries and answers come from heuristics: docstrings, note intros, imports, and a skill catalog. That mode is what the demo uses.

To let a model rewrite folder summaries and answer the ask bar, set one of these before starting:

| Provider | Environment |
| --- | --- |
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Grok / xAI | `XAI_API_KEY` or `GROK_API_KEY` |
| Ollama | `OLLAMA_HOST` (for example `http://127.0.0.1:11434`) |

Force a provider with `LLM_PROVIDER=openai|anthropic|grok|ollama`. Override the model with `LLM_MODEL`.

If several keys are set and `LLM_PROVIDER` is empty, the app prefers Ollama when `OLLAMA_HOST` is set, then OpenAI, Anthropic, and Grok.

PowerShell:

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:LLM_MODEL = "gpt-4o-mini"
.\start.bat -Projects "D:\notes\ai-projects"
```

The key stays in the environment. The UI shows the provider name and model id, never the key.

## What it refuses to read

`.env`, `.env.local`, and similar files are parsed for **key names only**. The characters after `=` are discarded and are not stored, shown, or sent to a model. `.env.example` counts as a template, not as a connected key.

Secret-shaped strings in scripts and notes (`sk-…`, `ghp_…`, Slack webhook URLs, `KEY=value` lines) are redacted before they enter the index.

## How a scan becomes the four views

The scanner walks each project, reads text files, and builds:

- a skill tag from a small catalog (OpenAI, RAG, Slack, routing, lab notes, …)
- an architecture graph from entry points, local imports, and functions that branch (`classify`, `route`, `bucket`, …)
- a service card when code or a key name mentions OpenAI, GitHub, Slack, Ollama, and the rest of the catalog
- a plain-English folder summary from the README plus those facts

The server starts listening before that walk finishes. The sidebar shows the projects folder you pointed at, and the main panel shows which folder and file are being read. A file watcher refreshes the dashboard about a second after you save. Results are cached in `.brain/cache.sqlite` (gitignored) so the next start is instant when nothing changed.

The ask bar retrieves matching files from that index. With a model configured, those excerpts are the only context sent — the same redacted text the UI can show.

Ideas borrowed, not vendored: [Graphify](https://github.com/Graphify-Labs/graphify) for a knowledge graph of a repo, Understand-Anything for plain-English explanations, [Repomix](https://github.com/yamadashy/repomix) for packing the relevant files into one model context, and [GitDiagram](https://github.com/ahmedkhaleel2004/gitdiagram) for drawing architecture from structure and imports. This app aims that at loose script folders rather than a single production repo.

## Develop

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
cd frontend && npm install && npm run build
BRAIN_ROOT=./demo-projects .venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8741
```

`npm run dev` in `frontend` serves the UI on port 8742 and proxies `/api` to 8741.

## Demo folder

`demo-projects/` is a fake week of VS Code work: an inbox labeler, a meeting-note search, a pull-request digest, a prompt vault, a local photo sorter, and a tiny agent loop. The `.env` files contain obvious placeholder values so the connections view can show “connected” without a real credential.
