#!/usr/bin/env python3
"""ORB trade playbook: clear entry, stop, and target on each rule.
Synthetic 5-min candles. Illustrative example, not real data.
Education only, not financial advice.
"""

from __future__ import annotations

from pathlib import Path as _Path


def _ensure_inter_fonts():
    out = _Path("fonts")
    needed = ["Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf"]
    if all((out / n).exists() for n in needed):
        return
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    src = "/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf"
    out.mkdir(parents=True, exist_ok=True)
    for w, name in [
        (400, "Inter-Regular.ttf"),
        (500, "Inter-Medium.ttf"),
        (600, "Inter-SemiBold.ttf"),
        (700, "Inter-Bold.ttf"),
    ]:
        instantiateVariableFont(TTFont(src), {"wght": w, "opsz": 18}).save(out / name)


_ensure_inter_fonts()

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Rectangle, Polygon, FancyArrowPatch
from matplotlib.lines import Line2D
from matplotlib.legend_handler import HandlerPatch
import matplotlib.patheffects as pe
from matplotlib.font_manager import FontProperties, fontManager

for _fn in (
    "fonts/Inter-Regular.ttf",
    "fonts/Inter-Medium.ttf",
    "fonts/Inter-SemiBold.ttf",
    "fonts/Inter-Bold.ttf",
):
    fontManager.addfont(_fn)

fp = FontProperties(fname="fonts/Inter-Regular.ttf")
fp_med = FontProperties(fname="fonts/Inter-Medium.ttf")
fp_semb = FontProperties(fname="fonts/Inter-SemiBold.ttf")
fp_bold = FontProperties(fname="fonts/Inter-Bold.ttf")
fp_mono = FontProperties(
    fname="/usr/share/fonts/truetype/sand-box/google/IBM Plex Mono/IBMPlexMono-Regular.ttf"
)
fp_mono_med = FontProperties(
    fname="/usr/share/fonts/truetype/sand-box/google/IBM Plex Mono/IBMPlexMono-Medium.ttf"
)
fp_mono_semb = FontProperties(
    fname="/usr/share/fonts/truetype/sand-box/google/IBM Plex Mono/IBMPlexMono-SemiBold.ttf"
)

# ---------------------------------------------------------------------------
# Theme — match the companion posters
# ---------------------------------------------------------------------------
FIG_BG = "#0b0e14"
AX_BG = "#131722"
GRID = "#1e222d"
SPINE = "#2a2e39"
TEXT = "#d1d4dc"
TEXT_MUTED = "#8b919d"
TEXT_DIM = "#5d636f"
WHITE = "#f4f6f8"
UP = "#26a69a"
DOWN = "#ef5350"
ORB_COLOR = "#5b9cf6"
ORB_FILL = "#5b9cf6"
PM_COLOR = "#c084fc"
OPEN_COLOR = "#6b7280"
ENTRY_COLOR = "#22c55e"
STOP_COLOR = "#ef5350"
TARGET_COLOR = "#34d399"
ZONE_RED = "#ef5350"
ZONE_GREEN = "#26a69a"
ACCENT = "#7dd3fc"
BADGE_RED = "#e35d6a"
GOLD = "#f5c14a"
GRAY = "#9ca3af"

# Consistent example levels
PML = 98.0
ORB_L = 100.0
MID = 101.0          # opening-range midpoint (stop on rule 1)
ORB_H = 102.0
PMH = 104.0
# Rule 1
P1_ENTRY, P1_STOP, P1_TGT = 102.2, 101.0, 104.0
# Rule 2
P2_WICK = 102.8      # failed-break high wick
P2_ENTRY, P2_STOP, P2_TGT = 101.8, 103.0, 100.0
# Rule 3
P3_ENTRY, P3_STOP, P3_TGT = 104.2, 103.4, 107.0  # 104 + 0.5*(104-98)

N_PM = 3
# bars: 0-2 premarket, 3-5 opening range (9:30, 9:35, 9:40), 6+ session
XMIN = -0.6


def stroke(w=3.6, fg=AX_BG):
    return [pe.withStroke(linewidth=w, foreground=fg)]


