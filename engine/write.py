"""Write the issue: Claude turns market data and cited research into the issue JSON.

Claude writes only the words. Charts, dates and the issue id are built here in code
from the market-data file, so a chart can never show a number the data doesn't hold.
"""
import json
from datetime import date, timedelta

import llm

SITE = "https://fivebeforemonday.vercel.app"

SYSTEM = """You write Five Before Monday, a weekly email that explains what moved large US tech stocks and why.

Voice: plain, specific, calm, a little dry. Short sentences (under 25 words). Explain like a sharp friend who reads markets for a living. At most one light line per section.

Hard rules:
1. Facts only from DATA and EVIDENCE below. Copy every figure exactly as given (DATA "display" values, or the figure as it appears in an EVIDENCE source). Never compute, round differently, or estimate a new number.
2. Explain, never advise. No buy, sell, hold, price targets of your own, predictions ("will rise"), or "investors should". Describe what others argue, and name them.
3. Never mention how the newsletter is made, research tools, AI or language models, and never write in the first person singular.
4. Banned: em dashes, "delve", "pivotal", "landscape", "underscore", "testament", "tapestry", "crucial", "navigate", "in conclusion", "overall", "it's worth noting", "not just X but Y" and "It's not X. It's Y." constructions, exclamation marks, emojis.
5. Sources are short labels: "Outlet · Mon D" for EVIDENCE (outlet from the source's site, date from the page or the week) and "Closing prices · Mon D" for DATA.
6. Every claim in "causes" lists the EVIDENCE ids it rests on.
7. The subject line must make a concrete, true promise that the first screen of the email pays off. Max 55 characters. Preview text adds a second reason to open; it never repeats the subject.

Return only one JSON object, no prose, with exactly these keys:
{
 "featured": "company name the issue centres on",
 "saturday": {"subject": "...", "preheader": "..."},
 "sunday": {"subject": "...", "preheader": "...", "headline": "max 8 words", "lead": "2 sentences: the answer, with its number", "what_happened": "120-200 words on the move itself"},
 "five": [5 items {"num": "the figure as displayed, e.g. -3.4% or $4.62T or #2", "tone": "up|down|gold", "text": "one sentence, max 22 words", "source": "..."}],
 "next_week": [1-4 items {"date": "YYYY-MM-DD", "what": "one sentence", "event": "2-3 word label", "detail": "short figure or note", "source": "...", "evidence": ["E.."]}],
 "teaser": "one sentence on the question Sunday's report answers",
 "causes": [3 items {"title": "2-4 words", "stat": "one figure", "text": "150-220 words: the cause, the figure, who said it, how it links to the move", "source": "...", "evidence": ["E..", ...]}],
 "after_causes": {"title": "2-4 words", "text": "60-120 words on how the whole group of tracked stocks moved this week (a chart of every stock's weekly move follows)"},
 "next_text": "150-220 words on what next week decides: the dated events and what each outcome would mean, without predicting",
 "bull": [2-4 short sentences], "bear": [2-4 short sentences],
 "table": [6-10 rows ["what", "figure", "as of (Mon D)", "source outlet"]],
 "compare_chart": null or {"title": "max 5 words", "subtitle": "...", "rows": [2-4 {"label": "...", "value": number, "display": "figure as in EVIDENCE", "hero": true|false}], "source": "...", "cause": 0|1|2}
}"""


def fmt_pct(v):
    return f"{'+' if v >= 0 else '−'}{abs(v):.1f}%"


def fmt_money(v):
    if v >= 1e12:
        return f"${v / 1e12:.2f}T"
    if v >= 1e9:
        return f"${v / 1e9:.0f}B"
    return f"${v:,.2f}"


def short_date(d):
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d:%b} {d.day}"


def data_facts(snap):
    facts = []
    for tk, s in list(snap["stocks"].items()) + list(snap["indices"].items()):
        n = s["name"]
        facts += [
            {"what": f"{n} weekly change", "display": fmt_pct(s["week_pct"])},
            {"what": f"{n} change on the last day", "display": fmt_pct(s["day_pct"])},
            {"what": f"{n} change over about a month", "display": fmt_pct(s["month_pct"])},
            {"what": f"{n} distance from 52-week high ({short_date(s['high_52w_date'])})", "display": fmt_pct(s["from_high_pct"])},
        ]
        if tk in snap["stocks"]:
            facts.append({"what": f"{n} closing price {short_date(s['close_date'])}", "display": f"${s['close']:,.2f}"})
        if s.get("market_cap"):
            facts.append({"what": f"{n} market value (approx.)", "display": fmt_money(s["market_cap"])})
    ranked = sorted((s for s in snap["stocks"].values() if s.get("market_cap")), key=lambda s: -s["market_cap"])
    for i, s in enumerate(ranked, 1):
        facts.append({"what": f"{s['name']} rank by market value among tracked stocks", "display": f"#{i}"})
    return facts


