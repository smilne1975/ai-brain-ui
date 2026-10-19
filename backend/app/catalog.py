"""Skill and service catalogs.

Needles are matched against relative paths and redacted file text. They are
intentionally specific so a casual mention of "github copilot" does not pretend
to be a GitHub API integration.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillDef:
    id: str
    name: str
    category: str
    blurb: str
    needles: tuple[str, ...] = ()
    # "markdown-notes" is applied by the scanner, not by a needle.
    special: str = ""


@dataclass(frozen=True)
class ServiceDef:
    id: str
    name: str
    category: str
    description: str
    needles: tuple[str, ...]
    env: tuple[str, ...] = ()


CATEGORY_ORDER = [
    "Models",
    "Prompting",
    "Retrieval",
    "Agents",
    "Automation",
    "Data",
    "Interfaces",
    "Devtools",
    "Notes",
]


SKILLS: tuple[SkillDef, ...] = (
    SkillDef("openai-api", "OpenAI API", "Models", "Chat and embedding calls against OpenAI.", ("openai", "api.openai.com", "openai_api_key")),
    SkillDef("anthropic", "Anthropic", "Models", "Claude, usually via the Anthropic API or a playground note.", ("anthropic", "claude")),
    SkillDef("local-models", "Local models", "Models", "Ollama or another model running on the machine.", ("ollama", "11434", "local model")),
    SkillDef("vision", "Vision", "Models", "Image opens, Pillow, or a vision-model note.", ("from pil", "import pil", "pillow", "image.open", "vision model")),
    SkillDef("prompt-craft", "Prompt craft", "Prompting", "System prompts, few-shot notes, and prompt revisions.", ("prompt", "few-shot", "few shot")),
    SkillDef("structured", "Structured output", "Prompting", "JSON replies, schemas, or response_format.", ("json.loads", "response_format", "json mode", "pydantic")),
    SkillDef("rag", "RAG", "Retrieval", "Retrieval over a pile of notes rather than a single prompt.", ("rag", "retriev")),
    SkillDef("chunking", "Chunking", "Retrieval", "Splitting notes before they are embedded or searched.", ("chunk",)),
    SkillDef("embeddings", "Embeddings", "Retrieval", "Turning text into vectors.", ("embedding",)),
    SkillDef("chroma", "Chroma", "Retrieval", "Chroma (or a note about it) as the vector store.", ("chroma",)),
    SkillDef("tool-use", "Tool use", "Agents", "A loop that picks tools and calls them.", ("tools/", "tool_call", "available tools")),
    SkillDef("routing", "Routing", "Agents", "A function that branches: classify, route, dispatch.", ("def route", "def classify", "def bucket", "dispatch")),
    SkillDef("slack", "Slack", "Automation", "Slack webhooks or chat methods.", ("slack",)),
    SkillDef("github", "GitHub API", "Automation", "The GitHub HTTP API or a token meant for it.", ("api.github.com", "github_token", "gh_token")),
    SkillDef("email", "Email triage", "Automation", "Inbox dumps, IMAP, or mail labeling.", ("imap", "smtplib", "inbox dump", "mailbox")),
    SkillDef("digests", "Digests", "Automation", "Scheduled summaries of pulls, mail, or notes.", ("digest", "cron", "schedule")),
    SkillDef("json-store", "JSON memory", "Data", "A json file used as memory or a tiny store.", ("json.dump", "store.json", "memory/")),
    SkillDef("sqlite", "SQLite", "Data", "sqlite3 in a script or a note about trying it.", ("sqlite3", "sqlite")),
    SkillDef("cli", "CLI scripts", "Interfaces", "Scripts with argparse or a __main__ guard.", ("argparse", "__main__")),
    SkillDef("copilot", "Copilot workflow", "Devtools", "VS Code Copilot notes, comments, or editor settings.", ("copilot", ".vscode")),
    SkillDef("lab-notes", "Lab notes", "Notes", "Markdown that is not a prompt file.", special="lab-notes"),
)


SERVICES: tuple[ServiceDef, ...] = (
    ServiceDef("openai", "OpenAI", "AI", "Chat completions and embeddings.", ("openai", "api.openai.com", "openai_api_key"), ("OPENAI_API_KEY",)),
    ServiceDef("anthropic", "Anthropic", "AI", "Claude models.", ("anthropic", "claude", "anthropic_api_key"), ("ANTHROPIC_API_KEY",)),
    ServiceDef("xai", "xAI Grok", "AI", "Grok models via the xAI API.", ("api.x.ai", "xai_api_key", "grok-"), ("XAI_API_KEY", "GROK_API_KEY")),
    ServiceDef("ollama", "Ollama", "AI", "Local models, usually on port 11434.", ("ollama", "11434"), ("OLLAMA_HOST",)),
    ServiceDef("cohere", "Cohere", "AI", "Cohere generate or embed APIs.", ("cohere", "cohere_api_key"), ("COHERE_API_KEY",)),
    ServiceDef("slack", "Slack", "Automation", "Incoming webhooks and bot tokens.", ("slack", "slack_webhook_url", "slack_bot_token"), ("SLACK_WEBHOOK_URL", "SLACK_BOT_TOKEN", "SLACK_API_TOKEN")),
    ServiceDef("discord", "Discord", "Automation", "Discord webhooks.", ("discord",), ("DISCORD_WEBHOOK_URL",)),
    ServiceDef("email", "Email", "Automation", "IMAP, SMTP, or an inbox export.", ("imap", "smtplib", "inbox dump", "mailbox"), ()),
    ServiceDef("github", "GitHub", "Devtools", "Repos, pull requests, and tokens.", ("api.github.com", "github_token", "gh_token"), ("GITHUB_TOKEN", "GH_TOKEN")),
    ServiceDef("copilot", "GitHub Copilot", "Devtools", "Editor assistant. Detected from notes or VS Code settings, not a live login.", ("copilot", ".vscode"), ()),
    ServiceDef("docker", "Docker", "Devtools", "Dockerfiles and compose files.", ("dockerfile", "docker-compose", "docker compose"), ()),
    ServiceDef("chroma", "Chroma", "Data", "Local or hosted Chroma collections.", ("chroma",), ()),
    ServiceDef("sqlite", "SQLite", "Data", "sqlite3 or a .sqlite file mentioned in notes.", ("sqlite3", "sqlite"), ()),
    ServiceDef("postgres", "Postgres", "Data", "A Postgres URL or driver.", ("postgres", "psycopg"), ("DATABASE_URL",)),
    ServiceDef("notion", "Notion", "Knowledge", "Notion API or exported pages.", ("notion",), ("NOTION_API_KEY", "NOTION_TOKEN")),
)


def skill_by_id() -> dict[str, SkillDef]:
    return {s.id: s for s in SKILLS}


def service_by_id() -> dict[str, ServiceDef]:
    return {s.id: s for s in SERVICES}
