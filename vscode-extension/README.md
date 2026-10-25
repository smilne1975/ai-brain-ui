# AI Brain for VS Code

Opens the local AI Brain dashboard inside VS Code.

## Install from VSIX

1. In VS Code, open the Extensions view.
2. Open the `...` menu and choose **Extensions: Install from VSIX...**.
3. Pick `releases/ai-brain-0.1.0.vsix` from this repo (the same file is also at `vscode-extension/` after a local package).
4. Reload if VS Code asks.

The activity bar shows an **AI Brain** icon. The command palette commands are **AI Brain: Open Dashboard** and **AI Brain: Open Digest**.

## What the command does

The panel loads `http://127.0.0.1:8741/` (change the port with the `aiBrain.port` setting).

If nothing is listening, VS Code asks before it starts the backend. The extension runs Python itself:

```text
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8741
```

It does not call `start.ps1` or any other PowerShell script. On Windows it tries `py`, then `python`, then `python3`, unless `aiBrain.pythonPath` is set.

The scan folder is `aiBrain.projectsFolder` when that setting is set, otherwise the folder open in VS Code. `BRAIN_ROOT` is set to that path. The Python checkout is found by walking the workspace and the extension folder for `backend/app/main.py`. An installed VSIX does not contain the backend, so set `aiBrain.repoPath` to your `ai-brain-ui` checkout when the workspace is not that repo.

`.env` values are still never read. Copilot chat text stays on the machine.
