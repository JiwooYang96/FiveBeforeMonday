"""Five Before Monday chart engine.

Renders email-safe PNG charts (1200 px wide, shown at 600 px) from a JSON issue file.
Charts carry their own newsprint background, so they look the same in light and dark email clients.

Usage: python3 engine/charts.py engine/data/<issue>.json img/
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

# Brand tokens, shared with the reels (reels_generator/src/theme.ts, palette "broadsheet").
BG = "#fbf7ee"  # newsprint card
INK = "#16130f"
SOFT = "#5d564b"
RULE = "#cfc6b4"
BLUE = "#1d4f91"
BLUE_DIM = "#a9bcd6"
HIGHLIGHT = "#ffd23f"
RED = "#c8372d"
GREEN = "#1f8a57"
BRAND = "FIVE BEFORE MONDAY"
# Old names, kept for anything importing them.
GOLD, GOLD_DIM, GRID = BLUE, BLUE_DIM, RULE

WIDTH_IN = 4.5  # 4.5 in x 266.67 dpi = 1200 px; a narrow canvas makes text larger relative to the width, for phones
DPI = 1200 / 4.5

# Bundled OFL fonts (engine/fonts): Instrument Serif for titles and numbers, Source Sans 3 for labels.
FONT_DIR = Path(__file__).parent / "fonts"
for _f in FONT_DIR.glob("*.ttf"):
    font_manager.fontManager.addfont(str(_f))


def _has(name):
    try:
        font_manager.findfont(name, fallback_to_default=False)
        return True
    except ValueError:
        return False


SERIF = "Instrument Serif" if _has("Instrument Serif") else "DejaVu Serif"
SANS = "Source Sans 3" if _has("Source Sans 3") else "DejaVu Sans"

plt.rcParams.update({"font.family": SANS, "font.weight": "semibold", "text.color": INK, "axes.edgecolor": BG})


def _frame(height_in, spec):
    fig = plt.figure(figsize=(WIDTH_IN, height_in), dpi=DPI, facecolor=BG)
    # Newspaper double rule across the top.
    for y, lw in ((1 - 0.05 / height_in, 2.2), (1 - 0.10 / height_in, 0.8)):
        fig.add_artist(plt.Line2D([0.055, 0.945], [y, y], color=INK, linewidth=lw, transform=fig.transFigure))
    top = 1 - 0.20 / height_in
    fig.text(0.055, top, spec["title"], fontsize=21, family=SERIF, fontweight="normal", color=INK, va="top")
    if spec.get("subtitle"):
        fig.text(0.055, top - 0.36 / height_in, spec["subtitle"], fontsize=9.5, color=SOFT, va="top")
    foot = 0.22 / height_in
    fig.add_artist(plt.Line2D([0.055, 0.945], [foot + 0.12 / height_in] * 2, color=RULE, linewidth=0.7,
                              transform=fig.transFigure))
    fig.text(0.055, foot, f"Source: {spec['source']}", fontsize=7.5, color=SOFT, va="center")
    fig.text(0.945, foot, BRAND, fontsize=7.5, color=RED, fontweight="bold", ha="right", va="center")
    if spec.get("note"):
        fig.text(0.055, foot + 0.24 / height_in, spec["note"], fontsize=7.5, color=SOFT, va="center", style="italic")
    return fig


def _plot_area(fig, height_in, spec, left=0.24, right=0.86, extra_bottom=0.0):
    top_pad = 1.05 if spec.get("subtitle") else 0.8
    bottom_pad = (0.68 if spec.get("note") else 0.48) + extra_bottom
    ax = fig.add_axes([left, bottom_pad / height_in, right - left, 1 - (top_pad + bottom_pad) / height_in])
    ax.set_facecolor(BG)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0, colors=INK)
    return ax


def _value(ax, x, y, text, color, **kw):
    ax.text(x, y, text, va="center", fontsize=16, family=SERIF, fontweight="normal", color=color, **kw)


def hbar(spec):
    rows = spec["rows"]
    h = 1.55 + 0.42 * len(rows)
    fig = _frame(h, spec)
    ax = _plot_area(fig, h, spec)
    vmax = max(r["value"] for r in rows)
    ys = list(range(len(rows)))[::-1]
    for y, r in zip(ys, rows):
        hero = r.get("hero")
        ax.barh(y, r["value"], height=0.6, color=RED if hero else BLUE_DIM, zorder=2)
        if hero:  # highlighter mark behind the bar that matters
            ax.barh(y, r["value"] + vmax * 0.02, height=0.86, left=-vmax * 0.01, color=HIGHLIGHT, zorder=1)
        _value(ax, r["value"] + vmax * 0.03, y, r["display"], RED if hero else BLUE)
    ax.set_yticks(ys, [r["label"] for r in rows], fontsize=10.5)
    ax.set_xlim(0, vmax * 1.18)
    ax.set_xticks([])
    return fig


def signed(spec):
    rows = spec["rows"]
    h = 1.75 + 0.42 * len(rows)
    fig = _frame(h, spec)
    ax = _plot_area(fig, h, spec)
    vmax = max(abs(r["value"]) for r in rows)
    lo = min(0, min(r["value"] for r in rows))
    ys = list(range(len(rows)))[::-1]
    ax.axvline(0, color=INK, linewidth=1, zorder=3)
    for y, r in zip(ys, rows):
        color = GREEN if r["value"] >= 0 else RED
        alpha = 1.0 if r.get("hero") else 0.8
        if r.get("hero"):
            ax.barh(y, r["value"], height=0.86, color=HIGHLIGHT, zorder=1)
        ax.barh(y, r["value"], height=0.58, color=color, alpha=alpha, zorder=2)
        x = r["value"] + (vmax * 0.03 if r["value"] >= 0 else -vmax * 0.03)
        _value(ax, x, y, r["display"], color, ha="left" if r["value"] >= 0 else "right")
    ax.set_yticks(ys, [r["label"] for r in rows], fontsize=10.5)
    hi = max(0, max(r["value"] for r in rows))
    ax.set_xlim(lo - vmax * 0.8 if lo < 0 else 0, hi + vmax * 0.8 if hi > 0 else vmax * 0.1)
    ax.set_xticks([])
    return fig


def compare(spec):
    rows = spec["rows"]
    h = 3.3
    fig = _frame(h, spec)
    ax = _plot_area(fig, h, spec, left=0.12, right=0.88, extra_bottom=0.3)
    vmax = max(r["value"] for r in rows)
    xs = range(len(rows))
    for x, r in zip(xs, rows):
        hero = r.get("hero")
        if hero:
            ax.bar(x, r["value"] * 1.02, width=0.62, color=HIGHLIGHT, zorder=1)
        ax.bar(x, r["value"], width=0.5, color=BLUE if hero else BLUE_DIM, zorder=2)
        ax.text(x, r["value"] + vmax * 0.05, r["display"], ha="center", va="bottom", fontsize=22, family=SERIF,
                fontweight="normal", color=BLUE if hero else SOFT)
    ax.set_xticks(list(xs), [r["label"] for r in rows], fontsize=10.5)
    ax.set_ylim(0, vmax * 1.28)
    ax.set_yticks([])
    ax.axhline(0, color=INK, linewidth=1)
    return fig


def calendar(spec):
    days = spec["days"]
    h = 2.9
    fig = _frame(h, spec)
    ax = fig.add_axes([0.055, 0.62 / h, 0.89, 1 - 1.62 / h])
    ax.set_axis_off()
    ax.set_xlim(0, len(days))
    ax.set_ylim(0, 1)
    for i, d in enumerate(days):
        hero = d.get("hero")
        box = FancyBboxPatch((i + 0.06, 0.02), 0.88, 0.96, boxstyle="round,pad=0,rounding_size=0.02",
                             facecolor=HIGHLIGHT if hero else BG, edgecolor=INK if hero else RULE,
                             linewidth=1.2, mutation_aspect=0.5)
        ax.add_patch(box)
        ax.text(i + 0.5, 0.84, d["day"], ha="center", fontsize=8.5, fontweight="bold", color=RED if hero else SOFT)
        ax.text(i + 0.5, 0.62, d["date"], ha="center", fontsize=15, family=SERIF, fontweight="normal", color=INK)
        if d.get("event"):
            ax.text(i + 0.5, 0.40, d["event"].replace(" ", "\n", 1), ha="center", va="center", fontsize=7.5,
                    fontweight="bold", color=INK, linespacing=1.1)
            ax.text(i + 0.5, 0.15, d.get("detail", "").replace(" ", "\n", 1), ha="center", va="center", fontsize=6,
                    color=SOFT, linespacing=1.0)
        else:
            ax.text(i + 0.5, 0.25, "–", ha="center", fontsize=10, color=RULE)
    return fig


RENDERERS = {"hbar": hbar, "signed": signed, "compare": compare, "calendar": calendar}


def main(issue_path, out_dir):
    issue = json.loads(Path(issue_path).read_text())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for spec in issue["charts"]:
        fig = RENDERERS[spec["type"]](spec)
        path = out / f"{issue['issue']}-{spec['id']}.png"
        fig.savefig(path, dpi=DPI, facecolor=BG)
        plt.close(fig)
        print(path)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