def _user(snap, evidence, feedback=None, previous=None):
    ev = [{"id": e["id"], "tag": e["tag"], "date": e.get("date"), "statement": e["text"],
           "sources": [{"outlet": s["outlet"], "title": s["title"], "page_date": s.get("page_age"),
                        "source_text": s["cited_text"]} for s in e["sources"]]} for e in evidence]
    msg = (f"Week: {short_date(snap['week_start'])}–{short_date(snap['week_end'])}, {snap['week_end'][:4]}.\n\n"
           f"DATA (closing prices, {', '.join(snap['sources'])}):\n{json.dumps(data_facts(snap), ensure_ascii=False)}\n\n"
           f"EVIDENCE:\n{json.dumps(ev, ensure_ascii=False)}\n\n"
           "Pick the week's main story from the biggest moves and the strongest evidence. Write the issue JSON.")
    if feedback:
        msg += ("\n\nYour previous draft failed these checks. Fix every one, change nothing else that passed, "
                "and drop any figure you can't support:\n- " + "\n- ".join(feedback) +
                f"\n\nPrevious draft:\n{json.dumps(previous, ensure_ascii=False)}")
    return msg


def draft(snap, evidence, feedback=None, previous=None):
    return llm.json_of(llm.call(SYSTEM, _user(snap, evidence, feedback, previous), max_tokens=12000))


def charts(snap, d):
    """Chart specs built from the data file, plus the writer's optional comparison chart."""
    end = short_date(snap["week_end"])
    src = f"{snap['sources'][0]} · {end}, {snap['week_end'][:4]}"
    featured = d.get("featured", "")
    caps = sorted((s for s in snap["stocks"].values() if s.get("market_cap")), key=lambda s: -s["market_cap"])
    out = [{
        "id": "market-value", "type": "hbar", "title": "Who's biggest now",
        "subtitle": f"Market value at the {end} close, $ trillions",
        "rows": [{"label": s["name"], "value": round(s["market_cap"] / 1e12, 2),
                  "display": fmt_money(s["market_cap"]), **({"hero": True} if s["name"] == featured else {})}
                 for s in caps[:6]],
        "source": f"{snap['sources'][0]}, SEC filings · {end}", "note": "Approximate: closing price x shares outstanding"}]
    moves = sorted(snap["stocks"].values(), key=lambda s: -s["week_pct"])
    out.append({
        "id": "week-moves", "type": "signed", "title": "How the week ended",
        "subtitle": f"Change from last Friday's close to {end}",
        "rows": [{"label": s["name"], "value": s["week_pct"], "display": fmt_pct(s["week_pct"]),
                  **({"hero": True} if s["name"] == featured else {})} for s in moves],
        "source": src})
    monday = date.fromisoformat(snap["week_end"]) + timedelta(days=3)
    events = {e["date"]: e for e in d.get("next_week", [])}
    days = []
    for i in range(5):
        day = monday + timedelta(days=i)
        cell = {"day": f"{day:%a}".upper(), "date": short_date(day)}
        if day.isoformat() in events:
            ev = events[day.isoformat()]
            cell.update({"event": ev.get("event", "")[:22], "detail": ev.get("detail", "")[:18], "hero": True})
        days.append(cell)
    first_src = d["next_week"][0]["source"] if d.get("next_week") else src
    out.append({"id": "calendar", "type": "calendar", "title": "The dates that matter",
                "subtitle": f"Week of {short_date(monday)}, {monday.year}", "days": days, "source": first_src})
    cc = d.get("compare_chart")
    if cc and cc.get("rows"):
        out.append({"id": "compare", "type": "compare", "title": cc["title"], "subtitle": cc.get("subtitle", ""),
                    "rows": cc["rows"], "source": cc["source"]})
    return out


def assemble(snap, d):
    """The issue JSON that engine/charts.py and engine/emails.py render."""
    end = date.fromisoformat(snap["week_end"])
    sat, sun = end + timedelta(days=1), end + timedelta(days=2)
    issue_id = snap["week_end"]
    specs = charts(snap, d)
    causes = d["causes"]
    cc = d.get("compare_chart")
    if cc and cc.get("rows") and isinstance(cc.get("cause"), int) and 0 <= cc["cause"] < len(causes):
        causes[cc["cause"]]["chart"] = "compare"
    start = date.fromisoformat(snap["week_start"])
    return {
        "issue": issue_id,
        "week": f"{start:%b} {start.day}–{end.day}, {end.year}" if start.month == end.month
        else f"{short_date(start)}–{short_date(end)}, {end.year}",
        "charts": specs,
        "site": SITE,
        "email": {
            "saturday": {**d["saturday"], "date": f"{sat:%a}, {short_date(sat)}, {sat.year}"},
            "sunday": {**d["sunday"], "date": f"{sun:%a}, {short_date(sun)}, {sun.year}"},
            "five": d["five"],
            "next_week": [{"when": f"{date.fromisoformat(e['date']):%a}, {short_date(e['date'])}",
                           "what": e["what"], "source": e["source"]} for e in d.get("next_week", [])],
            "teaser": d["teaser"],
            "causes": causes,
            "after_causes": {**d["after_causes"], "chart": "week-moves"},
            "next_text": d["next_text"],
            "featured": d["featured"],
            "bull": d["bull"],
            "bear": d["bear"],
            "table": d["table"],
        },
    }
