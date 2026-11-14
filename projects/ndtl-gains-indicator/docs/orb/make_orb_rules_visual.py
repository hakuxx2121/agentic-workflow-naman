#!/usr/bin/env python3
"""Educational Opening Range Breakout (ORB) rules visual.
Synthetic 5-minute candles. Illustrative example, not real data.
"""

from __future__ import annotations

from pathlib import Path as _Path

def _ensure_inter_fonts():
    """Instantiate static Inter weights from the variable font if needed."""
    out = _Path("fonts")
    needed = ["Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf"]
    if all((out / n).exists() for n in needed):
        return
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    src = "/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf"
    out.mkdir(parents=True, exist_ok=True)
    weights = [(400, "Inter-Regular.ttf"), (500, "Inter-Medium.ttf"), (600, "Inter-SemiBold.ttf"), (700, "Inter-Bold.ttf")]
    for w, name in weights:
        inst = instantiateVariableFont(TTFont(src), {"wght": w, "opsz": 18})
        inst.save(out / name)

_ensure_inter_fonts()

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.lines import Line2D
import matplotlib.patheffects as pe
from matplotlib.font_manager import FontProperties, fontManager

# ---------------------------------------------------------------------------
# Fonts (static Inter instances + IBM Plex Mono)
# ---------------------------------------------------------------------------
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
fp_mono = FontProperties(fname="/usr/share/fonts/truetype/sand-box/google/IBM Plex Mono/IBMPlexMono-Regular.ttf")
fp_mono_med = FontProperties(fname="/usr/share/fonts/truetype/sand-box/google/IBM Plex Mono/IBMPlexMono-Medium.ttf")

# ---------------------------------------------------------------------------
# Theme (TradingView-like dark)
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
EXT_COLOR = "#f5c14a"
OPEN_COLOR = "#6b7280"
ACCENT = "#7dd3fc"
BADGE_RED = "#e35d6a"
TARGET_GREEN = "#34d399"

# Levels (round numbers, easy to teach)
PML = 98.0
ORB_L = 100.0
ORB_H = 102.0
PMH = 104.0
EXT = PMH + 0.5 * (PMH - PML)  # 107.0

N_PM = 6  # bars 0-5 = premarket (9:00-9:25)
# bars 6-8 = opening range (9:30, 9:35, 9:40)
N = 33    # 9:00 through 11:40


def tlabel(i: int) -> str:
    minutes = 9 * 60 + i * 5
    h, m = divmod(minutes, 60)
    return f"{h}:{m:02d}"


def candle(o, h, l, c):
    h = max(h, o, c)
    l = min(l, o, c)
    return (round(o, 2), round(h, 2), round(l, 2), round(c, 2))


PM = [
    (100.20, 100.80, 99.85, 100.50),
    (100.50, 102.45, 100.40, 102.15),
    (102.15, 104.00, 101.90, 103.20),  # tags PMH
    (103.20, 103.50, 100.55, 100.85),
    (100.85, 101.15, 98.00, 98.55),    # tags PML
    (98.55, 100.55, 98.35, 100.25),
]

ORB = [
    (100.25, 101.30, 100.00, 101.10),  # tags ORB low
    (101.10, 101.85, 100.65, 101.60),
    (101.60, 102.00, 101.15, 101.50),  # tags ORB high
]

# Panel 1: break ORB high, run to PM high
P1_REST = [
    (101.50, 101.80, 101.20, 101.40),
    (101.40, 101.70, 101.10, 101.25),
    (101.25, 102.90, 101.20, 102.70),  # BREAK ORB high  (idx 11)
    (102.70, 103.20, 102.45, 103.00),
    (103.00, 103.45, 102.75, 103.25),
    (103.25, 103.55, 103.00, 103.20),
    (103.20, 103.75, 103.05, 103.55),
    (103.55, 103.95, 103.35, 103.80),
    (103.80, 104.08, 103.65, 104.00),  # TARGET PM high (idx 17)
    (104.00, 104.12, 103.72, 103.85),
    (103.85, 104.05, 103.68, 103.92),
    (103.92, 104.08, 103.70, 103.88),
    (103.88, 104.00, 103.68, 103.82),
    (103.82, 103.98, 103.62, 103.78),
    (103.78, 103.95, 103.58, 103.80),
    (103.80, 103.96, 103.62, 103.74),
    (103.74, 103.90, 103.55, 103.72),
    (103.72, 103.88, 103.52, 103.68),
    (103.68, 103.85, 103.50, 103.70),
    (103.70, 103.86, 103.54, 103.66),
    (103.66, 103.82, 103.50, 103.64),
    (103.64, 103.80, 103.48, 103.62),
    (103.62, 103.78, 103.46, 103.60),
    (103.60, 103.76, 103.44, 103.58),
]

