"""Collect Instagram insights for every posted reel (input for the reels performance analyser).

Usage:
  python3 engine/reelstats.py collect [--dry]   # one snapshot per posted reel, saved to engine/data/reel-stats.json
  python3 engine/reelstats.py show              # print the latest numbers

Reads reels/*.json (written by post-reel.yml: posted.id) and keeps, per reel, one snapshot a day for its
first 30 days. The analyser (reels_generator: scripts/reelanalyze.py) joins these with each reel's plan.

Metrics (Instagram Media Insights, REELS, lifetime; numbers settle within about 48 hours):
  views, reach, likes, comments, shares, saved, total_interactions, reposts,
  ig_reels_avg_watch_time (ms), ig_reels_video_view_total_time (ms),
  reels_skip_rate (% of first plays that left within the first 3 seconds).
The per-second retention graph is not in the API; it comes from app screenshots (reels_generator data/retention/).

Env: IG_ACCESS_TOKEN (same as posting), IG_USER_ID (optional).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from instagram import API, QUEUE, _req, user_id  # noqa: E402

OUT = Path(__file__).resolve().parent / "data" / "reel-stats.json"
METRICS = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions", "reposts",
           "ig_reels_avg_watch_time", "ig_reels_video_view_total_time", "reels_skip_rate"]
KEEP_DAYS = 30


def insights(media_id):
    """All metrics in one call; if Instagram rejects one (new or retired metric), fetch them one by one."""
    def parse(resp):
        return {d["name"]: (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value"))
                for d in resp.get("data", [])}
    try:
        return parse(_req("GET", f"{API}/{media_id}/insights", {"metric": ",".join(METRICS)})), []
    except RuntimeError:
        got, missing = {}, []
        for m in METRICS:
            try:
                got.update(parse(_req("GET", f"{API}/{media_id}/insights", {"metric": m})))
            except RuntimeError as err:
                missing.append(f"{m}: {str(err)[:120]}")
        return got, missing


def collect(dry=False):
    now = datetime.now(timezone.utc)
    db = json.loads(OUT.read_text()) if OUT.exists() else {"reels": {}, "account": []}
    try:
        acct = _req("GET", f"{API}/{user_id()}", {"fields": "followers_count,media_count"})
        db["account"] = [a for a in db["account"] if a["at"][:10] != now.date().isoformat()]
        db["account"].append({"at": now.isoformat(timespec="seconds"), "followers": acct.get("followers_count"),
                              "media": acct.get("media_count")})
    except RuntimeError as err:
        print("account:", str(err)[:200])
    problems = []
    for meta_path in sorted(QUEUE.glob("*.json")):
        meta = json.loads(meta_path.read_text())
        posted = meta.get("posted") or {}
        if not posted.get("id") or posted.get("id") == "make":
            continue
        key = meta_path.stem
        at = datetime.fromisoformat(posted["at"])
        age_h = (now - at).total_seconds() / 3600
        rec = db["reels"].setdefault(key, {"id": posted["id"], "url": posted.get("url"), "postedAt": posted["at"],
                                           "snapshots": []})
        if age_h > KEEP_DAYS * 24 and rec["snapshots"]:
            continue
        values, missing = insights(posted["id"])
        if missing:
            problems.append(f"{key}: " + "; ".join(missing))
        snap = {"at": now.isoformat(timespec="seconds"), "ageH": round(age_h, 1), **values}
        # One snapshot per day: today's replaces an earlier one from the same day.
        rec["snapshots"] = [s for s in rec["snapshots"] if s["at"][:10] != snap["at"][:10]] + [snap]
        rec["latest"] = snap
        print(f"{key:32} {age_h:6.0f}h  views {values.get('views')}  skip {values.get('reels_skip_rate')}%  "
              f"avg {values.get('ig_reels_avg_watch_time')}ms  shares {values.get('shares')}")
    for p in problems:
        print("missing:", p)
    if dry:
        print("(dry run: nothing saved)")
        return db
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(db, indent=1, ensure_ascii=False) + "\n")
    return db


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    if cmd == "collect":
        collect(dry="--dry" in sys.argv)
    elif cmd == "show":
        db = json.loads(OUT.read_text())
        for k, r in db["reels"].items():
            print(k, json.dumps(r.get("latest", {})))
    else:
        sys.exit(__doc__)