def tlabel(i: int) -> str:
    # i=0 -> 9:15, i=3 -> 9:30
    minutes = 9 * 60 + 15 + i * 5
    h, m = divmod(minutes, 60)
    return f"{h}:{m:02d}"


def candle(o, h, l, c):
    h = max(h, o, c)
    l = min(l, o, c)
    return (round(o, 2), round(h, 2), round(l, 2), round(c, 2))


# Compact premarket that tags PM high 104 and PM low 98
PM = [
    (100.40, 102.20, 100.20, 101.90),
    (101.90, 104.00, 101.70, 103.10),  # tags PM high
    (103.10, 103.30, 99.55, 100.20),   # lifts into the open (PM low 98 is in the key / formula)
]

# Opening range clearly 100–102 (first 15 min)
ORB = [
    (100.20, 101.25, 100.00, 101.10),  # tags ORB low
    (101.10, 101.75, 100.55, 101.50),
    (101.50, 102.00, 101.20, 101.40),  # tags ORB high
]


def pack(rest):
    return [candle(*b) for b in (PM + ORB + rest)]


# Panel 1: close above ORB high at 102.2, run to PM high 104
# entry at index 7 (second session bar)
P1 = pack([
    (101.40, 101.70, 101.15, 101.45),  # 6  still inside
    (101.45, 102.45, 101.35, 102.20),  # 7  ENTRY — close 102.20
    (102.20, 102.70, 102.00, 102.55),  # 8
    (102.55, 103.15, 102.40, 103.00),  # 9
    (103.00, 103.55, 102.80, 103.40),  # 10
    (103.40, 104.08, 103.20, 104.00),  # 11  TARGET HIT
    (104.00, 104.12, 103.70, 103.85),  # 12
])
P1_ENTRY_X = 7

# Panel 2: poke above ORB high (wick 102.8), close back inside at 101.8, down to 100
P2 = pack([
    (101.40, 101.75, 101.20, 101.60),  # 6
    (101.60, 102.80, 101.50, 102.45),  # 7  failed poke (wick 102.8)
    (102.45, 102.60, 101.50, 101.80),  # 8  ENTRY SHORT — close back below 102
    (101.80, 101.90, 101.25, 101.40),  # 9
    (101.40, 101.55, 100.70, 100.85),  # 10
    (100.85, 101.00, 100.10, 100.05),  # 11  TARGET 100
    (100.05, 100.35, 99.92, 100.15),   # 12
])
P2_ENTRY_X = 8
P2_POKE_X = 7

# Panel 3: break ORB, then close above PM high at 104.2, run to 107
P3 = pack([
    (101.40, 102.40, 101.25, 102.25),  # 6  breaks ORB high
    (102.25, 103.15, 102.10, 102.95),  # 7
    (102.95, 103.70, 102.80, 103.55),  # 8
    (103.55, 104.55, 103.40, 104.20),  # 9  ENTRY — close 104.20 above PM high
    (104.20, 104.90, 104.05, 104.70),  # 10
    (104.70, 105.50, 104.55, 105.30),  # 11
    (105.30, 106.15, 105.15, 105.95),  # 12
    (105.95, 106.60, 105.80, 106.45),  # 13
    (106.45, 107.15, 106.30, 107.00),  # 14  TARGET 107
    (107.00, 107.18, 106.70, 106.88),  # 15
])
P3_ENTRY_X = 9

# Panel 4: two breaks of ORB high, each reclaimed — would-be entries get an X
P4 = pack([
    (101.40, 101.75, 101.20, 101.50),  # 6
    (101.50, 102.65, 101.40, 102.40),  # 7  would-be entry 1 (close above 102)
    (102.40, 102.55, 101.35, 101.50),  # 8  RECLAIM 1
    (101.50, 101.80, 101.20, 101.45),  # 9
    (101.45, 102.70, 101.35, 102.45),  # 10 would-be entry 2
    (102.45, 102.60, 101.30, 101.50),  # 11 RECLAIM 2  — no trade
    (101.50, 101.95, 101.10, 101.35),  # 12 chop
    (101.35, 102.25, 101.15, 102.05),  # 13
    (102.05, 102.35, 101.40, 101.60),  # 14
    (101.60, 101.90, 101.15, 101.40),  # 15
])
P4_FAKE_XS = (7, 10)
P4_RECLAIM_XS = (8, 11)

