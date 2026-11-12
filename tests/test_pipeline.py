"""Offline tests: synthetic market data and canned Claude replies, no network.

Run: python3 -m unittest discover -s tests
"""
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

import build  # noqa: E402
import check  # noqa: E402
import collect  # noqa: E402
import figures  # noqa: E402
import llm  # noqa: E402
import research  # noqa: E402
import write  # noqa: E402

FRIDAY = date(2026, 11, 13)


def series(start_price, weekly_drift, days=300):
    out, p, d = [], start_price, FRIDAY - timedelta(days=days)
    while d <= FRIDAY:
        if d.weekday() < 5:
            p *= 1 + weekly_drift / 5
            out.append((d.isoformat(), round(p, 2)))
        d += timedelta(days=1)
    return out


def snapshot():
    monday, friday = collect.week_bounds(FRIDAY)
    snap = {"as_of": FRIDAY.isoformat(), "week_start": monday.isoformat(), "week_end": friday.isoformat(),
            "stocks": {}, "indices": {}, "sources": ["Yahoo Finance", "SEC EDGAR (shares outstanding)"]}
    specs = {"NVDA": (120, -0.01, 24.3e9), "AAPL": (200, 0.004, 14.8e9), "MSFT": (400, 0.002, 7.43e9),
             "GOOGL": (150, 0.003, 12.1e9), "AMZN": (180, 0.001, 10.6e9), "META": (500, -0.002, 2.5e9),
             "AVGO": (150, 0.006, 4.7e9), "TSLA": (250, -0.004, 3.2e9)}
    for tk, (p0, drift, shares) in specs.items():
        row = {"name": collect.STOCKS[tk][0], **collect.summarise(series(p0, drift), monday, friday)}
        row["shares"], row["market_cap"] = int(shares), round(row["close"] * shares)
        snap["stocks"][tk] = row
    snap["indices"]["^NDX"] = {"name": "Nasdaq-100", **collect.summarise(series(18000, 0.001), monday, friday)}
    return snap


def cite(url, text):
    return {"type": "web_search_result_location", "url": url, "title": "Nvidia slides as chip stocks fall",
            "cited_text": text}


