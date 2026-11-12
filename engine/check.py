"""Quality gates. An issue is sent only if every gate passes.

Code checks: figures, sources, dates, advice language, machine-sounding phrasing, length.
Then a second Claude call reviews the draft against the evidence for unsupported claims.
"""
import json
import re
from datetime import date, timedelta

import figures
import llm
import research
import write

ADVICE = [
    r"\b(?:you|investors|readers) (?:should|must|need to|ought to)\b",
    r"\btime to (?:buy|sell)\b", r"\b(?:buy|sell|short) (?:the dip|now|this stock|it)\b",
    r"\b(?:will|is going to|is set to|is poised to|are poised to) (?:rise|fall|climb|drop|soar|surge|crash|rebound|rally|double)\b",
    r"\bwe (?:expect|predict|recommend|think)\b", r"\bguarantee", r"\bcan'?t lose\b", r"\b(?:under|over)valued\b",
    r"\bstrong buy\b", r"\bmust[- ]own\b", r"\bprice target\b",
]
TELLS = [
    "—", r"\bdelve", r"\bpivotal\b", r"\blandscape\b", r"\bunderscor", r"\btestament\b", r"\btapestry\b",
    r"\bcrucial\b", r"\bnavigat", r"\bin conclusion\b", r"\boverall,", r"\bit'?s worth noting\b", r"\bgame[- ]changer\b",
    r"\bnot (?:just|only|merely)\b[^.]{0,80}\bbut\b", r"\bisn'?t [^.]{1,50}\. it'?s\b", r"!", r"\bin today'?s\b",
    r"\b(?:AI|artificial intelligence)[- ](?:written|generated|drafted|assisted)\b", r"\blanguage model\b",
    r"\bas an ai\b", r"\bI (?:think|believe|found|searched)\b",
]


def _strings(obj, path=""):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _strings(v, f"{path}[{i}]")


def data_numbers(snap):
    out = []
    for s in list(snap["stocks"].values()) + list(snap["indices"].values()):
        for k in ("week_pct", "day_pct", "month_pct", "from_high_pct"):
            out.append((abs(s[k]), "pct"))
        for k in ("close", "prev_week_close", "high_52w", "market_cap"):
            if s.get(k):
                out.append((s[k], "num"))
    return out


def gate_figures(d, snap, evidence):
    allowed = data_numbers(snap) + research.sourced_numbers(evidence)
    problems = []
    for path, text in _strings(d):
        if path.endswith(("date", ".evidence")) or ".evidence[" in path:
            continue
        for value, kind, raw, step in figures.extract(text):
            if not figures.matches(value, kind, step, allowed):
                problems.append(f'{path}: the figure "{raw}" is not in DATA or in any EVIDENCE source text')
    cc = d.get("compare_chart") or {}
    for r in cc.get("rows", []):
        for value, kind, raw, step in figures.extract(r.get("display", ""), small_ints=True):
            if not figures.matches(value, kind, step, allowed):
                problems.append(f'compare_chart: "{raw}" is not in any EVIDENCE source text')
    return problems


def gate_sources(d, evidence):
    ids = {e["id"] for e in evidence}
    outlets = " ".join(s["outlet"] + " " + s["title"] for e in evidence for s in e["sources"]).lower()
    problems = []
    for i, c in enumerate(d.get("causes", [])):
        refs = c.get("evidence") or []
        if not refs or not set(refs) <= ids:
            problems.append(f"causes[{i}]: must list valid EVIDENCE ids (got {refs})")
    labelled = [("five", x) for x in d.get("five", [])] + [("causes", x) for x in d.get("causes", [])] + \
               [("next_week", x) for x in d.get("next_week", [])]
    for where, x in labelled:
        src = x.get("source", "")
        if src.lower().startswith("closing prices"):
            continue
        name = src.split("·")[0].lower()
        months = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"}
        words = [w for w in re.findall(r"[a-z]{3,}", name)
                 if w not in months | {"the", "and", "com", "www", "news", "closing", "prices"}]
        if not words or not any(w in outlets for w in words):
            problems.append(f'{where}: source "{src}" does not name an outlet found in EVIDENCE')
    return problems


def gate_dates(d, snap):
    problems = []
    end = date.fromisoformat(snap["week_end"])
    lo, hi = end + timedelta(days=1), end + timedelta(days=10)
    if not d.get("next_week"):
        problems.append("next_week: needs at least one dated event")
    for i, e in enumerate(d.get("next_week", [])):
        try:
            day = date.fromisoformat(e["date"])
        except (KeyError, ValueError):
            problems.append(f"next_week[{i}]: date must be YYYY-MM-DD")
            continue
        if not lo <= day <= hi:
            problems.append(f"next_week[{i}]: {day} is not in the coming week")
    return problems


def gate_language(d):
    problems = []
    for path, text in _strings(d):
        for pat in ADVICE:
            if re.search(pat, text, re.I):
                problems.append(f'{path}: reads like advice or a prediction ("{re.search(pat, text, re.I).group(0)}")')
        for pat in TELLS:
            m = re.search(pat, text, re.I if pat not in ("!", "—") else 0)
            if m:
                problems.append(f'{path}: banned phrasing "{m.group(0)}"')
    return problems


def _words(s):
    return len(re.findall(r"\w+", s or ""))


def gate_length(d):
    problems = []
    if len(d.get("five", [])) != 5:
        problems.append("five: needs exactly 5 items")
    if len(d.get("causes", [])) != 3:
        problems.append("causes: needs exactly 3 items")
    for k, n in (("saturday", 55), ("sunday", 70)):
        if len(d.get(k, {}).get("subject", "")) > n:
            problems.append(f"{k}.subject: too long (max {n} characters)")
    sat = sum(_words(x.get("text")) for x in d.get("five", [])) + _words(d.get("teaser"))
    if sat > 260:
        problems.append(f"Saturday brief is {sat} words; keep it under 260")
    sun = sum(_words(t) for _, t in _strings(d))
    if not 900 <= sun <= 2400:
        problems.append(f"Sunday report is about {sun} words; aim for 1,300-1,900")
    return problems


REVIEW = """You are a strict fact-checker for a markets newsletter. Compare the DRAFT with the EVIDENCE (source text) and DATA.
List every claim that is unsupported, misattributed, wrong, misleading, or that predicts prices or advises readers.
Return only JSON: {"issues": [{"field": "...", "problem": "...", "severity": "high|low"}]}. Use "high" for anything factually unsupported or advisory. An empty list means the draft passes."""


def review(d, snap, evidence):
    msg = (f"DATA:\n{json.dumps(write.data_facts(snap), ensure_ascii=False)}\n\n"
           f"EVIDENCE:\n{json.dumps(evidence, ensure_ascii=False)}\n\nDRAFT:\n{json.dumps(d, ensure_ascii=False)}")
    out = llm.json_of(llm.call(REVIEW, msg, max_tokens=4000))
    return [f'{i.get("field")}: {i.get("problem")} (reviewer, {i.get("severity", "high")})' for i in out.get("issues", [])], \
        any(i.get("severity", "high") == "high" for i in out.get("issues", []))


def run(d, snap, evidence):
    # Source labels are optional; figures are still checked against data and source quotes.
    return gate_figures(d, snap, evidence) + gate_dates(d, snap) + gate_language(d) + gate_length(d)
