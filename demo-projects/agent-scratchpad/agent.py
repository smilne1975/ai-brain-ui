"""One-file agent loop. Tools are real modules. The router is the messy part."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request

from memory.store import Memory
from tools.post_slack import post_slack
from tools.search_notes import search_notes


def route_turn(text: str, memory: Memory) -> str:
    """Pick a tool. This is the decision the diagram should show."""
    low = text.lower()
    if low.startswith("remember "):
        memory.add(text.removeprefix("remember ").strip())
        return "stored"
    if "slack" in low or low.startswith("post "):
        post_slack(text)
        return "slack"
    if "search" in low or "notes" in low or "meeting" in low:
        hits = search_notes(text)
        return hits[0] if hits else "no notes"
    return ask_model(text, memory)


def ask_model(text: str, memory: Memory) -> str:
    key = os.environ["OPENAI_API_KEY"]
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a small local assistant. Use the memory notes if they help."},
            {"role": "user", "content": text + "\n\nmemory:\n" + "\n".join(memory.recent())},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        body = json.loads(resp.read().decode())
    return body["choices"][0]["message"]["content"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Scratchpad agent")
    parser.add_argument("text", nargs="+")
    args = parser.parse_args()
    memory = Memory("memory/store.json")
    print(route_turn(" ".join(args.text), memory))


if __name__ == "__main__":
    main()
