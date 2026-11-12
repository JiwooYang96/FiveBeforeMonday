"""Minimal Claude API client (Messages API over HTTPS, no SDK needed).

Reads ANTHROPIC_API_KEY from the environment. FBM_MODEL picks the model.
"""
import json
import os
import time
import urllib.error
import urllib.request

API = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("FBM_MODEL", "claude-sonnet-5-5")
LAST = {}  # stop_reason of the latest reply, for error messages
USAGE = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "searches": 0}
# Sonnet 5.5 list prices, USD per million tokens; web search per 1,000 searches.
PRICES = {"input": 2.0, "output": 10.0, "cache_read": 0.20, "cache_write": 2.50, "searches": 10.0}


def cost():
    p = PRICES
    return round((USAGE["input"] * p["input"] + USAGE["output"] * p["output"] + USAGE["cache_read"] * p["cache_read"]
                  + USAGE["cache_write"] * p["cache_write"]) / 1e6 + USAGE["searches"] * p["searches"] / 1000, 3)


def _count(u):
    USAGE["input"] += u.get("input_tokens", 0)
    USAGE["output"] += u.get("output_tokens", 0)
    USAGE["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
    USAGE["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
    USAGE["searches"] += (u.get("server_tool_use") or {}).get("web_search_requests", 0)
# Reputable financial outlets, official statistics and the tracked companies' own sites only.
TRUSTED = [
    "reuters.com", "bloomberg.com", "cnbc.com", "wsj.com", "ft.com", "barrons.com", "marketwatch.com",
    "finance.yahoo.com", "apnews.com", "nasdaq.com", "forbes.com", "fortune.com", "businessinsider.com",
    "axios.com", "morningstar.com", "investopedia.com", "economist.com", "nytimes.com", "washingtonpost.com",
    "theverge.com", "techcrunch.com", "fool.com", "foxbusiness.com", "investing.com", "seekingalpha.com",
    "sec.gov", "bls.gov", "bea.gov", "federalreserve.gov", "treasury.gov", "census.gov",
    "nvidia.com", "apple.com", "microsoft.com", "abc.xyz", "aboutamazon.com", "meta.com", "fb.com",
    "broadcom.com", "tesla.com",
]
WEB_SEARCH = {"type": "web_search_20250305", "name": "web_search", "max_uses": 6, "allowed_domains": TRUSTED}


def call(system, user, tools=None, max_tokens=8000, model=None):
    """Send one user message; follow pause_turn until Claude finishes.

    Returns every content block Claude produced across the turn, in order.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    messages = [{"role": "user", "content": user}]
    blocks = []
    for _ in range(8):
        body = {"model": model or MODEL, "max_tokens": max_tokens, "system": system, "messages": messages}
        if tools:
            body["tools"] = tools
        resp = _post(body, key)
        _count(resp.get("usage") or {})
        blocks += resp["content"]
        LAST["stop_reason"] = resp.get("stop_reason")
        if resp.get("stop_reason") != "pause_turn":
            return blocks
        messages = messages + [{"role": "assistant", "content": resp["content"]}]
    raise RuntimeError("Claude kept pausing; giving up")


def _post(body, key, tries=4):
    data = json.dumps(body).encode()
    for i in range(tries):
        req = urllib.request.Request(API, data=data, method="POST", headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as err:
            detail = err.read().decode(errors="replace")[:600]
            if err.code in (429, 500, 502, 503, 529) and i < tries - 1:
                time.sleep(15 * (i + 1))
                continue
            raise RuntimeError(f"Claude API error {err.code}: {detail}") from None
    raise RuntimeError("Claude API unreachable")


def text_of(blocks):
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def json_of(blocks):
    """Parse the largest JSON object in Claude's final text, wherever it sits (fences or prose around it)."""
    t = text_of(blocks)
    dec = json.JSONDecoder()
    best = None
    i = t.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(t, i)
            if isinstance(obj, dict) and (best is None or end - i > best[1]):
                best = (obj, end - i)
        except ValueError:
            pass
        i = t.find("{", i + 1)
    if best is None:
        raise ValueError(f"no JSON object in reply (stop_reason={LAST.get('stop_reason')}, "
                         f"{len(t)} chars): {t[:300]!r}")
    return best[0]
