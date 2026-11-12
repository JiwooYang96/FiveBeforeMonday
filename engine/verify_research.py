"""Load and verify research written by the weekly Claude Code research task.

The research task saves engine/data/research/<week_end>.json. Before the issue is
written, every quote is checked against its page:

- page fetched and quote found     -> kept, marked verified
- page fetched, quote not on it    -> dropped (the quote can't be trusted)
- page blocked or paywalled         -> kept, marked unverified (many big outlets block bots)

Figures in the issue must still match the data file or a kept quote, so a figure the
researcher got wrong never reaches readers.

Usage:
  python3 engine/verify_research.py <file>                # verify and print a summary
  python3 engine/verify_research.py <file> --schema-only  # only check the file's shape (no network)
"""
import html
import json
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

TAGS = {"STORY", "CAUSE", "NUMBER", "EVENT", "BULL", "BEAR", "CONTEXT"}
UA = "Mozilla/5.0 (compatible; FiveBeforeMonday-checker/1.0; +https://fivebeforemonday.vercel.app)"


def schema_problems(data):
    problems = []
    items = data.get("items")
    if not isinstance(items, list) or len(items) < 8:
        return ["'items' must be a list of at least 8 statements"]
    for i, it in enumerate(items):
        where = f"items[{i}]"
        if it.get("tag") not in TAGS:
            problems.append(f"{where}: tag must be one of {sorted(TAGS)}")
        if not str(it.get("text", "")).strip():
            problems.append(f"{where}: empty text")
        if it.get("tag") == "EVENT" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(it.get("date", ""))):
            problems.append(f"{where}: EVENT needs date YYYY-MM-DD")
        srcs = it.get("sources")
        if not isinstance(srcs, list) or not srcs:
            problems.append(f"{where}: needs at least one source")
            continue
        for j, s in enumerate(srcs):
            if not str(s.get("url", "")).startswith("http"):
                problems.append(f"{where}.sources[{j}]: url missing")
            if len(str(s.get("quote", "")).strip()) < 12:
                problems.append(f"{where}.sources[{j}]: quote must be an exact phrase copied from the page")
    return problems


def _norm(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("−", "-").replace("–", "-").replace("—", "-").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read(3_000_000).decode("utf-8", errors="replace")
    except Exception:
        return None


def _check(quote, page):
    """True = quote is on the page; None = can't tell; False = the page clearly doesn't say it."""
    if page is None:
        return None
    text = _norm(page)
    if quote in text:
        return True
    if len(text) < 3000:
        return None  # script-rendered or blocked page: not enough text to judge
    words = [w for w in re.findall(r"[a-z]{4,}", quote)]
    figures = re.findall(r"\d[\d.,]*", quote)
    if words and sum(w in text for w in words) / len(words) >= 0.8 and all(f in text for f in figures):
        return None  # same words and figures, different formatting: don't punish it
    return False


def verify(data, fetcher=None):
    fetcher = fetcher or fetch
    pages, evidence, dropped = {}, [], []
    for it in data["items"]:
        kept = []
        for s in it["sources"]:
            url = s["url"]
            if url not in pages:
                pages[url] = fetcher(url)
            page = pages[url]
            quote = _norm(s["quote"])
            status = _check(quote, page)
            if status is False:
                dropped.append(f'{it["tag"]}: quote not found on {url}: "{s["quote"][:80]}"')
                continue
            kept.append({"url": url, "title": s.get("title", ""), "cited_text": s["quote"],
                         "outlet": urlparse(url).netloc.replace("www.", ""), "page_age": s.get("published"),
                         "verified": status})
        if kept:
            evidence.append({"id": f"E{len(evidence) + 1}", "tag": it["tag"], "date": it.get("date"),
                             "text": it["text"], "sources": kept})
    return evidence, dropped


def load(path, fetcher=None):
    data = json.loads(Path(path).read_text())
    problems = schema_problems(data)
    if problems:
        raise ValueError("research file is malformed: " + "; ".join(problems[:8]))
    return verify(data, fetcher)


if __name__ == "__main__":
    path = sys.argv[1]
    data = json.loads(Path(path).read_text())
    probs = schema_problems(data)
    if probs:
        print("\n".join(probs))
        sys.exit(1)
    if "--schema-only" in sys.argv:
        print(f"OK: {len(data['items'])} statements, {len(data.get('reels', []))} reel ideas")
        sys.exit(0)
    ev, dropped = verify(data)
    checked = sum(1 for e in ev for s in e["sources"] if s["verified"])
    print(f"{len(ev)} statements kept, {checked} quotes confirmed on the page, {len(dropped)} dropped")
    print("\n".join(dropped))
