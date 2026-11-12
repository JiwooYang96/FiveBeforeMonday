"""Create a Kit broadcast from a rendered issue email.

Usage:
  python3 engine/send.py <issue> <saturday|sunday> <draft|schedule> [send_at]

  issue     e.g. sample-2026-11-06 (reads emails/out/<issue>-<kind>.html
            and engine/data/<issue>.json for the subject)
  draft     creates an unsent draft you can review in Kit (default, safe)
  schedule  schedules the send. send_at is ISO-8601 UTC; if omitted, the
            next Saturday 8:00 am New York time is used.

Uses Kit's v4 API with the KIT_API_KEY environment variable (a GitHub
Actions secret, starting with "kit_"). The key is never printed. v4 keeps
our designed HTML as one HTML block; the older v3 API drops anything beyond
simple tags, which left the first test draft empty.

Safety: no targeting yet, so every broadcast goes to all subscribers. Until
paid members exist, the Sunday report may only be created as a draft.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

API = "https://api.kit.com/v4/broadcasts"
ROOT = Path(__file__).resolve().parent.parent
NY = ZoneInfo("America/New_York")


def next_saturday_8am_ny(now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(NY)
    days = (5 - now.weekday()) % 7
    target = (now + timedelta(days=days)).replace(hour=8, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=7)
    return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def body_of(html):
    """Kit wraps content in its own layout (which adds the unsubscribe
    footer), so send only what sits inside <body>."""
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.S | re.I)
    if not m:
        sys.exit("No <body> found in the rendered email.")
    return m.group(1).strip()


def build_payload(issue, kind, mode, send_at=None):
    data = json.loads((ROOT / "engine/data" / f"{issue}.json").read_text())
    meta = data["email"][kind]
    html = (ROOT / "emails/out" / f"{issue}-{kind}.html").read_text()
    payload = {
        "subject": meta["subject"],
        "preview_text": meta.get("preheader", ""),
        "description": f"Five Before Monday · {kind} · {issue}",
        "content": body_of(html),
        "public": False,
    }
    if mode == "schedule":
        if kind != "saturday":
            sys.exit("Refusing to schedule the Sunday report: it would go to every "
                     "subscriber, including free ones. Create it as a draft instead.")
        payload["send_at"] = send_at or next_saturday_8am_ny()
    elif mode == "draft":
        payload["send_at"] = None
    else:
        sys.exit("mode must be 'draft' or 'schedule'")
    return payload


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    issue, kind, mode = argv[0], argv[1], argv[2]
    send_at = argv[3] if len(argv) > 3 and argv[3] else None
    payload = build_payload(issue, kind, mode, send_at)

    secret = os.environ.get("KIT_API_KEY", "").strip()
    if not secret:
        sys.exit("KIT_API_KEY is not set. Add a Kit v4 key (starts with kit_) as a repository secret.")
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "X-Kit-Api-Key": secret},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = json.loads(r.read())["broadcast"]
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace").replace(secret, "***")
        sys.exit(f"Kit refused the broadcast ({err.code}): {detail[:500]}")

    when = b.get("send_at") or "not scheduled (draft)"
    print(f"Kit broadcast {b['id']} created: {payload['subject']!r}, send: {when}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"### Kit broadcast {b['id']}\n- Subject: {payload['subject']}\n"
                    f"- Kind: {kind} ({mode})\n- Send: {when}\n"
                    f"- Review: https://app.kit.com/campaigns/{b['id']}/draft\n")


if __name__ == "__main__":
    main(sys.argv[1:])
