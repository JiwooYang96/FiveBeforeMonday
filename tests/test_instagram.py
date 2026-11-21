"""Offline tests for engine/instagram.py: a reel already on Instagram is never posted again. No network.

Run: python3 -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))

import instagram  # noqa: E402


def _queue(caption):
    d = Path(tempfile.mkdtemp())
    (d / "2026-11-20.json").write_text(json.dumps({"video": "reels/2026-11-20.mp4", "caption": caption, "posted": None}))
    return d


class DuplicateGuard(unittest.TestCase):
    def setUp(self):
        if hasattr(instagram.already_on_instagram, "recent"):
            del instagram.already_on_instagram.recent

    def run_queue(self, caption, recent):
        q = _queue(caption)
        stamp = (datetime.now(timezone.utc) - timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%S+0000")
        media = [{"id": "1", "caption": c, "permalink": "https://www.instagram.com/reel/X/", "timestamp": stamp} for c in recent]
        with mock.patch.object(instagram, "QUEUE", q), \
             mock.patch.object(instagram, "user_id", return_value="42"), \
             mock.patch.object(instagram, "_req", return_value={"data": media}), \
             mock.patch.object(instagram, "wait_public", return_value=True), \
             mock.patch.object(instagram, "publish", return_value=("2", "https://www.instagram.com/reel/NEW/")) as pub, \
             mock.patch.dict("os.environ", {"MAKE_WEBHOOK_URL": ""}):
            instagram.post_queue()
        return pub, json.loads((q / "2026-11-20.json").read_text())["posted"]

    def test_already_posted_is_recorded_not_reposted(self):
        pub, posted = self.run_queue("Intuit stock fell.\n\nSources: x", ["Intuit stock fell.\n\nSources:  x"])
        pub.assert_not_called()
        self.assertEqual(posted["url"], "https://www.instagram.com/reel/X/")
        self.assertTrue(posted["found"])

    def test_new_caption_is_posted(self):
        pub, posted = self.run_queue("Intuit stock fell.", ["Something else"])
        pub.assert_called_once()
        self.assertEqual(posted["url"], "https://www.instagram.com/reel/NEW/")


if __name__ == "__main__":
    unittest.main()
