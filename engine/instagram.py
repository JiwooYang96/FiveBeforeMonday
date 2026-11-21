"""Post queued reels to Instagram (Instagram API with Instagram Login, graph.instagram.com).

The daily reel task queues a reel as reels/<date>.mp4 + reels/<date>.json ({"video", "caption", "posted"}).
Vercel serves the mp4 publicly at SITE/reels/<date>.mp4; Instagram downloads it from there.

Trial reels: a queued reel with "trial": "SS_PERFORMANCE" (or "MANUAL") is posted as a trial reel.

Usage:
  python3 engine/instagram.py post            # post every queued reel whose "posted" is null
  python3 engine/instagram.py refresh         # print a refreshed long-lived token (valid 60 days)
  python3 engine/instagram.py check           # check the token and print the account

Env: IG_ACCESS_TOKEN, IG_USER_ID (optional; looked up from the token), SITE (default the Vercel site).
Second account (@5beforemonday, chips): IG_QUEUE=reels-chips, IG_USERNAME=5beforemonday, IG_ACCESS_TOKEN from the
IG_ACCESS_TOKEN_2 secret. With a Facebook-login token the user id is found by IG_USERNAME among the token's pages.
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

# Two kinds of token work:
#   IGAA...  Instagram-login token  -> graph.instagram.com
#   EAA...   Facebook/unified-login token (new apps get these) -> graph.facebook.com, needs IG_USER_ID
TOKEN = lambda: os.environ.get("IG_ACCESS_TOKEN", "").strip()  # noqa: E731  (pasted secrets often carry a newline)
API = "https://graph.facebook.com/v23.0" if TOKEN().startswith("EAA") else "https://graph.instagram.com/v23.0"
DEFAULT_IG_USER_ID = "17841457551550085"  # @fivebeforemonday
KNOWN_IG_USER_IDS = {"fivebeforemonday": "17841457551550085", "5beforemonday": "17841415005394410"}  # from the Meta app
ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / os.environ.get("IG_QUEUE", "reels")
SITE = os.environ.get("SITE", "https://fivebeforemonday.com").rstrip("/")


def _req(method, url, params=None, timeout=60):
    params = dict(params or {})
    params["access_token"] = TOKEN()
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
    if "graph.facebook.com" in API:
        want = os.environ.get("IG_USERNAME", "").strip().lstrip("@").lower()
        if not want:
            return DEFAULT_IG_USER_ID
        if want in KNOWN_IG_USER_IDS:
            return KNOWN_IG_USER_IDS[want]
        if not getattr(user_id, "cache", None):
            pages = _req("GET", f"{API}/me/accounts", {"fields": "instagram_business_account{id,username}", "limit": "100"})
            found = {p["instagram_business_account"]["username"].lower(): p["instagram_business_account"]["id"]
                     for p in pages.get("data", []) if p.get("instagram_business_account")}
            if want not in found:
                # Unified-login tokens (generated per Instagram account in the app dashboard) belong to the
                # Instagram user itself: /me answers with its id and username.
                try:
                    me = _req("GET", f"{API}/me", {"fields": "id,username"})
                    if me.get("username", "").lower() == want:
                        found[want] = me["id"]
                except RuntimeError as err:
                    print(f"/me lookup failed: {str(err)[:200]}")
            if want not in found and os.environ.get("IG_USER_ID_FALLBACK"):
                found[want] = os.environ["IG_USER_ID_FALLBACK"]
            if want not in found:
                raise RuntimeError(f"@{want} is not linked to a Facebook Page this token can see (found: {sorted(found) or 'none'})")
            user_id.cache = found[want]
        return user_id.cache
    return _req("GET", f"{API}/me", {"fields": "user_id,username"})["user_id"]


def long_lived():
    """Swap the current token for a fresh 60-day one. EAA tokens need META_APP_ID and META_APP_SECRET."""
    if "graph.facebook.com" in API:
        app_id, secret = os.environ.get("META_APP_ID", "").strip(), os.environ.get("META_APP_SECRET", "").strip()
        if not (app_id and secret):
            raise RuntimeError("META_APP_ID and META_APP_SECRET are needed to extend a Facebook-login token")
        url = "https://graph.facebook.com/v23.0/oauth/access_token?" + urllib.parse.urlencode({
            "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": secret,
            "fb_exchange_token": TOKEN()})
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read())["access_token"]
    return _req("GET", "https://graph.instagram.com/refresh_access_token", {"grant_type": "ig_refresh_token"})["access_token"]


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


def publish(video_url, caption, trial=None):
    """trial: None, "SS_PERFORMANCE" (shown to non-followers first; Instagram shares it to followers if it does well)
    or "MANUAL" (graduated by hand in the app). If the account can't post trial reels, it posts a normal reel."""
    uid = user_id()
    params = {"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true", "thumb_offset": "1500"}
    if trial:
        try:
            container = _req("POST", f"{API}/{uid}/media", {**params, "trial_params": json.dumps({"graduation_strategy": trial})})["id"]
        except RuntimeError as err:
            print(f"Trial reel refused ({str(err)[:200]}); posting as a normal reel.")
            trial, container = None, _req("POST", f"{API}/{uid}/media", params)["id"]
    else:
        container = _req("POST", f"{API}/{uid}/media", params)["id"]
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
    publish.trial = trial
    return media, link