# Panel 2: false break of ORB high, retrace to ORB low
P2_REST = [
    (101.50, 101.90, 101.25, 101.70),
    (101.70, 102.20, 101.55, 102.08),
    (102.08, 102.95, 101.95, 102.72),  # false break (idx 11)
    (102.72, 103.00, 102.35, 102.48),  # stall
    (102.48, 102.62, 101.55, 101.68),  # FAIL / reclaim (idx 13)
    (101.68, 101.90, 101.20, 101.32),
    (101.32, 101.50, 100.80, 100.92),
    (100.92, 101.10, 100.48, 100.58),
    (100.58, 100.75, 100.15, 100.28),
    (100.28, 100.42, 99.92, 100.02),   # retrace to ORB low (idx 18)
    (100.02, 100.35, 99.85, 100.18),
    (100.18, 100.42, 100.00, 100.22),
    (100.22, 100.48, 100.05, 100.30),
    (100.30, 100.55, 100.12, 100.28),
    (100.28, 100.50, 100.08, 100.24),
    (100.24, 100.46, 100.05, 100.18),
    (100.18, 100.40, 100.00, 100.16),
    (100.16, 100.38, 99.98, 100.14),
    (100.14, 100.36, 99.96, 100.12),
    (100.12, 100.34, 99.95, 100.10),
    (100.10, 100.32, 99.94, 100.08),
    (100.08, 100.30, 99.94, 100.10),
    (100.10, 100.28, 99.96, 100.08),
    (100.08, 100.26, 99.95, 100.06),
]

# Panel 3: breaks ORB high AND PM high, runs to 50% extension
P3_REST = [
    (101.50, 101.75, 101.20, 101.40),
    (101.40, 102.95, 101.35, 102.75),  # BREAK ORB high (idx 10)
    (102.75, 103.35, 102.55, 103.18),
    (103.18, 103.85, 103.00, 103.70),
    (103.70, 104.55, 103.55, 104.40),  # BREAK PM high (idx 13)
    (104.40, 105.00, 104.20, 104.82),
    (104.82, 105.40, 104.65, 105.25),
    (105.25, 105.80, 105.05, 105.62),
    (105.62, 106.15, 105.45, 105.98),
    (105.98, 106.50, 105.80, 106.35),
    (106.35, 106.85, 106.15, 106.70),
    (106.70, 107.18, 106.55, 107.00),  # 50% extension (idx 20)
    (107.00, 107.22, 106.72, 106.88),
    (106.88, 107.10, 106.65, 106.82),
    (106.82, 107.05, 106.60, 106.78),
    (106.78, 107.00, 106.55, 106.72),
    (106.72, 106.95, 106.50, 106.68),
    (106.68, 106.90, 106.48, 106.64),
    (106.64, 106.86, 106.45, 106.62),
    (106.62, 106.84, 106.44, 106.60),
    (106.60, 106.80, 106.42, 106.58),
    (106.58, 106.78, 106.40, 106.55),
    (106.55, 106.75, 106.38, 106.52),
    (106.52, 106.72, 106.36, 106.50),
]

# Panel 4: ORB high reclaimed twice (chop) — sit out
P4_REST = [
    (101.50, 101.85, 101.20, 101.45),
    (101.45, 102.75, 101.40, 102.58),  # break 1 (idx 10)
    (102.58, 102.95, 102.20, 102.42),
    (102.42, 102.60, 101.45, 101.58),  # RECLAIM 1 (idx 12)
    (101.58, 101.88, 101.20, 101.42),
    (101.42, 102.85, 101.35, 102.68),  # break 2 (idx 14)
    (102.68, 103.05, 102.35, 102.80),
    (102.80, 102.95, 101.38, 101.50),  # RECLAIM 2 (idx 16)
    (101.50, 101.85, 101.05, 101.28),
    (101.28, 102.45, 101.10, 102.22),
    (102.22, 102.55, 101.55, 101.68),
    (101.68, 102.05, 101.15, 101.38),
    (101.38, 101.80, 100.95, 101.15),
    (101.15, 101.55, 100.80, 101.05),
    (101.05, 101.50, 100.70, 100.92),
    (100.92, 101.35, 100.65, 101.10),
    (101.10, 101.55, 100.85, 101.22),
    (101.22, 101.70, 100.95, 101.18),
    (101.18, 101.60, 100.88, 101.08),
    (101.08, 101.48, 100.80, 101.02),
    (101.02, 101.42, 100.75, 100.98),
    (100.98, 101.38, 100.72, 100.95),
    (100.95, 101.35, 100.70, 100.92),
    (100.92, 101.32, 100.68, 100.90),
]


