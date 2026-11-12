"""Five Before Monday email renderer.

Builds the Saturday brief and the Sunday report as email-safe HTML (tables + inline styles, 600 px wide)
from an issue JSON. Charts are PNGs from engine/charts.py, hosted on the website under /img/.

Usage: python3 engine/emails.py engine/data/<issue>.json emails/out/
"""
import html
import json
import sys
from pathlib import Path

# Light body for reliability across email clients; the dark brand lives in the header and the charts.
PAGE = "#ece6da"
CARD = "#fffdf8"
INK = "#191510"
SOFT = "#6f675c"
LINE = "#e4dccd"
DARK = "#0c0b0a"
GOLD = "#f2c25b"
GOLD_TEXT = "#a86f0f"
UP = "#1f8a57"
DOWN = "#c8372d"
DISPLAY = "'Arial Black', 'Helvetica Neue', Helvetica, Arial, sans-serif"
BODY = "Helvetica, Arial, sans-serif"
MONO = "'SFMono-Regular', Menlo, Consolas, monospace"
TONE = {"up": UP, "down": DOWN, "gold": GOLD_TEXT}


def e(s):
    return html.escape(str(s), quote=True)


def chart_alt(spec):
    parts = [spec["title"] + "."]
    if spec.get("rows"):
        parts.append(", ".join(f"{r['label']} {r['display']}" for r in spec["rows"]) + ".")
    if spec.get("days"):
        parts += [f"{d['day']} {d['date']}: {d['event']} ({d.get('detail', '')})." for d in spec["days"] if d.get("event")]
    if spec.get("note"):
        parts.append(spec["note"] + ".")
    parts.append(f"Source: {spec['source']}.")
    return " ".join(parts)


class Issue:
    def __init__(self, data):
        self.d = data
        self.m = data["email"]
        self.charts = {c["id"]: c for c in data["charts"]}
        self.site = data["site"].rstrip("/")

    def chart(self, cid):
        spec = self.charts[cid]
        src = f"{self.site}/img/{self.d['issue']}-{cid}.png"
        return (f'<tr><td style="padding:8px 24px 20px;"><img src="{e(src)}" width="552" alt="{e(chart_alt(spec))}" '
                f'style="display:block;width:100%;max-width:552px;height:auto;border:0;border-radius:10px;"></td></tr>')


def p(text, size=16, color=INK, pad="0 24px 14px", weight="normal"):
    return (f'<tr><td style="padding:{pad};font:{weight} {size}px/1.55 {BODY};color:{color};">{text}</td></tr>')


def h2(text, pad="26px 24px 10px"):
    return (f'<tr><td style="padding:{pad};font:900 22px/1.1 {DISPLAY};color:{INK};text-transform:uppercase;'
            f'letter-spacing:0.5px;">{e(text)}</td></tr>')


def kicker(text, pad="22px 24px 6px"):
    return (f'<tr><td style="padding:{pad};font:bold 12px/1 {MONO};color:{GOLD_TEXT};letter-spacing:1.5px;'
            f'text-transform:uppercase;">{e(text)}</td></tr>')


def rule():
    return f'<tr><td style="padding:6px 24px;"><div style="border-top:1px solid {LINE};font-size:0;line-height:0;">&nbsp;</div></td></tr>'


def five_rows(items, big=True):
    rows = []
    for i, it in enumerate(items, 1):
        size = 34 if big else 24
        rows.append(
            f'<tr><td style="padding:0 24px;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-bottom:1px solid {LINE};"><tr>'
            f'<td width="{118 if big else 92}" valign="top" style="padding:14px 10px 14px 0;font:900 {size}px/1 {DISPLAY};'
            f'color:{TONE[it["tone"]]};white-space:nowrap;">{e(it["num"])}</td>'
            f'<td valign="top" style="padding:14px 0;font:normal 15px/1.5 {BODY};color:{INK};">{e(it["text"])}'
            f'<div style="font:normal 12px/1.4 {MONO};color:{SOFT};padding-top:4px;">{e(it["source"])}</div></td>'
            f'</tr></table></td></tr>')
    return "".join(rows)


def button(label, href):
    return (f'<tr><td style="padding:8px 24px 24px;"><table role="presentation" cellpadding="0" cellspacing="0" border="0">'
            f'<tr><td bgcolor="{GOLD}" style="border-radius:8px;"><a href="{e(href)}" style="display:inline-block;'
            f'padding:14px 22px;font:bold 16px/1 {BODY};color:{DARK};text-decoration:none;border-radius:8px;">'
            f'{e(label)}</a></td></tr></table></td></tr>')


def shell(issue, kind, date_label, body_rows):
    m = issue.m[kind]
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light">
<title>{e(m['subject'])}</title>
</head>
<body style="margin:0;padding:0;background:{PAGE};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{PAGE};">{e(m['preheader'])}&#8199;&#65279;&#847;&#8199;&#65279;&#847;&#8199;&#65279;&#847;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{PAGE}" style="background:{PAGE};">
<tr><td align="center" style="padding:20px 10px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;">
<tr><td bgcolor="{DARK}" style="background:{DARK};border-radius:14px 14px 0 0;padding:20px 24px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td style="font:900 17px/1.2 {DISPLAY};color:#f4efe6;text-transform:uppercase;letter-spacing:0.5px;white-space:nowrap;">
      <span style="background:{GOLD};color:{DARK};padding:2px 7px;border-radius:4px;">5</span>&nbsp;Before&nbsp;Monday</td>
    <td align="right" style="font:normal 11px/1.3 {MONO};color:#9c9488;white-space:nowrap;padding-left:8px;">{e(date_label)}</td>
  </tr></table>
