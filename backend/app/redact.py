"""Strip secret-shaped strings before anything is stored or sent to a model.

.env files are handled separately: only key names are parsed, and the rest of
each line is discarded. This module is the safety net for secrets that landed
in scripts, notes, or config.
"""

from __future__ import annotations

import re

_ASSIGN = re.compile(
    r"(?im)^(\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|WEBHOOK)[A-Za-z0-9_]*\s*=\s*)(.+)$"
)
_BEARER = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)(\S+)")
_JSON_SECRET = re.compile(
    r'(?i)("(?:api[_-]?key|token|secret|password|authorization)"\s*:\s*")([^"]*)(")'
)
_SK = re.compile(r"sk-[A-Za-z0-9_\-]{6,}")
_GHP = re.compile(r"ghp_[A-Za-z0-9]{8,}")
_XOX = re.compile(r"xox[baprs]-[A-Za-z0-9\-]{8,}")
_SLACK_HOOK = re.compile(r"https://hooks\.slack\.com/\S+")
_ANTHROPIC = re.compile(r"sk-ant-[A-Za-z0-9_\-]{6,}")


def redact(text: str) -> str:
    if not text:
        return ""
    text = _ASSIGN.sub(lambda m: m.group(1) + "[redacted]", text)
    text = _BEARER.sub(lambda m: m.group(1) + "[redacted]", text)
    text = _JSON_SECRET.sub(lambda m: m.group(1) + "[redacted]" + m.group(3), text)
    text = _SLACK_HOOK.sub("https://hooks.slack.com/[redacted]", text)
    text = _ANTHROPIC.sub("[redacted-key]", text)
    text = _SK.sub("[redacted-key]", text)
    text = _GHP.sub("[redacted-key]", text)
    text = _XOX.sub("[redacted-key]", text)
    return text