def series(rest):
    bars = [candle(*b) for b in (PM + ORB + rest)]
    assert len(bars) == N, len(bars)
    return bars


SERIES = [series(P1_REST), series(P2_REST), series(P3_REST), series(P4_REST)]

XMAX = 35.8
XMIN = -0.7


def stroke(w=3.4, fg=AX_BG):
    return [pe.withStroke(linewidth=w, foreground=fg)]


def draw_candles(ax, bars, pm_end=N_PM):
    width = 0.66
    for i, (o, h, l, c) in enumerate(bars):
        color = UP if c >= o else DOWN
        alpha = 0.48 if i < pm_end else 1.0
        ax.vlines(i, l, h, color=color, linewidth=1.25, alpha=alpha, zorder=3)
        body_lo, body_hi = min(o, c), max(o, c)
        if abs(c - o) < 0.03:
            ax.hlines(c, i - width / 2, i + width / 2, color=color, linewidth=1.35, alpha=alpha, zorder=4)
        else:
            ax.add_patch(
                Rectangle(
                    (i - width / 2, body_lo),
                    width,
                    body_hi - body_lo,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=0.45,
                    alpha=alpha,
                    zorder=4,
                    antialiased=True,
                )
            )


def add_levels(ax, show_ext=False):
    # Opening range box (first 15 min of regular session): bars 6, 7, 8
    ax.add_patch(
        Rectangle(
            (5.5, ORB_L),
            3.0,
            ORB_H - ORB_L,
            facecolor=ORB_FILL,
            edgecolor="none",
            alpha=0.18,
            zorder=1,
        )
    )
    # Premarket shade
    ax.axvspan(XMIN, 5.5, facecolor="#0a0c11", alpha=0.55, zorder=0)
    # Open line
    ax.axvline(5.5, color=OPEN_COLOR, linewidth=0.85, linestyle=(0, (2.2, 3.0)), zorder=2, alpha=0.9)

    def hline(y, color, ls, lw=1.05):
        ax.hlines(y, XMIN, XMAX, colors=color, linestyles=ls, linewidth=lw, zorder=2, alpha=0.95)

    hline(PMH, PM_COLOR, (0, (4.5, 3.0)), 1.15)
    hline(PML, PM_COLOR, (0, (4.5, 3.0)), 1.15)
    hline(ORB_H, ORB_COLOR, "-", 1.3)
    hline(ORB_L, ORB_COLOR, "-", 1.3)
    if show_ext:
        hline(EXT, EXT_COLOR, (0, (5.5, 2.4)), 1.3)

    # Right-edge labels, offset so they sit just off the line and don't collide
    label_x = XMAX - 0.12
    specs = [
        (PMH, "PM High", PM_COLOR, "bottom", 0.22),
        (ORB_H, "ORB High", ORB_COLOR, "bottom", 0.22),
        (ORB_L, "ORB Low", ORB_COLOR, "top", -0.22),
        (PML, "PM Low", PM_COLOR, "top", -0.22),
    ]
    if show_ext:
        specs.insert(0, (EXT, "50% Ext.", EXT_COLOR, "bottom", 0.22))

    for y, text, color, va, dy in specs:
        ax.text(
            label_x,
            y + dy,
            text,
            ha="right",
            va=va,
            color=color,
            fontproperties=fp_med,
            fontsize=7.3,
            zorder=6,
            path_effects=stroke(),
        )

    # Premarket / Open labels sit under the PM low line, above the x-axis
    ax.text(
        2.35,
        97.15,
        "Premarket",
        ha="center",
        va="center",
        color=TEXT_DIM,
        fontproperties=fp_med,
        fontsize=6.7,
        zorder=5,
    )
    ax.text(
        5.75,
        97.15,
        "Open",
        ha="left",
        va="center",
        color=TEXT_DIM,
        fontproperties=fp_med,
        fontsize=6.7,
        zorder=5,
    )


