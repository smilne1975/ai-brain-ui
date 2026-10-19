"""Post a line to Slack using the bot token named in the environment."""

from __future__ import annotations

import json
import os
import urllib.request


def post_slack(text: str) -> None:
    token = os.environ["SLACK_BOT_TOKEN"]
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps({"channel": "#scratch", "text": text[:500]}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    urllib.request.urlopen(req, timeout=20).read()
