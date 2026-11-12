"""Five Before Monday chart engine.

Renders email-safe PNG charts (1200 px wide, shown at 600 px) from a JSON issue file.
Charts carry their own dark background, so they look the same in light and dark email clients.

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

# Brand tokens, shared with the reels (reels_generator/src/theme.ts, palette "gold").
BG = "#17140f"
INK = "#f4efe6"
SOFT = "#8d857a"
GRID = "#2a251d"
GOLD = "#f2c25b"
GOLD_DIM = "#5a4a2a"
RED = "#e0483d"
GREEN = "#2fa36b"
BRAND = "FIVE BEFORE MONDAY"

WIDTH_IN = 4.5  # 4.5 in x 266.67 dpi = 1200 px; a narrow canvas makes text larger relative to the width, for phones
DPI = 1200 / 4.5


def _font():
    for name in ("Inter", "DejaVu Sans"):
        try:
            font_manager.findfont(name, fallback_to_default=False)
            return name
        except ValueError:
            continue
    return "sans-serif"


plt.rcParams.update({"font.family": _font(), "text.color": INK, "axes.edgecolor": BG})


def _frame(height_in, spec):
    fig = plt.figure(figsize=(WIDTH_IN, height_in), dpi=DPI, facecolor=BG)
    top = 1 - 0.36 / height_in
    fig.text(0.055, top, spec["title"], fontsize=15, fontweight="bold", color=INK, va="top")
    if spec.get("subtitle"):
        fig.text(0.055, top - 0.30 / height_in, spec["subtitle"], fontsize=9.5, color=SOFT, va="top")
    foot = 0.22 / height_in
    fig.text(0.055, foot, f"Source: {spec['source']}", fontsize=7.5, color=SOFT, va="center")
    fig.text(0.945, foot, BRAND, fontsize=7.5, color=GOLD, fontweight="bold", ha="right", va="center")
    if spec.get("note"):
        fig.text(0.055, foot + 0.2 / height_in, spec["note"], fontsize=7.5, color=SOFT, va="center", style="italic")
    return fig


def _plot_area(fig, height_in, spec, left=0.24, right=0.86, extra_bottom=0.0):
    top_pad = 0.95 if spec.get("subtitle") else 0.7
    bottom_pad = (0.62 if spec.get("note") else 0.45) + extra_bottom
    ax = fig.add_axes([left, bottom_pad / height_in, right - left, 1 - (top_pad + bottom_pad) / height_in])
    ax.set_facecolor(BG)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0, colors=INK)
    return ax


def hbar(spec):
    rows = spec["rows"]
    h = 1.55 + 0.42 * len(rows)
    fig = _frame(h, spec)
    ax = _plot_area(fig, h, spec)
    vmax = max(r["value"] for r in rows)
    ys = list(range(len(rows)))[::-1]
    for y, r in zip(ys, rows):
        color = GOLD if r.get("hero") else GOLD_DIM
        ax.barh(y, r["value"], height=0.58, color=color, zorder=2)
        ax.text(r["value"] + vmax * 0.02, y, r["display"], va="center", fontsize=11, fontweight="bold",
                color=INK)
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
    ax.axvline(0, color=SOFT, linewidth=0.8, zorder=3)
    for y, r in zip(ys, rows):
        color = GREEN if r["value"] >= 0 else RED
        alpha = 1.0 if r.get("hero") else 0.55
        ax.barh(y, r["value"], height=0.58, color=color, alpha=alpha, zorder=2)
        x = r["value"] + (vmax * 0.03 if r["value"] >= 0 else -vmax * 0.03)
        ax.text(x, y, r["display"], va="center", ha="left" if r["value"] >= 0 else "right",
                fontsize=11, fontweight="bold", color=INK)
    ax.set_yticks(ys, [r["label"] for r in rows], fontsize=10.5)
    hi = max(0, max(r["value"] for r in rows))
    ax.set_xlim(lo - vmax * 0.55 if lo < 0 else 0, hi + vmax * 0.55 if hi > 0 else vmax * 0.1)
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
        color = GOLD if r.get("hero") else GOLD_DIM
        ax.bar(x, r["value"], width=0.5, color=color, zorder=2)
        ax.text(x, r["value"] + vmax * 0.04, r["display"], ha="center", va="bottom", fontsize=13,
                fontweight="bold", color=INK)
    ax.set_xticks(list(xs), [r["label"] for r in rows], fontsize=10.5)
    ax.set_ylim(0, vmax * 1.28)
    ax.set_yticks([])
    ax.axhline(0, color=GRID, linewidth=1)
    return fig


def calendar(spec):
    days = spec["days"]
    h = 2.55
    fig = _frame(h, spec)
    ax = fig.add_axes([0.055, 0.62 / h, 0.89, 1 - 1.62 / h])
    ax.set_axis_off()
    ax.set_xlim(0, len(days))
    ax.set_ylim(0, 1)
    for i, d in enumerate(days):
        hero = d.get("hero")
        box = FancyBboxPatch((i + 0.06, 0.02), 0.88, 0.96, boxstyle="round,pad=0,rounding_size=0.08",
                             facecolor=GOLD if hero else "#211c15", edgecolor="none", mutation_aspect=0.5)
        ax.add_patch(box)
        fg = BG if hero else SOFT
        ax.text(i + 0.5, 0.80, d["day"], ha="center", fontsize=8.5, fontweight="bold", color=fg)
        ax.text(i + 0.5, 0.58, d["date"], ha="center", fontsize=10.5, fontweight="bold",
                color=BG if hero else INK)
        if d.get("event"):
            ax.text(i + 0.5, 0.33, d["event"].replace(" ", "\n", 1), ha="center", va="center", fontsize=7.5,
                    fontweight="bold", color=BG, linespacing=1.1)
            ax.text(i + 0.5, 0.11, d.get("detail", ""), ha="center", fontsize=7, color=BG)
        else:
            ax.text(i + 0.5, 0.25, "–", ha="center", fontsize=10, color=GRID)
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