def style_ax(ax, ylim):
    ax.set_facecolor(AX_BG)
    ax.set_xlim(XMIN, XMAX)
    ax.set_ylim(*ylim)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6, alpha=1)
    ax.xaxis.grid(False)
    ax.tick_params(axis="both", length=0, pad=3, colors=TEXT_MUTED)
    ticks = [0, 6, 12, 18, 24, 30]
    ax.set_xticks(ticks)
    ax.set_xticklabels([tlabel(i) for i in ticks], fontproperties=fp, fontsize=7.1, color=TEXT_MUTED)
    yticks = [PML, ORB_L, ORB_H, PMH]
    if ylim[1] > EXT - 0.3:
        yticks = yticks + [EXT]
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{y:.0f}" for y in yticks], fontproperties=fp_mono, fontsize=7.0, color=TEXT_MUTED)
    for s in ax.spines.values():
        s.set_color(SPINE)
        s.set_linewidth(0.8)
    ax.spines["top"].set_visible(False)


def pill(ax, x, y, text, facecolor, edgecolor, fontsize=7.5, text_color=WHITE):
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        color=text_color,
        fontproperties=fp_semb,
        fontsize=fontsize,
        zorder=8,
        bbox=dict(
            boxstyle="round,pad=0.35,rounding_size=0.35",
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=0.9,
        ),
    )


def callout(ax, xy, text, xytext, color=WHITE, fontsize=7.5, ha="left", rad=0.0):
    ax.annotate(
        text,
        xy=xy,
        xytext=xytext,
        textcoords="data",
        ha=ha,
        va="center",
        color=color,
        fontproperties=fp_med,
        fontsize=fontsize,
        zorder=7,
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=1.05,
            mutation_scale=9,
            shrinkA=0,
            shrinkB=3,
            connectionstyle=f"arc3,rad={rad}",
        ),
        path_effects=stroke(),
    )