</td></tr>
<tr><td bgcolor="{CARD}" style="background:{CARD};border-radius:0 0 14px 14px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
{body_rows}
</table>
</td></tr>
<tr><td style="padding:18px 24px 6px;font:normal 12px/1.55 {BODY};color:{SOFT};">
  Five Before Monday explains what moved big tech stocks. It is not investment advice and never a recommendation to buy or sell.
  Researched and drafted with AI; every figure names its source. <a href="{e(issue.site)}/disclaimer.html" style="color:{SOFT};">Disclaimer</a>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


def saturday(issue):
    m = issue.m
    rows = [
        kicker(f"This week in five · {issue.d['week']}", pad="24px 24px 6px"),
        p("The five numbers that moved big tech this week, each with where it came from.", size=16, color=SOFT,
          pad="4px 24px 6px"),
        five_rows(m["five"]),
        h2("Next week"),
    ]
    for ev in m["next_week"]:
        rows.append(p(f'<b>{e(ev["when"])}</b>: {e(ev["what"])} '
                      f'<span style="font:normal 12px {MONO};color:{SOFT};">{e(ev["source"])}</span>', size=15))
    rows += [
        rule(),
        p(f'<b>In Sunday\'s report</b><br>{e(m["teaser"])}', size=15, pad="14px 24px 8px"),
        button("Become a founding member", issue.site + "/#founding"),
    ]
    return shell(issue, "saturday", m["saturday"].get("date", "Saturday"), "".join(rows))


def sunday(issue):
    m = issue.m
    s = m["sunday"]
    rows = [
        kicker(f"Sunday report · {issue.d['week']}", pad="24px 24px 8px"),
        f'<tr><td style="padding:0 24px 12px;font:900 30px/1.08 {DISPLAY};color:{INK};text-transform:uppercase;">{e(s["headline"])}</td></tr>',
        p(e(s["lead"]), size=16, color=SOFT),
        issue.chart("market-value"),
        h2("1. The week in five", pad="10px 24px 4px"),
        five_rows(m["five"], big=False),
        h2("2. Why it moved"),
    ]
    for c in m["causes"]:
        rows.append(
            f'<tr><td style="padding:6px 24px 10px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'border="0" style="border:1px solid {LINE};border-radius:10px;"><tr><td style="padding:16px 18px;">'
            f'<div style="font:bold 15px/1.3 {BODY};color:{INK};">{e(c["title"])}</div>'
            f'<div style="font:900 32px/1.1 {DISPLAY};color:{GOLD_TEXT};padding:6px 0;">{e(c["stat"])}</div>'
            f'<div style="font:normal 15px/1.55 {BODY};color:{INK};">{e(c["text"])}</div>'
            f'<div style="font:normal 12px/1.4 {MONO};color:{SOFT};padding-top:6px;">{e(c["source"])}</div>'
            f'</td></tr></table></td></tr>')
        if c.get("chart"):
            rows.append(issue.chart(c["chart"]))
    a = m["after_causes"]
    rows += [
        p(f'<b>{e(a["title"])}</b><br>{e(a["text"])}', size=15, pad="10px 24px 6px"),
        issue.chart(a["chart"]),
        h2("3. The next 7 days"),
        p(e(m["next_text"]), size=15),
        issue.chart("calendar"),
        h2(f"4. Bull vs. bear: {m['featured']}"),
        p("The strongest arguments on each side, as they're being made in this week's coverage. A map of the debate, not a recommendation.",
          size=14, color=SOFT),
    ]
    for label, color, items in (("The bull case", UP, m["bull"]), ("The bear case", DOWN, m["bear"])):
        li = "".join(f'<li style="margin:0 0 6px;">{e(x)}</li>' for x in items)
        rows.append(
            f'<tr><td style="padding:4px 24px 10px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'border="0" style="border-left:3px solid {color};"><tr><td style="padding:4px 0 4px 14px;">'
            f'<div style="font:bold 15px/1.3 {BODY};color:{color};padding-bottom:6px;">{label}</div>'
            f'<ul style="margin:0;padding-left:18px;font:normal 15px/1.5 {BODY};color:{INK};">{li}</ul>'
            f'</td></tr></table></td></tr>')
    trs = "".join(
        f'<tr><td style="padding:8px 8px 8px 0;border-bottom:1px solid {LINE};font:normal 14px/1.4 {BODY};color:{INK};">{e(r[0])}</td>'
        f'<td style="padding:8px 8px 8px 0;border-bottom:1px solid {LINE};font:bold 14px/1.4 {MONO};color:{INK};white-space:nowrap;">{e(r[1])}</td>'
        f'<td style="padding:8px 0;border-bottom:1px solid {LINE};font:normal 12px/1.4 {MONO};color:{SOFT};">{e(r[2])}<br>{e(r[3])}</td></tr>'
        for r in m["table"])
    rows += [
        h2("5. The numbers"),
        f'<tr><td style="padding:0 24px 10px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{trs}</table></td></tr>',
        h2("6. How this issue was made"),
        p("Researched and drafted with AI from the outlets named above. Every figure traces to a page that was opened, and each claim was checked against its source. Intraday figures are labelled as intraday.",
          size=14, color=SOFT, pad="0 24px 24px"),
    ]
    return shell(issue, "sunday", s.get("date", "Sunday"), "".join(rows))


def main(issue_path, out_dir):
    issue = Issue(json.loads(Path(issue_path).read_text()))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for kind, fn in (("saturday", saturday), ("sunday", sunday)):
        path = out / f"{issue.d['issue']}-{kind}.html"
        path.write_text(fn(issue))
        print(path, f"{path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