# Shared x window so panels feel consistent (pad shorter series)
XMAX = 16.4


def draw_candles(ax, bars, width=0.68, lw=1.45):
    for i, (o, h, l, c) in enumerate(bars):
        color = UP if c >= o else DOWN
        alpha = 0.45 if i < N_PM else 1.0
        ax.vlines(i, l, h, color=color, linewidth=lw, alpha=alpha, zorder=3)
        body_lo, body_hi = min(o, c), max(o, c)
        if abs(c - o) < 0.04:
            ax.hlines(c, i - width / 2, i + width / 2, color=color, linewidth=lw + 0.15, alpha=alpha, zorder=4)
        else:
            ax.add_patch(
                Rectangle(
                    (i - width / 2, body_lo),
                    width,
                    body_hi - body_lo,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=0.5,
                    alpha=alpha,
                    zorder=4,
                    antialiased=True,
                )
            )


def add_orb_pm(ax, show_pmh=True, show_pml=False, show_mid=False, y_open=None):
    # Opening-range box: bars 3,4,5
    ax.add_patch(
        Rectangle((2.5, ORB_L), 3.0, ORB_H - ORB_L, facecolor=ORB_FILL, edgecolor="none", alpha=0.18, zorder=1)
    )
    ax.axvspan(XMIN, 2.5, facecolor="#0a0c11", alpha=0.55, zorder=0)
    ax.axvline(2.5, color=OPEN_COLOR, linewidth=0.85, linestyle=(0, (2.2, 3.0)), zorder=2, alpha=0.9)
    ax.hlines(ORB_H, XMIN, XMAX, colors=ORB_COLOR, linestyles="-", linewidth=1.2, zorder=2, alpha=0.95)
    ax.hlines(ORB_L, XMIN, XMAX, colors=ORB_COLOR, linestyles="-", linewidth=1.2, zorder=2, alpha=0.95)
    if show_pmh:
        ax.hlines(PMH, XMIN, XMAX, colors=PM_COLOR, linestyles=(0, (4.5, 3.0)), linewidth=1.15, zorder=2, alpha=0.95)
    if show_pml:
        ax.hlines(PML, XMIN, XMAX, colors=PM_COLOR, linestyles=(0, (4.5, 3.0)), linewidth=1.15, zorder=2, alpha=0.95)
    if show_mid:
        ax.hlines(MID, XMIN, XMAX, colors=TEXT_DIM, linestyles=(0, (2, 3)), linewidth=0.7, zorder=2, alpha=0.6)
    # tiny zone tags, tucked in empty corners (set by caller via y_open)
    if y_open is not None:
        ax.text(1.0, y_open, "Premarket", ha="center", va="center", color=TEXT_DIM, fontproperties=fp_med, fontsize=6.5, zorder=5)
        ax.text(2.65, y_open, "Open", ha="left", va="center", color=TEXT_DIM, fontproperties=fp_med, fontsize=6.5, zorder=5)


def style_ax(ax, ylim, yticks, last_i):
    ax.set_facecolor(AX_BG)
    ax.set_xlim(XMIN, XMAX)
    ax.set_ylim(*ylim)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.xaxis.grid(False)
    ax.tick_params(axis="both", length=0, pad=3, colors=TEXT_MUTED)
    # time ticks at open and every 30 min of the window: 9:15, 9:30, 10:00, 10:30
    ticks = [0, 3, 9, 15]
    ticks = [t for t in ticks if t <= last_i + 0.5]
    ax.set_xticks(ticks)
    ax.set_xticklabels([tlabel(i) for i in ticks], fontproperties=fp, fontsize=7.2, color=TEXT_MUTED)
    ax.set_yticks(yticks)
    ax.set_yticklabels(
        [f"{y:g}" for y in yticks],
        fontproperties=fp_mono,
        fontsize=7.2,
        color=TEXT_MUTED,
    )
    for s in ax.spines.values():
        s.set_color(SPINE)
        s.set_linewidth(0.8)
    ax.spines["top"].set_visible(False)


