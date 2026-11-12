"""Find and compare the numbers in a piece of text.

Used to check that every figure in an issue matches either the market-data file or
the exact text of a cited source.
"""
import re

UNITS = {"t": 1e12, "trillion": 1e12, "b": 1e9, "bn": 1e9, "billion": 1e9, "m": 1e6, "million": 1e6,
         "k": 1e3, "thousand": 1e3}
MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"

# Names and labels whose digits are not claims.
IGNORE = [
    r"S&P\s?500", r"Nasdaq[- ]?100", r"Russell\s?2000", r"Dow\s?30", r"Mag(?:nificent)?\s?7", r"\bQ[1-4]\b",
    r"\bFY\s?\d{2,4}\b", r"\b\d{1,2}(?:st|nd|rd|th)\b", rf"{MONTHS}\s+\d{{1,2}}(?:\s*[–-]\s*\d{{1,2}})?(?:,\s*\d{{4}})?",
    r"\b\d{1,2}:\d{2}\s?(?:am|pm|AM|PM)?\b", r"\b(?:19|20)\d{2}\b(?!\s?%)", r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b[A-Z]{2,5}\d\b", r"#\d\b", r"\b\d\.\s",
]
NUM = re.compile(
    r"(?P<sign>[−\-+])?\s?(?P<cur>\$)?(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?"
    r"(?P<unit>%|percent\b|trillion\b|billion\b|million\b|thousand\b|bn\b|[TBMK]\b)?",
    re.I)


def clean(text):
    text = str(text)
    for pat in IGNORE:
        text = re.sub(pat, " ", text)
    return text


def extract(text, small_ints=False):
    """Return [(value, kind, raw, step)]: kind is 'pct' or 'num', value is absolute,
    step is the precision the text was written to (for "$4.6T", 0.1e12)."""
    out = []
    for m in NUM.finditer(clean(text)):
        raw = m.group(0).strip()
        digits = m.group("num").replace(",", "")
        n = float(digits)
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        step = 10 ** -decimals
        unit = (m.group("unit") or "").lower()
        if unit in ("%", "percent"):
            out.append((abs(n), "pct", raw, step))
            continue
        if unit:
            n *= UNITS[unit]
            step *= UNITS[unit]
        elif not m.group("cur") and n <= 12 and float(n).is_integer() and not small_ints:
            continue  # small counts like "3 causes" or "next 7 days" are structure, not claims
        out.append((abs(n), "num", raw, step))
    return out


def matches(value, kind, step, allowed):
    """True if an allowed number of the same kind rounds to what the text says.

    Rounding to the text's own precision is allowed ("$4.6T" for 4.62T, "25%" for 24.8%),
    plus 0.5% slack for small differences between data vendors.
    """
    for v, k in allowed:
        if k == kind and abs(value - v) <= step / 2 + 0.005 * v + 1e-9:
            return True
    return False
