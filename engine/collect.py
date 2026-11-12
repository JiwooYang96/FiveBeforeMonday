"""Collect the week's market data for Five Before Monday.

Pulls daily closes for the tracked big-tech stocks and indices (Yahoo Finance chart
data, Stooq as a fallback) and shares outstanding from SEC EDGAR, then works out the
numbers every issue leans on: weekly and monthly moves, distance from the 52-week
high, and approximate market value.

Every number the newsletter states about prices comes from this file, so the checker
can compare the text against it.

Usage: python3 engine/collect.py [YYYY-MM-DD] > engine/data/raw/<date>.json
"""
import csv
import io
import json
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

UA = "FiveBeforeMonday research fivebeforemonday@gmail.com"

STOCKS = {
    # ticker: (name, SEC CIK)
    "NVDA": ("Nvidia", 1045810),
    "AAPL": ("Apple", 320193),
    "MSFT": ("Microsoft", 789019),
    "GOOGL": ("Alphabet", 1652044),
    "AMZN": ("Amazon", 1018724),
    "META": ("Meta", 1326801),
    "AVGO": ("Broadcom", 1730168),
    "TSLA": ("Tesla", 1318605),
}
INDICES = {
    "^NDX": ("Nasdaq-100", "^ndx"),
    "^GSPC": ("S&P 500", "^spx"),
    "^SOX": ("Chip index (SOX)", "^sox"),
}


def _get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as err:  # network hiccups and 429s: back off and retry
            last = err
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}: {last}")


# ---------- price sources ----------

def yahoo_closes(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(symbol)}?range=1y&interval=1d"
    data = json.loads(_get(url))["chart"]["result"][0]
    out = []
    for ts, c in zip(data["timestamp"], data["indicators"]["quote"][0]["close"]):
        if c is not None:
            d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            out.append((d.isoformat(), round(float(c), 4)))
    return out


def stooq_closes(symbol):
    text = _get(f"https://stooq.com/q/d/l/?s={urllib.request.quote(symbol)}&i=d").decode()
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or "Close" not in rows[0]:
        raise RuntimeError(f"Stooq returned no data for {symbol}")
    cutoff = (date.today() - timedelta(days=380)).isoformat()
    return [(r["Date"], float(r["Close"])) for r in rows if r["Date"] >= cutoff and r["Close"]]


def closes_for(yahoo_symbol, stooq_symbol):
    try:
        return yahoo_closes(yahoo_symbol), "Yahoo Finance"
    except Exception as err:
        print(f"Yahoo failed for {yahoo_symbol}: {err}; trying Stooq", file=sys.stderr)
        return stooq_closes(stooq_symbol), "Stooq"


# ---------- shares outstanding (SEC EDGAR) ----------

def shares_outstanding(cik):
    """Latest total common shares outstanding from the company's SEC filings.

    Companies with several share classes (Alphabet, Meta) report one value per class
    on the same date, so values sharing the latest date and filing are summed.
    """
    facts = json.loads(_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"))
    units = facts["facts"].get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {})
    vals = units.get("shares", [])
    if not vals:
        return None, None
    latest_end = max(v["end"] for v in vals)
    same = [v for v in vals if v["end"] == latest_end]
    accn = max(same, key=lambda v: v.get("filed", ""))["accn"]
    total = sum({v["val"] for v in same if v["accn"] == accn})
    return int(total), latest_end


# ---------- maths ----------

def week_bounds(as_of):
    """Monday..Friday of the trading week that contains as_of (weekends map back to that week)."""
    monday = as_of - timedelta(days=as_of.weekday())
    return monday, monday + timedelta(days=4)


def pct(a, b):
    return round((a / b - 1) * 100, 2)


def summarise(closes, monday, friday):
    week = [(d, c) for d, c in closes if monday.isoformat() <= d <= friday.isoformat()]
    before = [(d, c) for d, c in closes if d < monday.isoformat()]
    if not week or not before:
        raise RuntimeError("not enough data for the week")
    last_d, last = week[-1]
    prev_close = before[-1][1]
    upto = [(d, c) for d, c in closes if d <= last_d]
    month_ago = upto[-22][1] if len(upto) >= 22 else upto[0][1]
    year = upto[-252:]
    hi_d, hi = max(year, key=lambda x: x[1])
    day_prev = upto[-2][1] if len(upto) >= 2 else prev_close
    return {
        "close": round(last, 2),
        "close_date": last_d,
        "prev_week_close": round(prev_close, 2),
        "week_pct": pct(last, prev_close),
        "day_pct": pct(last, day_prev),
        "month_pct": pct(last, month_ago),
        "high_52w": round(hi, 2),
        "high_52w_date": hi_d,
        "from_high_pct": pct(last, hi),
        "week_closes": [[d, round(c, 2)] for d, c in week],
    }


def trading_week(as_of=None):
    """Monday and Friday of the trading week for as_of (Saturday and Sunday belong to the week just ended)."""
    as_of = as_of or datetime.now(timezone.utc).date()
    return week_bounds(as_of if as_of.weekday() < 5 else as_of - timedelta(days=as_of.weekday() - 4))


def collect(as_of=None):
    as_of = as_of or datetime.now(timezone.utc).date()
    monday, friday = trading_week(as_of)
    snap = {"as_of": as_of.isoformat(), "week_start": monday.isoformat(), "week_end": friday.isoformat(),
            "stocks": {}, "indices": {}, "sources": set()}
    for tk, (name, cik) in STOCKS.items():
        closes, src = closes_for(tk, f"{tk.lower()}.us")
        snap["sources"].add(src)
        row = {"name": name, **summarise(closes, monday, friday)}
        try:
            shares, shares_date = shares_outstanding(cik)
        except Exception as err:
            print(f"EDGAR failed for {tk}: {err}", file=sys.stderr)
            shares, shares_date = None, None
        if shares:
            row["shares"] = shares
            row["shares_date"] = shares_date
            row["market_cap"] = round(row["close"] * shares)
        snap["stocks"][tk] = row
    for sym, (name, stooq) in INDICES.items():
        try:
            closes, src = closes_for(sym, stooq)
            snap["indices"][sym] = {"name": name, **summarise(closes, monday, friday)}
            snap["sources"].add(src)
        except Exception as err:
            print(f"index {sym} skipped: {err}", file=sys.stderr)
    snap["sources"] = sorted(snap["sources"]) + ["SEC EDGAR (shares outstanding)"]
    return snap


if __name__ == "__main__":
    from pathlib import Path
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    day = date.fromisoformat(args[0]) if args else None
    snap = collect(day)
    if "--save" in sys.argv:  # engine/data/raw/<week_end>.json, read by the research task and the build
        out = Path(__file__).resolve().parent / "data/raw" / f"{snap['week_end']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snap, indent=2))
        print(out)
    else:
        print(json.dumps(snap, indent=2))
