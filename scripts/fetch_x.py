#!/usr/bin/env python3
"""Mirror recent posts from official X accounts into official.json.

Runs every 30 minutes from .github/workflows/official-posts.yml with the
repository secret X_BEARER_TOKEN. Uses since_id so each run only pays for
posts it hasn't seen (X API pay-per-use). Exits quietly when no token is set.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ACCOUNTS = ["RockstarGames"]
KEEP = 20
OUT = Path(__file__).resolve().parent.parent / "official.json"
TOKEN = os.environ.get("X_BEARER_TOKEN", "").strip()


def get(path, **params):
    url = "https://api.x.com/2/" + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "User-Agent": "LeonidaCodebookFeed/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    if not TOKEN:
        print("X_BEARER_TOKEN not set; skipping.")
        return
    state = json.loads(OUT.read_text()) if OUT.exists() else {}
    accounts = state.get("accounts", {})
    posts = {p["id"]: p for p in state.get("posts", [])}
    added = 0
    for handle in ACCOUNTS:
        acct = accounts.get(handle)
        if not acct:
            user = get(f"users/by/username/{handle}", **{"user.fields": "name"})["data"]
            acct = {"id": user["id"], "name": user["name"], "since_id": None}
        params = {"max_results": 10, "exclude": "replies,retweets", "tweet.fields": "created_at"}
        if acct.get("since_id"):
            params["since_id"] = acct["since_id"]
        res = get(f"users/{acct['id']}/tweets", **params)
        for t in res.get("data", []):
            posts[t["id"]] = {"id": t["id"], "handle": handle, "name": acct["name"], "text": t["text"],
                              "created_at": t.get("created_at"), "url": f"https://x.com/{handle}/status/{t['id']}"}
            added += 1
        if res.get("meta", {}).get("newest_id"):
            acct["since_id"] = res["meta"]["newest_id"]
        accounts[handle] = acct
    if added == 0 and OUT.exists() and state.get("accounts"):
        print("No new posts.")
        return
    latest = sorted(posts.values(), key=lambda p: p.get("created_at") or "", reverse=True)[:KEEP]
    OUT.write_text(json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "accounts": accounts, "posts": latest}, ensure_ascii=False, indent=1))
    print(f"Added {added} post(s).")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print(f"X API error {e.code}: {e.read()[:300]!r}")
        sys.exit(1)
