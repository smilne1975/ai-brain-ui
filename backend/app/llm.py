"""Optional model backends. Heuristics run when no provider is configured.

Supported:
  LLM_PROVIDER=openai|anthropic|grok|ollama   (optional; otherwise the first configured wins)
  OPENAI_API_KEY, ANTHROPIC_API_KEY, XAI_API_KEY or GROK_API_KEY, OLLAMA_HOST
  LLM_MODEL to override the default model name
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from backend.app.redact import redact

_DEFAULTS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "grok": "grok-3-mini",
    "ollama": "llama3.2",
}


def resolve_provider() -> dict | None:
    if os.getenv("BRAIN_DISABLE_LLM") == "1":
        return None
    forced = os.getenv("LLM_PROVIDER", "").strip().lower()
    available = {
        "ollama": bool(os.getenv("OLLAMA_HOST", "").strip()) or forced == "ollama",
        "openai": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY", "").strip()),
        "grok": bool(os.getenv("XAI_API_KEY", "").strip() or os.getenv("GROK_API_KEY", "").strip()),
    }
    order = ["ollama", "openai", "anthropic", "grok"]
    if forced:
        if forced not in available or not available[forced]:
            return None
        chosen = forced
    else:
        chosen = next((name for name in order if available[name] and _configured(name)), None)
        if not chosen:
            return None
    model = os.getenv("LLM_MODEL", "").strip() or _DEFAULTS[chosen]
    if chosen == "ollama":
        return {
            "name": "ollama",
            "display": "Ollama",
            "style": "ollama",
            "model": model,
            "base": os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
            "key": "",
        }
    if chosen == "anthropic":
        return {
            "name": "anthropic",
            "display": "Anthropic",
            "style": "anthropic",
            "model": model,
            "base": "https://api.anthropic.com",
            "key": os.getenv("ANTHROPIC_API_KEY", ""),
        }
    if chosen == "grok":
        return {
            "name": "grok",
            "display": "Grok",
            "style": "openai",
            "model": model,
            "base": "https://api.x.ai/v1",
            "key": os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY") or "",
        }
    return {
        "name": "openai",
        "display": "OpenAI",
        "style": "openai",
        "model": model,
        "base": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        "key": os.getenv("OPENAI_API_KEY", ""),
    }


def _configured(name: str) -> bool:
    if name == "ollama":
        return bool(os.getenv("OLLAMA_HOST", "").strip())
    if name == "openai":
        return bool(os.getenv("OPENAI_API_KEY", "").strip())
    if name == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    if name == "grok":
        return bool(os.getenv("XAI_API_KEY", "").strip() or os.getenv("GROK_API_KEY", "").strip())
    return False


def public_provider() -> dict:
    provider = resolve_provider()
    if not provider:
        return {"mode": "heuristic", "model": None, "label": "Heuristics"}
    return {"mode": provider["name"], "model": provider["model"], "label": f"{provider['display']} · {provider['model']}"}


def complete(provider: dict, system: str, user: str, max_tokens: int = 700, timeout: int | None = None) -> str:
    system = redact(system)
    user = redact(user)
    if provider["style"] == "anthropic":
        limit = 45 if timeout is None else timeout
        return _anthropic(provider, system, user, max_tokens, limit)
    if provider["style"] == "ollama":
        limit = 90 if timeout is None else timeout
        return _ollama(provider, system, user, limit)
    limit = 45 if timeout is None else timeout
    return _openai(provider, system, user, max_tokens, limit)


def summarize_projects(provider: dict, brain: dict) -> dict[str, str]:
    blocks = []
    for project in brain.get("projects") or []:
        files = [f for f in brain.get("files") or [] if f["project_id"] == project["id"]]
        lines = [f"id: {project['id']}", f"name: {project['name']}"]
        if project.get("stats", {}).get("env_keys"):
            lines.append("env key names: " + ", ".join(project["stats"]["env_keys"]))
        lines.append("heuristic: " + project.get("summary", ""))
        for rec in files[:12]:
            if rec["kind"] == "env":
                lines.append(f"- {rec['rel']}: key names {', '.join(rec.get('env_keys') or [])}")
            else:
                lines.append(f"- {rec['rel']}: {rec.get('summary', '')}")
                excerpt = (rec.get("excerpt") or "")[:400]
                if excerpt:
                    lines.append(excerpt)
        blocks.append("\n".join(lines)[:2800])
    if not blocks:
        return {}
    user = (
        "Write a 2 sentence plain-English summary of what the person was trying to do in each folder. "
        "Keep file and folder names when they help. Do not invent services or keys.\n"
        "Return a JSON object mapping folder id to summary, and nothing else.\n\n"
        + "\n\n".join(blocks)
    )
    raw = complete(
        provider,
        "You summarize messy local coding folders. Reply with JSON only.",
        user,
        max_tokens=900,
    )
    return _parse_json_object(raw)


def _parse_json_object(text: str) -> dict[str, str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, value in data.items():
        if isinstance(value, str) and value.strip():
            out[str(key)] = redact(value.strip())[:700]
    return out


def _post(url: str, payload: dict, headers: dict, timeout: int = 45) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"model HTTP {exc.code}") from None


def _openai(provider: dict, system: str, user: str, max_tokens: int, timeout: int) -> str:
    data = _post(
        f"{provider['base']}/chat/completions",
        {
            "model": provider["model"],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        {
            "Authorization": f"Bearer {provider['key']}",
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )
    return data["choices"][0]["message"]["content"]


def _anthropic(provider: dict, system: str, user: str, max_tokens: int, timeout: int) -> str:
    data = _post(
        f"{provider['base']}/v1/messages",
        {
            "model": provider["model"],
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        {
            "x-api-key": provider["key"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )
    parts = data.get("content") or []
    return "".join(part.get("text", "") for part in parts if isinstance(part, dict))


def _ollama(provider: dict, system: str, user: str, timeout: int) -> str:
    data = _post(
        f"{provider['base']}/api/chat",
        {
            "model": provider["model"],
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        {"Content-Type": "application/json"},
        timeout=timeout,
    )
    return (data.get("message") or {}).get("content") or ""
