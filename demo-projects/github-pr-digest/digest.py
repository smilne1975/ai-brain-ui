"""Post a short pull-request digest to Slack.

Token and webhook live in the environment. This file only names them.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request


def bucket(pr: dict) -> str:
    title = (pr.get("title") or "").lower()
    labels = [item.get("name", "").lower() for item in pr.get("labels") or []]
    if "wip" in labels or title.startswith("wip"):
        return "skip"
    if pr.get("draft"):
        return "draft"
    if "review" in labels or "please review" in title:
        return "needs-you"
    return "fyi"


def fetch_prs(repo: str) -> list[dict]:
    token = os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/pulls?state=open",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "pr-digest",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def post_slack(text: str) -> None:
    webhook = os.environ["SLACK_WEBHOOK_URL"]
    req = urllib.request.Request(
        webhook,
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=20).read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Digest open pull requests")
    parser.add_argument("--repos", default="repos.txt")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    lines = ["Open pull requests"]
    for repo in Path_read(args.repos):
        for pr in fetch_prs(repo):
            kind = bucket(pr)
            if kind == "skip":
                continue
            lines.append(f"[{kind}] {repo} #{pr['number']} {pr['title']}")
    text = "\n".join(lines[:40])
    if args.dry_run:
        print(text)
        return
    post_slack(text)


def Path_read(path: str) -> list[str]:
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            rows.append(line)
    return rows


# cron idea, not installed:
# 0 8 * * 1-5  python digest.py

if __name__ == "__main__":
    main()