def research_blocks():
    lines = [
        ("[STORY] Nvidia shares fell for a third week as chip stocks slid.", "Nvidia shares fell for a third straight week"),
        ("[CAUSE] Microsoft said it would cut data-center spending by $10 billion.", "cut data-center spending by $10 billion"),
        ("[CAUSE] US CPI rose 3.1% in October, above forecasts.", "consumer prices rose 3.1% in October"),
        ("[CAUSE] CoreWeave reported $35 billion of debt.", "CoreWeave reported $35 billion of debt"),
        ("[CAUSE] Analysts at Bernstein said orders were slowing.", "Bernstein said orders were slowing"),
        ("[NUMBER] Chip stocks lost $400 billion in value this week.", "lost $400 billion in value this week"),
        ("[EVENT 2026-11-18] Nvidia reports earnings on Nov 18 with a $108 billion revenue guide.", "Nvidia reports on Nov. 18; guidance of $108 billion"),
        ("[BULL] Bank of America said demand remains above supply.", "demand remains above supply"),
        ("[BEAR] Morgan Stanley said margins may peak.", "margins may peak"),
    ]
    blocks = [{"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "nvidia week"}},
              {"type": "web_search_tool_result", "tool_use_id": "s1",
               "content": [{"type": "web_search_result", "url": "https://www.reuters.com/x", "title": "t",
                            "page_age": "November 12, 2026"}]}]
    for text, quote in lines:
        tag, rest = text.split("] ", 1)
        blocks.append({"type": "text", "text": tag + "] "})
        blocks.append({"type": "text", "text": rest, "citations": [cite("https://www.reuters.com/x", quote)]})
        blocks.append({"type": "text", "text": "\n"})
    return blocks


def good_draft(snap):
    nv = snap["stocks"]["NVDA"]
    wk = write.fmt_pct(nv["week_pct"])
    long = ("Microsoft said it would cut data-center spending by $10 billion, which raised questions about future chip "
            "orders across the industry. ") * 9
    return {
        "featured": "Nvidia",
        "saturday": {"subject": f"Nvidia {wk}: this week's 5 numbers", "preheader": "A $10 billion cut and one date."},
        "sunday": {"subject": "Why Nvidia slid, and what Nov 18 decides", "preheader": "Three causes and the case on each side.",
                   "headline": "Nvidia slid again. Here's why.", "lead": f"Nvidia moved {wk} this week. Three causes stood out.",
                   "what_happened": long},
        "five": [{"num": wk, "tone": "down", "text": "Nvidia's move this week.", "source": "Closing prices · Nov 13"},
                 {"num": "$10B", "tone": "down", "text": "Microsoft's cut to data-center spending.", "source": "Reuters · Nov 12"},
                 {"num": "3.1%", "tone": "down", "text": "US inflation in October.", "source": "Reuters · Nov 12"},
                 {"num": "$35B", "tone": "down", "text": "CoreWeave's debt.", "source": "Reuters · Nov 12"},
                 {"num": "$108B", "tone": "gold", "text": "Nvidia's guide for Nov 18.", "source": "Reuters · Nov 12"}],
        "next_week": [{"date": "2026-11-18", "what": "Nvidia reports.", "event": "Nvidia earnings", "detail": "$108B guide",
                       "source": "Reuters · Nov 12", "evidence": ["E7"]}],
        "teaser": "Sunday: why Nvidia slid and what Nov 18 decides.",
        "causes": [{"title": "Spending cut", "stat": "$10B", "text": long, "source": "Reuters · Nov 12", "evidence": ["E2"]},
                   {"title": "Hot inflation", "stat": "3.1%", "text": long, "source": "Reuters · Nov 12", "evidence": ["E3"]},
                   {"title": "Buyers in debt", "stat": "$35B", "text": long, "source": "Reuters · Nov 12", "evidence": ["E4"]}],
        "after_causes": {"title": "The whole group", "text": "Most tracked stocks moved with the chip names."},
        "next_text": long,
        "bull": ["Bank of America said demand remains above supply."],
        "bear": ["Morgan Stanley said margins may peak."],
        "table": [["Nvidia weekly change", wk, "Nov 13", "Closing prices"], ["Microsoft spending cut", "$10B", "Nov 12", "Reuters"]],
        "compare_chart": None,
    }


class Figures(unittest.TestCase):
    def test_rounding_to_text_precision(self):
        allowed = [(4.62e12, "num"), (3.42, "pct"), (165000, "num")]
        for text in ("$4.62T", "$4.6T", "3.4%", "about 3%", "165K", "165,000"):
            for v, k, raw, step in figures.extract(text):
                self.assertTrue(figures.matches(v, k, step, allowed), text)
        for v, k, raw, step in figures.extract("$4.9T and 4.4%"):
            self.assertFalse(figures.matches(v, k, step, allowed), raw)

    def test_dates_and_names_are_not_claims(self):
        self.assertEqual(figures.extract("S&P 500 on Nov 18, 2026 in Q3; 3 causes"), [])


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.snap = snapshot()

    def test_collect_maths(self):
        s = self.snap["stocks"]["NVDA"]
        self.assertEqual(s["close_date"], "2026-11-13")
        self.assertLess(s["week_pct"], 0)
        self.assertLessEqual(s["from_high_pct"], 0)

    def test_research_keeps_cited_lines(self):
        ev = research.evidence_from(research_blocks(), self.snap["week_start"])
        self.assertEqual(len(ev), 9)
        self.assertEqual(ev[6]["tag"], "EVENT")
        self.assertEqual(ev[6]["date"], "2026-11-18")
        self.assertIn((10e9, "num"), research.sourced_numbers(ev))

    def test_good_draft_passes_gates(self):
        ev = research.evidence_from(research_blocks(), self.snap["week_start"])
        self.assertEqual(check.run(good_draft(self.snap), self.snap, ev), [])

    def test_bad_draft_is_caught(self):
        ev = research.evidence_from(research_blocks(), self.snap["week_start"])
        d = good_draft(self.snap)
        d["five"][1]["text"] = "Microsoft cut $12 billion. Investors should buy the dip — it will rebound!"
        d["five"][2]["source"] = "Some Blog · Nov 12"
        probs = " | ".join(check.run(d, self.snap, ev))
        for expected in ('"$12 billion"', "advice", "banned phrasing", "Some Blog"):
            self.assertIn(expected, probs)

    def test_end_to_end_build(self):
        snap_path = ROOT / "tests" / "_snap.json"
        snap_path.write_text(json.dumps(self.snap))
        replies = [research_blocks(),
                   [{"type": "text", "text": json.dumps(good_draft(self.snap))}],
                   [{"type": "text", "text": '{"issues": []}'}]]
        try:
            with mock.patch.object(llm, "call", side_effect=replies):
                status = build.build(snapshot=str(snap_path))
            self.assertEqual(status["status"], "ready", status)
            issue = json.loads((ROOT / "engine/data/2026-11-13.json").read_text())
            self.assertEqual({c["id"] for c in issue["charts"]}, {"market-value", "week-moves", "calendar"})
            self.assertTrue((ROOT / "emails/out/2026-11-13-sunday.html").exists())
            self.assertTrue((ROOT / "img/2026-11-13-week-moves.png").exists())
        finally:
            snap_path.unlink(missing_ok=True)
            for p in [ROOT / "engine/data/2026-11-13.json", ROOT / "engine/data/audit/2026-11-13.json",
                      ROOT / "build-status.json", *ROOT.glob("img/2026-11-13-*.png"), *ROOT.glob("emails/out/2026-11-13-*")]:
                p.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
