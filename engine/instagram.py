"""Post queued reels to Instagram (Instagram API with Instagram Login, graph.instagram.com).

The daily reel task queues a reel as reels/<date>.mp4 + reels/<date>.json ({"video", "caption", "posted"}).
Vercel serves the mp4 publicly at SITE/reels/<date>.mp4; Instagram downloads it from there.

Usage:
  python3 engine/instagram.py post            # post every queued reel whose "posted" is null
  python3 engine/instagram.py refresh         # print a refreshed long-lived token (valid 60 days)
  python3 engine/instagram.py check           # check the token and print the account

Env: IG_ACCESS_TOKEN, IG_USER_ID (optional; looked up from the token), SITE (default the Vercel site).
Or, without a Meta developer app: MAKE_WEBHOOK_URL, a Make.com scenario (Custom webhook -> Instagram for
Business "Create a reel post") that receives {"video_url", "caption", "date"} and publishes it.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://graph.instagram.com/v23.0"
ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "reels"
SITE = os.environ.get("SITE", "https://fivebeforemonday.com").rstrip("/")


def _req(method, url, params=None, timeout=60):
    params = dict(params or {})
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"].strip()  # pasted secrets often carry a newline
    data = None
    if method == "GET":
        url = url + "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors="replace")
        # Never print the token: it is only in the query/body, not in the error text.
        raise RuntimeError(f"Instagram API {err.code}: {body}") from None


def user_id():
    if os.environ.get("IG_USER_ID"):
        return os.environ["IG_USER_ID"]
    return _req("GET", f"{API}/me", {"fields": "user_id,username"})["user_id"]


def wait_public(url, tries=30):
    """Wait until Vercel serves the video (a push deploys in about a minute)."""
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200 and "video" in r.headers.get("Content-Type", ""):
                    return True
        except urllib.error.URLError:
            pass
        time.sleep(20)
    return False


def publish(video_url, caption):
    uid = user_id()
    container = _req("POST", f"{API}/{uid}/media", {
        "media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true",
    })["id"]
    for _ in range(40):  # up to ~10 minutes of processing
        status = _req("GET", f"{API}/{container}", {"fields": "status_code,status"})
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram could not process the video: {status}")
        time.sleep(15)
    else:
        raise RuntimeError("Instagram is still processing the video after 10 minutes")
    media = _req("POST", f"{API}/{uid}/media_publish", {"creation_id": container})["id"]
    link = _req("GET", f"{API}/{media}", {"fields": "permalink"}).get("permalink", "")
    return media, link


def via_make(video_url, caption, date):
    body = json.dumps({"video_url": video_url, "caption": caption, "date": date}).encode()
    req = urllib.request.Request(os.environ["MAKE_WEBHOOK_URL"], data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if r.status >= 300:
            raise RuntimeError(f"Make webhook answered {r.status}")
    return "make", ""


def post_queue():
    posted = []
    for meta_path in sorted(QUEUE.glob("*.json")):
        meta = json.loads(meta_path.read_text())
        if meta.get("posted"):
            continue
        url = f"{SITE}/{meta['video']}"
        if not wait_public(url):
            print(f"skip {meta_path.name}: {url} is not live yet")
            continue
        if os.environ.get("MAKE_WEBHOOK_URL"):
            media, link = via_make(url, meta["caption"], meta_path.stem)
        else:
            media, link = publish(url, meta["caption"])
        meta["posted"] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "id": media, "url": link}
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
        posted.append(f"{meta_path.stem}: {link or media}")
        print("posted", meta_path.stem, link)
    return posted


def prune(days=7):
    """Delete posted videos older than `days` to keep the repo small (the JSON record stays)."""
    today = datetime.now(timezone.utc).date()
    for meta_path in QUEUE.glob("*.json"):
        meta = json.loads(meta_path.read_text())
        video = ROOT / meta["video"]
        try:
            age = (today - datetime.strptime(meta_path.stem[:10], "%Y-%m-%d").date()).days
        except ValueError:
            continue
        if meta.get("posted") and video.exists() and age > days:
            video.unlink()
            print("pruned", video.name)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "post"
    if cmd == "post":
        done = post_queue()
        prune()
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as f:
                f.write(f"posted={len(done)}\n")
    elif cmd == "refresh":
        r = _req("GET", "https://graph.instagram.com/refresh_access_token", {"grant_type": "ig_refresh_token"})
        sys.stdout.write(r["access_token"])
    elif cmd == "check":
        me = _req("GET", f"{API}/me", {"fields": "user_id,username,account_type"})
        print(f"OK: @{me.get('username')} ({me.get('account_type')}), user id {me.get('user_id')}")
    else:
        sys.exit(__doc__)