def fmt_px(p):
    return f"{p:.1f}" if abs(p - round(p)) > 1e-9 else f"{p:.0f}"


def draw_position(ax, entry_x, entry, stop, target, side="long", rr_text="1.5R"):
    """TradingView-style long/short position tool from the entry bar to the right."""
    x0 = entry_x - 0.12
    x1 = XMAX - 0.15
    w = x1 - x0
    risk_lo, risk_hi = min(entry, stop), max(entry, stop)
    rew_lo, rew_hi = min(entry, target), max(entry, target)
    ax.add_patch(Rectangle((x0, risk_lo), w, risk_hi - risk_lo, facecolor=ZONE_RED, edgecolor="none", alpha=0.22, zorder=1.4))
    ax.add_patch(Rectangle((x0, rew_lo), w, rew_hi - rew_lo, facecolor=ZONE_GREEN, edgecolor="none", alpha=0.22, zorder=1.4))
    ax.hlines(stop, x0, x1, colors=STOP_COLOR, linestyles=(0, (5.5, 2.8)), linewidth=1.7, zorder=5)
    ax.hlines(target, x0, x1, colors=TARGET_COLOR, linestyles="-", linewidth=1.8, zorder=5)
    ax.hlines(entry, x0, x1, colors=WHITE, linestyles="-", linewidth=1.05, zorder=5, alpha=0.85)

    # Right-edge labels, stacked in the margin, with a dark stroke
    def rlab(y, text, color, va, dy):
        ax.text(
            x1 - 0.05,
            y + dy,
            text,
            ha="right",
            va=va,
            color=color,
            fontproperties=fp_semb,
            fontsize=8.0,
            zorder=8,
            path_effects=stroke(4.0),
        )

    if side == "long":
        rlab(target, f"TARGET  {fmt_px(target)}", TARGET_COLOR, "bottom", 0.10)
        rlab(stop, f"STOP  {fmt_px(stop)}", STOP_COLOR, "top", -0.10)
    else:
        rlab(stop, f"STOP  {fmt_px(stop)}", STOP_COLOR, "bottom", 0.10)
        rlab(target, f"TARGET  {fmt_px(target)}", TARGET_COLOR, "top", -0.10)

    # R:R sits in the reward zone, left of the right-edge target/stop labels
    mid_rew = (entry + target) / 2
    ax.text(
        x1 - 3.4,
        mid_rew,
        rr_text,
        ha="center",
        va="center",
        color=TARGET_COLOR,
        fontproperties=fp_bold,
        fontsize=9.0,
        zorder=8,
        path_effects=stroke(4.2),
    )


def draw_entry_marker(ax, x, price, side="long", label=None):
    """Big triangle at the entry close, plus a price callout."""
    # Highlight the entry bar
    ax.axvspan(x - 0.48, x + 0.48, facecolor=ENTRY_COLOR, alpha=0.10, zorder=1.2)
    marker = "^" if side == "long" else "v"
    # Place the triangle just to the right of the candle so the body stays visible
    ax.scatter(
        [x + 0.62],
        [price],
        marker=marker,
        s=220,
        color=ENTRY_COLOR,
        edgecolors=WHITE,
        linewidths=0.9,
        zorder=11,
        clip_on=False,
    )
    text = label or f"ENTRY  {fmt_px(price)}"
    # For longs, put the label above and right; for shorts, below and right —
    # callers can override later if needed. Default: just above the triangle for long,
    # just below for short, with a stroke.
    dy = 0.48 if side == "long" else -0.32
    va = "bottom" if side == "long" else "top"
    ax.text(
        x + 0.85,
        price + dy,
        text,
        ha="left",
        va=va,
        color=ENTRY_COLOR,
        fontproperties=fp_bold,
        fontsize=8.4,
        zorder=12,
        path_effects=stroke(4.2),
    )


