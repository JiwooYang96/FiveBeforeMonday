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
WEB_SEARCH = {"type": "web_search_20250305", "name": "web_search", "max_uses": 12}


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
        blocks += resp["content"]
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
    """Parse the JSON object in Claude's final text (tolerates a ```json fence)."""
    t = text_of(blocks).strip()
    if "```" in t:
        t = t.split("```")[1]
        t = t[4:] if t.startswith("json") else t
    start, end = t.find("{"), t.rfind("}")
    return json.loads(t[start:end + 1])
