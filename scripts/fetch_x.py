#!/usr/bin/env python3
"""Mirror recent posts from official X accounts into official.json.

Runs every 30 minutes from .github/workflows/official-posts.yml with the
repository secret X_BEARER_TOKEN. Uses since_id so each run only pays for
posts it hasn't seen (X API pay-per-use). Exits quietly when no token is set.

Only GTA VI posts are published in `posts`. When none of the recent posts
match, the single latest post is published instead (`fallback: true`).
`--refilter` re-applies the filter to the saved posts without calling X.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ACCOUNTS = ["RockstarGames"]
KEEP = 20
RECENT = 60
GTA_VI = re.compile(r"\bgta\s?(vi|6)\b|#gtavi|#gta6|\bgrand theft auto vi\b|\bleonida\b|\bvice city\b|\bjason\b|\blucia\b", re.I)
OUT = Path(__file__).resolve().parent.parent / "official.json"
TOKEN = os.environ.get("X_BEARER_TOKEN", "").strip()


def get(path, **params):
    url = "https://api.x.com/2/" + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "User-Agent": "LeonidaCodebookFeed/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def publish(state, recent):
    """Write official.json if the published set changed. Returns True if written."""
    recent = sorted(recent.values(), key=lambda p: p.get("created_at") or "", reverse=True)[:RECENT]
    for p in recent:
        p["vi"] = bool(GTA_VI.search(p.get("text", "")))
    vi = [p for p in recent if p["vi"]][:KEEP]
    fallback = not vi
    posts = vi or recent[:1]
    if state.get("posts") == posts and state.get("fallback") == fallback and state.get("recent") == recent:
        return False
    state.update({"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "fallback": fallback, "posts": posts, "recent": recent})
    OUT.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    print(f"Published {len(posts)} post(s){' (fallback: latest post)' if fallback else ' about GTA VI'}.")
    return True


def main():
    state = json.loads(OUT.read_text()) if OUT.exists() else {}
    # Older files only had `posts`; seed the recent pool from them.
    recent = {p["id"]: p for p in state.get("recent", state.get("posts", []))}
    if "--refilter" in sys.argv:
        publish(state, recent)
        return
    if not TOKEN:
        print("X_BEARER_TOKEN not set; skipping.")
        return
    accounts = state.get("accounts", {})
    posts = recent
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
    state["accounts"] = accounts
    print(f"Fetched {added} new post(s).")
    if not publish(state, posts):
        print("Nothing to publish.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print(f"X API error {e.code}: {e.read()[:300]!r}")
        sys.exit(1)