def main():
    # 12 in * 200 dpi = 2400 px wide
    fig = plt.figure(figsize=(12.00, 13.40), dpi=200, facecolor=FIG_BG)

    fig.text(
        0.50,
        0.978,
        "Opening Range Breakout (ORB) Rules",
        ha="center",
        va="top",
        color=WHITE,
        fontproperties=fp_bold,
        fontsize=21.0,
    )
    fig.text(
        0.50,
        0.952,
        "A simple rule set for the first 15 minutes of the regular session.    ·    Illustrative example, not real data.",
        ha="center",
        va="top",
        color=TEXT_MUTED,
        fontproperties=fp,
        fontsize=9.2,
    )

    # Leave generous room under the title and between the two rows
    # so panel headers / captions never collide with the title or each other.
    gs = fig.add_gridspec(
        2,
        2,
        left=0.048,
        right=0.978,
        top=0.868,
        bottom=0.078,
        wspace=0.14,
        hspace=0.40,
    )

    panels = [
        dict(
            title="Rule 1  —  The breakout",
            rule="If the ORB high or low breaks, price will go to the premarket high or low.",
            note="Shown: a break of ORB high, targeting PM high.  The same idea applies in reverse to the lows.",
            show_ext=False,
            ylim=(96.7, 106.45),
        ),
        dict(
            title="Rule 2  —  Failed break, or a reclaim",
            rule="If the ORB high or low fails or is reclaimed, price will retrace the opening range.",
            note="A failed break above ORB high often travels all the way back to ORB low.",
            show_ext=False,
            ylim=(96.7, 106.45),
        ),
        dict(
            title="Rule 3  —  Both levels give way",
            rule="If ORB and premarket levels are broken, target the 50% extension.",
            note="50% ext.  =  Premarket high  +  0.5  ×  (Premarket high  −  Premarket low)",
            show_ext=True,
            ylim=(96.7, 109.35),
        ),
        dict(
            title="Note  —  Chop day",
            rule="If an ORB is reclaimed more than once  =  chop day.  Sit out till the PM session.",
            note="Two or more reclaims of ORB high is the sit-out signal — wait for the afternoon.",
            show_ext=False,
            ylim=(96.7, 106.45),
        ),
    ]

    axes = []
    for i, p in enumerate(panels):
        r, c = divmod(i, 2)
        ax = fig.add_subplot(gs[r, c])
        axes.append(ax)
        style_ax(ax, p["ylim"])
        add_levels(ax, show_ext=p["show_ext"])
        draw_candles(ax, SERIES[i])
        ax._panel_meta = p  # type: ignore

    ax1, ax2, ax3, ax4 = axes

    # ----- Panel 1 -----
    # Empty band above PM high holds the break callout and the target badge.
    callout(
        ax1,
        xy=(11, 102.90),
        xytext=(12.8, 105.70),
        text="ORB high breaks",
        color=ACCENT,
        fontsize=7.7,
        ha="left",
        rad=0.05,
    )
    ax1.annotate(
        "",
        xy=(17.0, 104.05),
        xytext=(11.25, 103.05),
        arrowprops=dict(
            arrowstyle="-|>",
            color=TARGET_GREEN,
            lw=1.4,
            mutation_scale=11,
            connectionstyle="arc3,rad=-0.18",
        ),
        zorder=6,
    )
    # Label sits above the arc and above the PM high line, left of the badge
    ax1.text(
        16.3,
        105.05,
        "Runs to PM high",
        color=TARGET_GREEN,
        fontproperties=fp_med,
        fontsize=7.3,
        ha="center",
        va="center",
        zorder=7,
        path_effects=stroke(),
    )
    pill(
        ax1,
        24.6,
        105.55,
        "TARGET HIT",
        facecolor="#0f3d32",
        edgecolor=TARGET_GREEN,
        fontsize=7.6,
        text_color=TARGET_GREEN,
    )

    # ----- Panel 2 -----
    callout(
        ax2,
        xy=(11.15, 102.95),
        xytext=(14.6, 105.70),
        text="Break fails",
        color="#f8b4b4",
        fontsize=7.7,
        ha="left",
        rad=0.0,
    )
    ax2.annotate(
        "",
        xy=(18.0, 100.05),
        xytext=(12.55, 102.55),
        arrowprops=dict(
            arrowstyle="-|>",
            color=DOWN,
            lw=1.4,
            mutation_scale=11,
            connectionstyle="arc3,rad=-0.12",
        ),
        zorder=6,
    )
    # Big empty pocket after the drop, between ORB high and the flat hold at 100
    ax2.text(
        23.6,
        101.55,
        "Failed breakout  →  retrace range",
        color=DOWN,
        fontproperties=fp_med,
        fontsize=7.4,
        ha="center",
        va="center",
        zorder=7,
        path_effects=stroke(),
    )
    pill(
        ax2,
        25.0,
        98.85,
        "HITS ORB LOW",
        facecolor="#3a1d22",
        edgecolor=DOWN,
        fontsize=7.3,
        text_color="#f8b4b4",
    )

    # ----- Panel 3 -----
    # Compact flags at the two breaks, kept off the rising candles
    ax3.annotate(
        "Breaks ORB high",
        xy=(10.0, 102.95),
        xytext=(6.15, 103.72),
        ha="right",
        va="center",
        color=ACCENT,
        fontproperties=fp_med,
        fontsize=7.3,
        zorder=7,
        arrowprops=dict(
            arrowstyle="-|>",
            color=ACCENT,
            lw=1.0,
            mutation_scale=8,
            shrinkA=0,
            shrinkB=2,
            connectionstyle="arc3,rad=0.0",
        ),
        path_effects=stroke(),
    )
    ax3.annotate(
        "Breaks PM high",
        xy=(13.0, 104.55),
        xytext=(8.0, 105.55),
        ha="right",
        va="center",
        color=PM_COLOR,
        fontproperties=fp_med,
        fontsize=7.3,
        zorder=7,
        arrowprops=dict(
            arrowstyle="-|>",
            color=PM_COLOR,
            lw=1.0,
            mutation_scale=8,
            shrinkA=0,
            shrinkB=2,
            connectionstyle="arc3,rad=0.12",
        ),
        path_effects=stroke(),
    )
    ax3.annotate(
        "",
        xy=(20.0, 107.00),
        xytext=(13.6, 105.20),
        arrowprops=dict(
            arrowstyle="-|>",
            color=EXT_COLOR,
            lw=1.4,
            mutation_scale=11,
            connectionstyle="arc3,rad=-0.14",
        ),
        zorder=6,
    )
    ax3.text(
        17.4,
        105.72,
        "Runs to 50% extension",
        color=EXT_COLOR,
        fontproperties=fp_med,
        fontsize=7.3,
        ha="center",
        va="center",
        zorder=7,
        path_effects=stroke(),
        rotation=16,
    )
    pill(
        ax3,
        26.8,
        108.25,
        "50% EXTENSION",
        facecolor="#3a3014",
        edgecolor=EXT_COLOR,
        fontsize=7.5,
        text_color=EXT_COLOR,
    )

    # ----- Panel 4 -----
    def reclaim_flag(ax, x_bar, n, label, x_text):
        # Number sits clearly above the PM high line; a thin leader drops to the reclaim candle
        ax.annotate(
            label,
            xy=(x_bar, 102.0),
            xytext=(x_text, 105.55),
            ha="left",
            va="center",
            color=WHITE,
            fontproperties=fp_med,
            fontsize=7.0,
            zorder=8,
            arrowprops=dict(
                arrowstyle="-|>",
                color=BADGE_RED,
                lw=1.0,
                mutation_scale=8,
                shrinkA=0,
                shrinkB=2,
                connectionstyle="arc3,rad=0.0",
            ),
            bbox=dict(
                boxstyle="round,pad=0.28,rounding_size=0.3",
                facecolor="#5a2028",
                edgecolor=BADGE_RED,
                linewidth=0.9,
            ),
        )

    reclaim_flag(ax4, 12.0, "1", "1st reclaim", 7.2)
    reclaim_flag(ax4, 16.0, "2", "2nd reclaim", 17.4)

    # Two-line SIT OUT badge in the clear upper-right, well above PM high
    ax4.text(
        28.4,
        105.55,
        "SIT OUT\ntill PM session",
        ha="center",
        va="center",
        color=WHITE,
        fontproperties=fp_bold,
        fontsize=9.0,
        linespacing=1.25,
        zorder=9,
        bbox=dict(
            boxstyle="round,pad=0.50,rounding_size=0.4",
            facecolor="#8b1e2d",
            edgecolor="#f3a0a8",
            linewidth=1.15,
        ),
    )
    ax4.axvspan(16.5, XMAX, facecolor=BADGE_RED, alpha=0.06, zorder=1)

    # ----- Titles and rule text above each panel (figure coords) -----
    fig.canvas.draw()
    for ax in axes:
        p = ax._panel_meta  # type: ignore
        bbox = ax.get_position()
        x0, x1, y0, y1 = bbox.x0, bbox.x1, bbox.y0, bbox.y1
        fig.patches.append(
            FancyBboxPatch(
                (x0, y1 + 0.014),
                x1 - x0,
                0.038,
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
            y1 + 0.047,
            p["title"],
            ha="left",
            va="top",
            color=WHITE,
            fontproperties=fp_semb,
            fontsize=9.4,
            zorder=4,
        )
        fig.text(
            x0 + 0.008,
            y1 + 0.029,
            p["rule"],
            ha="left",
            va="top",
            color=TEXT,
            fontproperties=fp,
            fontsize=7.35,
            zorder=4,
        )
        is_formula = ax is ax3
        fig.text(
            (x0 + x1) / 2,
            y0 - 0.016,
            p["note"],
            ha="center",
            va="top",
            color=EXT_COLOR if is_formula else TEXT_MUTED,
            fontproperties=fp_mono_med if is_formula else fp,
            fontsize=6.8 if is_formula else 7.0,
            zorder=4,
        )

    legend_items = [
        Line2D([0], [0], color=ORB_COLOR, lw=2.0, label="ORB high / ORB low"),
        Line2D([0], [0], color=PM_COLOR, lw=1.6, ls=(0, (4, 2.5)), label="Premarket high / low"),
        Line2D([0], [0], color=EXT_COLOR, lw=1.6, ls=(0, (5, 2)), label="50% extension"),
        mpatches.Patch(facecolor=ORB_FILL, alpha=0.35, edgecolor=ORB_COLOR, label="Opening range (first 15 min)"),
        Line2D([0], [0], color=UP, lw=6, solid_capstyle="butt", label="Up candle"),
        Line2D([0], [0], color=DOWN, lw=6, solid_capstyle="butt", label="Down candle"),
    ]
    fig.legend(
        handles=legend_items,
        loc="lower center",
        bbox_to_anchor=(0.50, 0.028),
        ncol=6,
        frameon=False,
        handlelength=1.8,
        handletextpad=0.45,
        columnspacing=1.35,
        labelcolor=TEXT_MUTED,
        prop=FontProperties(fname="fonts/Inter-Regular.ttf", size=7.4),
    )

    fig.text(
        0.50,
        0.013,
        "Illustrative example, not real data.    For education only — not financial advice.    Opening range = first 15 minutes after the 9:30 open  (three 5-min candles).",
        ha="center",
        va="bottom",
        color=TEXT_DIM,
        fontproperties=fp,
        fontsize=6.7,
    )

    out = "orb-rules-visual.png"
    fig.savefig(out, dpi=200, facecolor=FIG_BG, edgecolor="none")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
