"""Research the week: Claude searches the web and returns short, cited statements.

Only statements that carry at least one citation survive. Each citation keeps the exact
source text (cited_text), and the checker later accepts a figure only if it appears in
that source text or in the market-data file.
"""
import json
import re
from datetime import date, timedelta
from urllib.parse import urlparse

import figures
import llm

TAGS = ("STORY", "CAUSE", "NUMBER", "EVENT", "BULL", "BEAR", "CONTEXT")

SYSTEM = """You research a weekly newsletter about large US tech stocks. You report facts; you never give opinions or advice.

Search the web for coverage published during the given week (and the next week's calendar). Prefer primary sources and major outlets: company releases and filings, Reuters, Bloomberg, CNBC, the Wall Street Journal, the Financial Times, Barron's, MarketWatch, Yahoo Finance, Forbes, government statistics sites.

Write your findings as single factual sentences, one per line, each starting with a tag:
[STORY] the week's main story among the tracked stocks (2-3 lines)
[CAUSE] a reason given in coverage for the main move, with its key figure (6-9 lines, covering at least three distinct causes)
[NUMBER] another notable figure from the week about these stocks or the market (5-8 lines)
[EVENT YYYY-MM-DD] a dated event in the following Monday-Friday that could move these stocks: earnings, Fed decisions, CPI, jobs data (2-6 lines)
[BULL] the strongest argument made this week for the featured stock (2-3 lines)
[BEAR] the strongest argument made this week against it (2-3 lines)
[CONTEXT] anything else a reader needs (0-3 lines)

Rules:
- Every line must be supported by a search result and cite it. Put the line's key figure in the cited words.
- Copy figures exactly as the source states them. Never estimate or compute a figure.
- Name who said it when it is an opinion ("Analysts at X said...").
- Only use pages published in the given week, except for event dates.
- Output only the tagged lines. No headings, no introduction, no summary."""


def _user(snap):
    rows = []
    for tk, s in snap["stocks"].items():
        rows.append(f"{s['name']} ({tk}): week {s['week_pct']:+.2f}%, month {s['month_pct']:+.2f}%, "
                    f"{s['from_high_pct']:+.2f}% from 52-week high")
    for sym, s in snap["indices"].items():
        rows.append(f"{s['name']}: week {s['week_pct']:+.2f}%")
    nxt = date.fromisoformat(snap["week_end"]) + timedelta(days=3)
    return (f"Week: {snap['week_start']} to {snap['week_end']}. Next week starts {nxt.isoformat()}.\n"
            "Closing-price moves this week (from market data, already known; don't search for these):\n"
            + "\n".join(rows) +
            "\n\nFind why the biggest movers moved, the week's main story, and next week's dated events.")


def _lines_with_citations(blocks):
    """Rebuild Claude's final answer line by line, keeping each line's citations."""
    lines, cur, cites = [], "", []
    for b in blocks:
        if b.get("type") != "text":
            continue
        own = [c for c in (b.get("citations") or []) if c.get("type") == "web_search_result_location"]
        parts = b["text"].split("\n")
        placed = not own
        for i, part in enumerate(parts):
            cur += part
            if not placed and (part.strip() or i == len(parts) - 1):
                cites, placed = cites + own, True  # a block's citations belong to the line its words land on
            if i < len(parts) - 1:
                lines.append((cur.strip(), cites))
                cur, cites = "", []
    lines.append((cur.strip(), cites))
    return [(t, c) for t, c in lines if t]


def _page_ages(blocks):
    ages = {}
    for b in blocks:
        if b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
            for r in b["content"]:
                if r.get("url"):
                    ages[r["url"]] = r.get("page_age")
    return ages


def _parse_age(s):
    from datetime import datetime
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def evidence_from(blocks, week_start):
    ages = _page_ages(blocks)
    oldest = date.fromisoformat(week_start) - timedelta(days=3)
    items = []
    for text, cites in _lines_with_citations(blocks):
        text = re.sub(r"^[\s\-*•>#\d.)]*", "", text).replace("**", "")  # tolerate bullets and bold
        m = re.match(r"\[(\w+)(?::|\s)*(\d{4}-\d{2}-\d{2})?\]\s*[:\-–]?\s*(.+)", text)
        if not m or m.group(1) not in TAGS:
            continue
        tag, when, body = m.group(1), m.group(2), m.group(3)
        kept = []
        for c in cites:
            age = _parse_age(ages.get(c["url"]) or "")
            if tag != "EVENT" and age and age < oldest:
                continue  # stale page: not this week's news
            kept.append({"url": c["url"], "title": c.get("title", ""), "cited_text": c.get("cited_text", ""),
                         "outlet": urlparse(c["url"]).netloc.replace("www.", ""), "page_age": ages.get(c["url"])})
        if kept:
            items.append({"id": f"E{len(items) + 1}", "tag": tag, "date": when, "text": body, "sources": kept})
    return items


def sourced_numbers(evidence):
    """Figures that literally appear in cited source text."""
    out = []
    for item in evidence:
        for s in item["sources"]:
            out += [(v, k) for v, k, _, _ in figures.extract(s["cited_text"], small_ints=True)]
    return out


LAST_BLOCKS = []  # the raw reply, kept for the audit file


def diagnose(blocks):
    """One line on why research came back thin: search errors, citations, what the text looked like."""
    kinds = {}
    for b in blocks:
        kinds[b.get("type")] = kinds.get(b.get("type"), 0) + 1
    errors = [b["content"].get("error_code") for b in blocks
              if b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), dict)]
    cites = sum(len(b.get("citations") or []) for b in blocks if b.get("type") == "text")
    text = llm.text_of(blocks).strip().replace("\n", " | ")
    return f"blocks={kinds} search_errors={errors} citations={cites} text_start={text[:400]!r}"


def research(snap):
    blocks = llm.call(SYSTEM, _user(snap), tools=[llm.WEB_SEARCH], max_tokens=8000)
    LAST_BLOCKS[:] = blocks
    ev = evidence_from(blocks, snap["week_start"])
    if len(ev) < 8:
        raise RuntimeError(f"research returned only {len(ev)} cited statements; {diagnose(blocks)}")
    return ev


if __name__ == "__main__":
    import sys
    snap = json.load(open(sys.argv[1]))
    print(json.dumps(research(snap), indent=2))