def via_make(video_url, caption, date):
    body = json.dumps({"video_url": video_url, "caption": caption, "date": date}).encode()
    req = urllib.request.Request(os.environ["MAKE_WEBHOOK_URL"], data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if r.status >= 300:
            raise RuntimeError(f"Make webhook answered {r.status}")
    return "make", ""


def _same_caption(a, b):
    norm = lambda t: " ".join((t or "").split())  # noqa: E731  (Instagram may trim or re-wrap whitespace)
    return bool(a) and norm(a) == norm(b)


def already_on_instagram(caption, hours=72):
    """The account's own recent post with this caption, if any: {"id", "url"}.

    The queue file can be stale (on Nov 20 two post runs overlapped and both reels went out twice), so before
    publishing we ask Instagram itself. If the lookup fails we say so and post anyway."""
    if not hasattr(already_on_instagram, "recent"):
        try:
            data = _req("GET", f"{API}/{user_id()}/media", {"fields": "id,caption,permalink,timestamp", "limit": "25"})
            already_on_instagram.recent = data.get("data", [])
        except RuntimeError as err:
            print(f"warning: couldn't list recent posts to check for duplicates ({str(err)[:200]})")
            already_on_instagram.recent = []
    now = datetime.now(timezone.utc)
    for m in already_on_instagram.recent:
        try:
            age = (now - datetime.strptime(m.get("timestamp", ""), "%Y-%m-%dT%H:%M:%S%z")).total_seconds() / 3600
        except ValueError:
            age = 0
        if age <= hours and _same_caption(m.get("caption"), caption):
            return {"id": m.get("id"), "url": m.get("permalink", "")}
    return None


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
        if not os.environ.get("MAKE_WEBHOOK_URL"):
            dup = already_on_instagram(meta["caption"])
            if dup:
                meta["posted"] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **dup, "found": True}
                meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
                print("already posted", meta_path.stem, dup["url"], "(not posting again)")
                continue
        if os.environ.get("MAKE_WEBHOOK_URL"):
            media, link = via_make(url, meta["caption"], meta_path.stem)
        else:
            media, link = publish(url, meta["caption"], meta.get("trial"))
        meta["posted"] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "id": media, "url": link}
        if meta.get("trial"):
            meta["posted"]["trial"] = getattr(publish, "trial", None)  # None = the account refused; posted normally
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
        sys.stdout.write(long_lived())
    elif cmd == "check":
        if "graph.facebook.com" in API:
            if os.environ.get("IG_USERNAME"):
                try:
                    print("token /me:", _req("GET", f"{API}/me", {"fields": "id,name"}))
                except RuntimeError as err:
                    print("token /me failed:", str(err)[:300])
            me = _req("GET", f"{API}/{user_id()}", {"fields": "username"})
            print(f"OK: @{me.get('username')} (Facebook-login token), user id {user_id()}")
        else:
            me = _req("GET", f"{API}/me", {"fields": "user_id,username,account_type"})
            print(f"OK: @{me.get('username')} ({me.get('account_type')}), user id {me.get('user_id')}")
    else:
        sys.exit(__doc__)
