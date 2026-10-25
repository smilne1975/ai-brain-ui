import * as http from "http";
import * as path from "path";
import { spawn, type ChildProcess } from "child_process";
import * as fs from "fs";
import * as vscode from "vscode";

let started: ChildProcess | undefined;
const output = vscode.window.createOutputChannel("AI Brain");

export function activate(context: vscode.ExtensionContext): void {
  const provider = new DashboardView(context);
  context.subscriptions.push(
    output,
    vscode.window.registerWebviewViewProvider("aiBrain.dashboard", provider),
    vscode.commands.registerCommand("aiBrain.openDashboard", () => openDashboard(context, provider)),
    { dispose: () => stopStarted() },
  );
}

export function deactivate(): void {
  stopStarted();
}

class DashboardView implements vscode.WebviewViewProvider {
  private view: vscode.WebviewView | undefined;

  constructor(private readonly context: vscode.ExtensionContext) {}

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = { enableScripts: true };
    const port = readConfig().port;
    void probe(port).then((up) => {
      view.webview.html = up ? panelHtml(port) : launchHtml(port);
    });
    view.webview.onDidReceiveMessage((message: { type?: string }) => {
      if (message?.type === "open") void openDashboard(this.context, this);
    });
  }

  show(port: number): void {
    if (!this.view) return;
    this.view.webview.html = panelHtml(port);
  }
}

async function openDashboard(context: vscode.ExtensionContext, sidebar: DashboardView): Promise<void> {
  const port = await ensureServer(context);
  if (!port) return;
  sidebar.show(port);
  const panel = vscode.window.createWebviewPanel("aiBrain.panel", "AI Brain", vscode.ViewColumn.Active, {
    enableScripts: true,
    retainContextWhenHidden: true,
  });
  panel.webview.html = panelHtml(port);
  await vscode.commands.executeCommand("aiBrain.dashboard.focus");
}

async function ensureServer(context: vscode.ExtensionContext): Promise<number | null> {
  const config = readConfig();
  if (await probe(config.port)) return config.port;
  const choice = await vscode.window.showInformationMessage(
    `AI Brain is not running on 127.0.0.1:${config.port}. Start the Python backend?`,
    "Start",
    "Cancel",
  );
  if (choice !== "Start") return null;
  const repo = findRepo(context);
  if (!repo) {
    void vscode.window.showErrorMessage(
      "AI Brain could not find backend/app/main.py. Set aiBrain.repoPath to your ai-brain-ui checkout.",
    );
    return null;
  }
  const projects = projectsFolder(repo);
  const python = await findPython(config.pythonPath);
  if (!python) {
    void vscode.window.showErrorMessage("Python was not found. Set aiBrain.pythonPath to python.exe.");
    return null;
  }
  output.appendLine(`Starting ${python} -m uvicorn in ${repo}`);
  output.appendLine(`BRAIN_ROOT=${projects}`);
  const child = spawn(python, ["-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", String(config.port)], {
    cwd: repo,
    shell: false,
    windowsHide: true,
    env: { ...process.env, BRAIN_ROOT: projects },
  });
  started = child;
  child.stdout?.on("data", (chunk: Buffer) => output.append(chunk.toString()));
  child.stderr?.on("data", (chunk: Buffer) => output.append(chunk.toString()));
  child.on("error", (error) => output.appendLine(error.message));
  const ready = await waitUntilReady(config.port, child);
  if (!ready) {
    stopStarted();
    void vscode.window.showErrorMessage(
      "AI Brain did not start. See the AI Brain output channel. The extension starts Python directly and does not run PowerShell.",
    );
    return null;
  }
  return config.port;
}

function readConfig(): { port: number; projectsFolder: string; pythonPath: string; repoPath: string } {
  const config = vscode.workspace.getConfiguration("aiBrain");
  const port = Number(config.get<number>("port") ?? 8741);
  return {
    port: Number.isFinite(port) && port > 0 ? port : 8741,
    projectsFolder: (config.get<string>("projectsFolder") ?? "").trim(),
    pythonPath: (config.get<string>("pythonPath") ?? "").trim(),
    repoPath: (config.get<string>("repoPath") ?? "").trim(),
  };
}

function projectsFolder(repo: string): string {
  const configured = readConfig().projectsFolder;
  if (configured) return configured;
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (folder) return folder.uri.fsPath;
  return path.join(repo, "demo-projects");
}

function findRepo(context: vscode.ExtensionContext): string | null {
  const configured = readConfig().repoPath;
  if (configured && hasBackend(configured)) return configured;
  const starts = [
    ...(vscode.workspace.workspaceFolders ?? []).map((folder) => folder.uri.fsPath),
    context.extensionPath,
  ];
  for (const start of starts) {
    let dir = start;
    for (let hop = 0; hop < 6; hop += 1) {
      if (hasBackend(dir)) return dir;
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  return null;
}

function hasBackend(dir: string): boolean {
  return fs.existsSync(path.join(dir, "backend", "app", "main.py"));
}

async function findPython(configured: string): Promise<string | null> {
  const candidates = configured ? [configured] : process.platform === "win32" ? ["py", "python", "python3"] : ["python3", "python"];
  for (const candidate of candidates) {
    if (await pythonWorks(candidate)) return candidate;
  }
  return null;
}

function pythonWorks(executable: string): Promise<boolean> {
  return new Promise((resolve) => {
    const child = spawn(executable, ["-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"], {
      shell: false,
      windowsHide: true,
    });
    child.on("error", () => resolve(false));
    child.on("exit", (code) => resolve(code === 0));
  });
}

function probe(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get({ hostname: "127.0.0.1", port, path: "/api/health", timeout: 1200 }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitUntilReady(port: number, child: ChildProcess): Promise<boolean> {
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) return false;
    if (await probe(port)) return true;
    await delay(400);
  }
  return false;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function stopStarted(): void {
  if (!started || started.killed) return;
  started.kill();
  started = undefined;
}

function panelHtml(port: number): string {
  const url = `http://127.0.0.1:${port}/`;
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; frame-src http://127.0.0.1:${port} http://localhost:${port};">
<style>
  html, body { margin: 0; height: 100%; background: #070807; color: #e7f6ee; font: 13px/1.4 Segoe UI, sans-serif; }
  body { display: grid; grid-template-rows: auto minmax(0, 1fr); }
  header { display: flex; justify-content: space-between; gap: 12px; padding: 6px 10px; color: #8ea898; }
  a { color: #3dff9a; }
  iframe { width: 100%; height: 100%; border: 0; background: #070807; }
</style>
</head>
<body>
<header><span>AI Brain · ${url}</span><a href="${url}">Open in browser</a></header>
<iframe src="${url}" title="AI Brain dashboard"></iframe>
</body>
</html>`;
}

function launchHtml(port: number): string {
  const nonce = String(Date.now());
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<style>
  body { margin: 0; padding: 16px; background: #070807; color: #e7f6ee; font: 13px/1.45 Segoe UI, sans-serif; }
  button { background: #3dff9a; color: #062015; border: 0; border-radius: 999px; padding: 8px 12px; font: inherit; }
  p { color: #8ea898; }
</style>
</head>
<body>
<h2>AI Brain</h2>
<p>The dashboard is served from 127.0.0.1:${port}. If that server is not running, you can start the Python backend from this checkout.</p>
<button type="button" id="open">Open dashboard</button>
<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  document.getElementById("open").addEventListener("click", () => vscode.postMessage({ type: "open" }));
</script>
</body>
</html>`;
}
