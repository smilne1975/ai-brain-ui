"""Label an inbox dump as action, waiting, or noise.

Copilot wrote the retry loop. I still do not fully trust it on long threads.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request


def classify(thread: str) -> str:
    """Cheap guardrails before we spend a model call."""
    low = thread.lower()
    if "unsubscribe" in low or "newsletter" in low:
        return "noise"
    if "waiting on you" in low or low.count("?") >= 2:
        return "waiting"
    return "action"


def ask_model(thread: str) -> str:
    key = os.environ["OPENAI_API_KEY"]
    payload = {
        "model": "gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": open("prompts/system.md", encoding="utf-8").read()},
            {"role": "user", "content": thread[:6000]},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    # TODO: send the action pile to Slack once the labels stop wobbling
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
            content = body["choices"][0]["message"]["content"]
            label = json.loads(content).get("label", "action")
            if label in {"action", "waiting", "noise"}:
                return label
        except (urllib.error.URLError, KeyError, json.JSONDecodeError):
            if attempt == 2:
                break
    return classify(thread)


def main() -> None:
    parser = argparse.ArgumentParser(description="Label threads in a mailbox export")
    parser.add_argument("path", help="Markdown or text export of threads")
    args = parser.parse_args()
    text = open(args.path, encoding="utf-8").read()
    # Source is a mailbox export today. IMAP can wait.
    chunks = [block.strip() for block in text.split("\n---\n") if block.strip()]
    for index, thread in enumerate(chunks, start=1):
        print(f"{index:02d}  {ask_model(thread)}")


if __name__ == "__main__":
    main()