def draw_x(ax, x, y, label=None, dy=0.35):
    ax.scatter(
        [x],
        [y],
        marker="x",
        s=280,
        color=GRAY,
        linewidths=3.0,
        zorder=12,
        clip_on=False,
    )
    if label:
        ax.text(
            x,
            y + dy,
            label,
            ha="center",
            va="bottom",
            color=GRAY,
            fontproperties=fp_med,
            fontsize=6.8,
            zorder=12,
            path_effects=stroke(),
        )


def left_level(ax, y, text, color, va="bottom", dy=0.10, x=None):
    ax.text(
        XMIN + 0.12 if x is None else x,
        y + dy,
        text,
        ha="left",
        va=va,
        color=color,
        fontproperties=fp_med,
        fontsize=6.8,
        zorder=6,
        path_effects=stroke(),
    )


def main():
    # 12 in * 200 dpi = 2400 px wide. Tall enough for 2x2 + trade cards.
    fig = plt.figure(figsize=(12.00, 14.30), dpi=200, facecolor=FIG_BG)

    fig.text(
        0.50,
        0.981,
        "Opening Range Breakout (ORB)  Trade Playbook",
        ha="center",
        va="top",
        color=WHITE,
        fontproperties=fp_bold,
        fontsize=20.5,
    )
    fig.text(
        0.50,
        0.960,
        "Entry, stop, and exit for each rule.    ·    Illustrative example, not real data.    Education only, not financial advice.",
        ha="center",
        va="top",
        color=TEXT_MUTED,
        fontproperties=fp,
        fontsize=8.8,
    )
    # Shared levels key
    fig.text(
        0.50,
        0.940,
        "Example levels    ·    ORB high  102      ORB low  100      Range midpoint  101      PM high  104      PM low  98      50% ext  107",
        ha="center",
        va="top",
        color=TEXT,
        fontproperties=fp_mono_med,
        fontsize=7.3,
    )

    # Room at the top for titles, generous hspace for a trade card under each chart
    gs = fig.add_gridspec(
        2,
        2,
        left=0.046,
        right=0.978,
        top=0.872,
        bottom=0.168,
        wspace=0.145,
        hspace=0.54,
    )

    # ================================================================== #
    # Panel 1 — breakout long
    # ================================================================== #
    ax1 = fig.add_subplot(gs[0, 0])
    style_ax(ax1, (99.15, 105.35), [100, 101, 102, 104], last_i=12)
    add_orb_pm(ax1, show_pmh=True, show_mid=True, y_open=99.40)
    left_level(ax1, ORB_H, "ORB high  102", ORB_COLOR, "bottom", 0.10)
    left_level(ax1, ORB_L, "ORB low  100", ORB_COLOR, "top", -0.10)
    left_level(ax1, PMH, "PM high  104", PM_COLOR, "bottom", 0.10)
    draw_candles(ax1, P1)
    draw_position(ax1, P1_ENTRY_X, P1_ENTRY, P1_STOP, P1_TGT, side="long", rr_text="1.5R")
    draw_entry_marker(ax1, P1_ENTRY_X, P1_ENTRY, side="long")
    # "range midpoint" note tucked next to the stop, on the left of the position box
    # so it doesn't fight the right-edge STOP label. Place just left of entry bar, in the red zone.
    ax1.text(
        P1_ENTRY_X - 0.7,
        MID - 0.18,
        "midpoint",
        ha="right",
        va="top",
        color=STOP_COLOR,
        fontproperties=fp,
        fontsize=6.4,
        zorder=7,
        path_effects=stroke(),
    )

    # ================================================================== #
    # Panel 2 — failed breakout short
    # ================================================================== #
    ax2 = fig.add_subplot(gs[0, 1])
    style_ax(ax2, (99.15, 105.35), [100, 101, 102, 103, 104], last_i=12)
    add_orb_pm(ax2, show_pmh=True, y_open=99.40)
    left_level(ax2, ORB_H, "ORB high  102", ORB_COLOR, "bottom", 0.10)
    left_level(ax2, ORB_L, "ORB low  100", ORB_COLOR, "top", -0.10)
    draw_candles(ax2, P2)
    draw_position(ax2, P2_ENTRY_X, P2_ENTRY, P2_STOP, P2_TGT, side="short", rr_text="1.5R")
    draw_entry_marker(ax2, P2_ENTRY_X, P2_ENTRY, side="short")
    # Mark the failed poke wick
    ax2.annotate(
        "Failed poke\nwick  102.8",
        xy=(P2_POKE_X, P2_WICK),
        xytext=(P2_POKE_X - 1.5, 104.15),
        ha="center",
        va="bottom",
        color=TEXT_MUTED,
        fontproperties=fp_med,
        fontsize=6.8,
        linespacing=1.2,
        zorder=8,
        arrowprops=dict(arrowstyle="-|>", color=TEXT_MUTED, lw=0.9, mutation_scale=7, shrinkB=3),
        path_effects=stroke(),
    )

    # ================================================================== #
    # Panel 3 — ORB + PM break, target 50% ext from premarket
    # ================================================================== #
    ax3 = fig.add_subplot(gs[1, 0])
    style_ax(ax3, (99.35, 108.85), [100, 102, 103.4, 104, 107], last_i=15)
    add_orb_pm(ax3, show_pmh=True, show_pml=False, y_open=99.62)
    left_level(ax3, ORB_H, "ORB high  102", ORB_COLOR, "bottom", 0.10)
    left_level(ax3, ORB_L, "ORB low  100", ORB_COLOR, "top", -0.10)
    left_level(ax3, PMH, "PM high  104", PM_COLOR, "top", -0.12)  # below the line so it misses the stop at 103.4
    draw_candles(ax3, P3)
    draw_position(ax3, P3_ENTRY_X, P3_ENTRY, P3_STOP, P3_TGT, side="long", rr_text="3.5R")
    draw_entry_marker(ax3, P3_ENTRY_X, P3_ENTRY, side="long")
    # Formula, in the empty upper-left above the early climb? Early climb fills 102-104 on the left.
    # Put it in the empty pocket ABOVE the target line, left side — price only reaches 107 on the right.
    ax3.text(
        3.6,
        108.15,
        "50% ext  =  PM high  +  0.5 × (PM high − PM low)\n"
        "          =  104  +  0.5 × 6   =   107",
        ha="left",
        va="center",
        color=GOLD,
        fontproperties=fp_mono_med,
        fontsize=6.5,
        linespacing=1.35,
        zorder=8,
        path_effects=stroke(3.8),
    )

    # ================================================================== #
    # Panel 4 — chop, no trade
    # ================================================================== #
    ax4 = fig.add_subplot(gs[1, 1])
    style_ax(ax4, (99.15, 105.65), [100, 101, 102, 104], last_i=15)
    add_orb_pm(ax4, show_pmh=True, y_open=99.40)
    left_level(ax4, ORB_H, "ORB high  102", ORB_COLOR, "bottom", 0.10)
    left_level(ax4, ORB_L, "ORB low  100", ORB_COLOR, "top", -0.10)
    draw_candles(ax4, P4)
    # Would-be entries crossed out
    draw_x(ax4, P4_FAKE_XS[0], 102.40, "Would-be entry", dy=0.42)
    draw_x(ax4, P4_FAKE_XS[1], 102.45, "Would-be entry", dy=0.42)
    # Reclaim labels, sitting in the empty pocket above the range after each red reclaim candle
    ax4.annotate(
        "1st reclaim",
        xy=(P4_RECLAIM_XS[0], 101.50),
        xytext=(P4_RECLAIM_XS[0] + 0.15, 103.55),
        ha="center",
        va="bottom",
        color=BADGE_RED,
        fontproperties=fp_med,
        fontsize=6.7,
        zorder=8,
        arrowprops=dict(arrowstyle="-|>", color=BADGE_RED, lw=0.85, mutation_scale=7, shrinkB=2),
        path_effects=stroke(),
    )
    ax4.annotate(
        "2nd reclaim",
        xy=(P4_RECLAIM_XS[1], 101.50),
        xytext=(P4_RECLAIM_XS[1] + 0.15, 103.55),
        ha="center",
        va="bottom",
        color=BADGE_RED,
        fontproperties=fp_med,
        fontsize=6.7,
        zorder=8,
        arrowprops=dict(arrowstyle="-|>", color=BADGE_RED, lw=0.85, mutation_scale=7, shrinkB=2),
        path_effects=stroke(),
    )
    # After the 2nd reclaim, a light wash and a sit-out badge in the clear upper-right
    ax4.axvspan(P4_RECLAIM_XS[1] + 0.5, XMAX, facecolor=BADGE_RED, alpha=0.06, zorder=1)
    ax4.text(
        13.15,
        104.95,
        "NO TRADE\n2nd reclaim  =  chop\nSit out till PM session\n(after  ~2 PM  ET)",
        ha="center",
        va="center",
        color=WHITE,
        fontproperties=fp_bold,
        fontsize=8.0,
        linespacing=1.35,
        zorder=10,
        bbox=dict(
            boxstyle="round,pad=0.50,rounding_size=0.4",
            facecolor="#8b1e2d",
            edgecolor="#f3a0a8",
            linewidth=1.15,
        ),
    )

    # ----- Headers + 3-line trade cards (figure coords) -----
    fig.canvas.draw()

    cards = [
        (
            ax1,
            "Rule 1  —  Breakout long",
            "Close above ORB high  →  target the premarket high.",
            [
                ("Enter", "102.2", "5-min close above ORB high"),
                ("Stop", "101", "Midpoint of the opening range"),
                ("Exit", "104", "Premarket high"),
            ],
            "1.5R",
            False,
        ),
        (
            ax2,
            "Rule 2  —  Failed breakout short",
            "Poke fails and closes back inside  →  retrace the opening range.",
            [
                ("Enter", "101.8", "Close back below ORB high"),
                ("Stop", "103", "Above the failed-break wick (102.8)"),
                ("Exit", "100", "ORB low  (retrace the range)"),
            ],
            "1.5R",
            False,
        ),
        (
            ax3,
            "Rule 3  —  ORB + premarket break long",
            "Close above premarket high  →  target the 50% extension (from premarket).",
            [
                ("Enter", "104.2", "5-min close above PM high"),
                ("Stop", "103.4", "Just under premarket high"),
                ("Exit", "107", "50% ext  =  104 + 0.5 × 6"),
            ],
            "3.5R",
            False,
        ),
        (
            ax4,
            "Note  —  Chop day, sit out",
            "ORB high reclaimed more than once  →  no trade.",
            [
                ("Enter", "—", "No trade"),
                ("Stop", "—", "No trade"),
                ("Exit", "—", "Sit out till after  ~2 PM  ET"),
            ],
            None,
            True,
        ),
    ]

    for ax, title, rule, rows, rr, is_notrade in cards:
        bbox = ax.get_position()
        x0, x1, y0, y1 = bbox.x0, bbox.x1, bbox.y0, bbox.y1
        # Header bar above the chart
        fig.patches.append(
            FancyBboxPatch(
                (x0, y1 + 0.012),
                x1 - x0,
                0.036,
                boxstyle="round,pad=0.001,rounding_size=0.004",
                facecolor="#181c27",
                edgecolor="#2a2e39",
                linewidth=0.6,
                transform=fig.transFigure,
                zorder=2,
            )
        )
        fig.text(
            x0 + 0.008,
            y1 + 0.043,
            title,
            ha="left",
            va="top",
            color=WHITE,
            fontproperties=fp_semb,
            fontsize=9.3,
            zorder=4,
        )
        fig.text(
            x0 + 0.008,
            y1 + 0.0255,
            rule,
            ha="left",
            va="top",
            color=TEXT,
            fontproperties=fp,
            fontsize=7.15,
            zorder=4,
        )

        # Trade card under the chart
        card_h = 0.058
        card_y = y0 - 0.022 - card_h
        edge = "#5a2028" if is_notrade else "#2a2e39"
        face = "#1a1216" if is_notrade else "#181c27"
        fig.patches.append(
            FancyBboxPatch(
                (x0, card_y),
                x1 - x0,
                card_h,
                boxstyle="round,pad=0.001,rounding_size=0.004",
                facecolor=face,
                edgecolor=edge,
                linewidth=0.7,
                transform=fig.transFigure,
                zorder=2,
            )
        )
        # Three rows, evenly spaced in the card
        row_ys = [card_y + card_h * 0.78, card_y + card_h * 0.50, card_y + card_h * 0.22]
        tag_color = {"Enter": ENTRY_COLOR, "Stop": STOP_COLOR, "Exit": TARGET_COLOR}
        for (tag, px, note), ry in zip(rows, row_ys):
            fig.text(
                x0 + 0.010,
                ry,
                tag.upper(),
                ha="left",
                va="center",
                color=tag_color[tag],
                fontproperties=fp_semb,
                fontsize=7.0,
                zorder=4,
            )
            fig.text(
                x0 + 0.048,
                ry,
                px,
                ha="left",
                va="center",
                color=WHITE,
                fontproperties=fp_mono_semb,
                fontsize=8.0,
                zorder=4,
            )
            fig.text(
                x0 + 0.095,
                ry,
                note,
                ha="left",
                va="center",
                color=TEXT_MUTED if not is_notrade else TEXT,
                fontproperties=fp,
                fontsize=7.0,
                zorder=4,
            )
        if rr:
            fig.text(
                x1 - 0.010,
                card_y + card_h / 2,
                rr,
                ha="right",
                va="center",
                color=TARGET_COLOR,
                fontproperties=fp_bold,
                fontsize=11.0,
                zorder=4,
            )

    # ----- Footer legend -----
    # Custom entry marker for the legend
    entry_handle = Line2D(
        [0], [0], marker="^", color=ENTRY_COLOR, markeredgecolor=WHITE,
        markeredgewidth=0.6, markersize=9, linestyle="None", label="Entry",
    )
    stop_handle = Line2D([0], [0], color=STOP_COLOR, lw=1.8, ls=(0, (4, 2)), label="Stop loss")
    tgt_handle = Line2D([0], [0], color=TARGET_COLOR, lw=2.0, label="Target / exit")
    risk_handle = mpatches.Patch(facecolor=ZONE_RED, alpha=0.40, edgecolor="none", label="Risk zone")
    rew_handle = mpatches.Patch(facecolor=ZONE_GREEN, alpha=0.40, edgecolor="none", label="Reward zone")
    orb_handle = mpatches.Patch(facecolor=ORB_FILL, alpha=0.35, edgecolor=ORB_COLOR, label="Opening range (first 15 min)")
    x_handle = Line2D(
        [0], [0], marker="x", color=GRAY, markersize=8, markeredgewidth=2.0,
        linestyle="None", label="Would-be entry (no trade)",
    )
    fig.legend(
        handles=[entry_handle, stop_handle, tgt_handle, risk_handle, rew_handle, orb_handle, x_handle],
        loc="lower center",
        bbox_to_anchor=(0.50, 0.040),
        ncol=7,
        frameon=False,
        handlelength=1.6,
        handletextpad=0.40,
        columnspacing=1.10,
        labelcolor=TEXT_MUTED,
        prop=FontProperties(fname="fonts/Inter-Regular.ttf", size=7.2),
    )
    fig.text(
        0.50,
        0.026,
        "Short version works the same in reverse at the lows.",
        ha="center",
        va="bottom",
        color=TEXT,
        fontproperties=fp_med,
        fontsize=8.0,
    )
    fig.text(
        0.50,
        0.010,
        "Illustrative example, not real data.    Education only, not financial advice.    Opening range = first 15 minutes after the 9:30 open  (three 5-min candles).",
        ha="center",
        va="bottom",
        color=TEXT_DIM,
        fontproperties=fp,
        fontsize=6.5,
    )

    out = "orb-trade-playbook.png"
    fig.savefig(out, dpi=200, facecolor=FIG_BG, edgecolor="none")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
