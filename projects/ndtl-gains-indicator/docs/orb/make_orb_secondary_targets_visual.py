#!/usr/bin/env python3
"""Educational ORB secondary-targets / strong-trend companion visual.
Synthetic 5-minute candles. Illustrative example, not real data.
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
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch
from matplotlib.lines import Line2D
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

# ---------------------------------------------------------------------------
# Theme — match the ORB Rules companion poster exactly
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
ADR_COLOR = "#f5c14a"
PD_COLOR = "#fb923c"       # prior day
PW_COLOR = "#22d3ee"       # prior week
OPEN_COLOR = "#6b7280"
ACCENT = "#7dd3fc"
BADGE_RED = "#e35d6a"
TARGET_GREEN = "#34d399"

# Levels — ORB / premarket match the first poster; then secondary + weekly
PDL = 96.0
PML = 98.0          # also today's low (tagged in premarket)
ORB_L = 100.0
ORB_H = 102.0
PMH = 104.0
PDH = 108.0
ADR = 14.0
DAY_LOW = PML       # 98
ADR_TOP = DAY_LOW + ADR  # 112
PWH = 116.0

N_PM = 6
N = 33
XMIN = -0.7
XMAX = 35.8
YLIM = (92.8, 118.9)


def tlabel(i: int) -> str:
    minutes = 9 * 60 + i * 5
    h, m = divmod(minutes, 60)
    return f"{h}:{m:02d}"


def candle(o, h, l, c):
    h = max(h, o, c)
    l = min(l, o, c)
    return (round(o, 2), round(h, 2), round(l, 2), round(c, 2))


def stroke(w=3.4, fg=AX_BG):
    return [pe.withStroke(linewidth=w, foreground=fg)]


# Same premarket + opening range as the companion poster (visual continuity)
PM = [
    (100.20, 100.80, 99.85, 100.50),
    (100.50, 102.45, 100.40, 102.15),
    (102.15, 104.00, 101.90, 103.20),  # tags PMH
    (103.20, 103.50, 100.55, 100.85),
    (100.85, 101.15, 98.00, 98.55),    # tags PML / day's low
    (98.55, 100.55, 98.35, 100.25),
]

ORB = [
    (100.25, 101.30, 100.00, 101.10),
    (101.10, 101.85, 100.65, 101.60),
    (101.60, 102.00, 101.15, 101.50),
]

# Panel A: already through ORB + PM high, then PDH (target 1), then ADR top (target 2)
A_REST = [
    (101.50, 101.80, 101.20, 101.45),  # 9
    (101.45, 103.15, 101.40, 102.95),  # 10  BREAK ORB high
    (102.95, 104.65, 102.80, 104.45),  # 11  BREAK PM high
    (104.45, 105.25, 104.20, 105.05),  # 12
    (105.05, 105.75, 104.85, 105.55),  # 13
    (105.55, 106.25, 105.35, 106.05),  # 14
    (106.05, 106.75, 105.85, 106.55),  # 15
    (106.55, 107.35, 106.35, 107.15),  # 16
    (107.15, 107.80, 106.95, 107.60),  # 17
    (107.60, 108.30, 107.45, 108.10),  # 18  TAG PDH — target 1
    (108.10, 108.35, 107.70, 107.90),  # 19  brief pause
    (107.90, 108.20, 107.65, 108.05),  # 20
    (108.05, 108.75, 107.90, 108.55),  # 21  resume
    (108.55, 109.35, 108.35, 109.15),  # 22
    (109.15, 109.90, 108.95, 109.70),  # 23
    (109.70, 110.45, 109.50, 110.25),  # 24
    (110.25, 110.95, 110.05, 110.75),  # 25
    (110.75, 111.45, 110.55, 111.25),  # 26
    (111.25, 112.20, 111.05, 112.00),  # 27  TAG ADR top — target 2
    (112.00, 112.28, 111.70, 111.88),  # 28
    (111.88, 112.12, 111.62, 111.82),  # 29
    (111.82, 112.08, 111.55, 111.76),  # 30
    (111.76, 112.02, 111.50, 111.70),  # 31
    (111.70, 111.96, 111.48, 111.68),  # 32
]

# Panel B: climbs the full ladder — ORB, PM high, PDH, prior week high
B_REST = [
    (101.50, 101.75, 101.20, 101.40),  # 9
    (101.40, 102.90, 101.35, 102.75),  # 10  BREAK ORB high
    (102.75, 103.40, 102.55, 103.20),  # 11
    (103.20, 104.55, 103.05, 104.40),  # 12  BREAK PM high
    (104.40, 105.15, 104.20, 104.95),  # 13
    (104.95, 105.75, 104.75, 105.55),  # 14
    (105.55, 106.35, 105.35, 106.15),  # 15
    (106.15, 106.95, 105.95, 106.75),  # 16
    (106.75, 107.55, 106.55, 107.35),  # 17
    (107.35, 108.45, 107.20, 108.30),  # 18  BREAK PDH
    (108.30, 108.85, 108.10, 108.60),  # 19
    (108.60, 109.45, 108.40, 109.25),  # 20
    (109.25, 110.15, 109.05, 109.95),  # 21
    (109.95, 110.85, 109.75, 110.65),  # 22
    (110.65, 111.55, 110.45, 111.35),  # 23
    (111.35, 112.30, 111.15, 112.10),  # 24
    (112.10, 113.05, 111.90, 112.85),  # 25
    (112.85, 113.80, 112.65, 113.55),  # 26
    (113.55, 114.55, 113.35, 114.35),  # 27
    (114.35, 115.30, 114.15, 115.10),  # 28
    (115.10, 116.28, 114.90, 116.08),  # 29  BREAK PWH
    (116.08, 116.40, 115.72, 115.95),  # 30
    (115.95, 116.28, 115.65, 115.88),  # 31
    (115.88, 116.20, 115.60, 115.82),  # 32
]

# Inset: clears ORB + PM high, then stalls under PDH
INSET_REST = [
    (101.50, 101.80, 101.25, 101.55),  # 9
    (101.55, 102.85, 101.45, 102.70),  # 10  BREAK ORB
    (102.70, 103.50, 102.55, 103.30),  # 11
    (103.30, 104.55, 103.15, 104.35),  # 12  BREAK PMH
    (104.35, 105.20, 104.15, 104.95),  # 13
    (104.95, 105.70, 104.75, 105.40),  # 14
    (105.40, 106.15, 105.15, 105.85),  # 15
    (105.85, 106.60, 105.60, 106.20),  # 16
    (106.20, 107.15, 105.95, 106.70),  # 17  approaches PDH
    (106.70, 107.55, 106.40, 106.85),  # 18  reject under PDH
    (106.85, 107.10, 106.15, 106.35),  # 19
    (106.35, 106.80, 105.70, 105.95),  # 20
    (105.95, 106.45, 105.40, 105.70),  # 21
    (105.70, 106.90, 105.50, 106.55),  # 22  another poke
    (106.55, 107.40, 106.25, 106.50),  # 23  fail again
    (106.50, 106.80, 105.80, 106.05),  # 24
    (106.05, 106.50, 105.55, 105.80),  # 25
    (105.80, 106.20, 105.35, 105.60),  # 26
    (105.60, 106.00, 105.20, 105.45),  # 27
    (105.45, 105.90, 105.10, 105.35),  # 28
    (105.35, 105.80, 105.00, 105.25),  # 29
    (105.25, 105.70, 104.95, 105.20),  # 30
    (105.20, 105.60, 104.90, 105.15),  # 31
    (105.15, 105.55, 104.85, 105.10),  # 32
]


def series(rest):
    bars = [candle(*b) for b in (PM + ORB + rest)]
    assert len(bars) == N, len(bars)
    return bars


A_BARS = series(A_REST)
B_BARS = series(B_REST)
INSET_BARS = series(INSET_REST)


def draw_candles(ax, bars, pm_end=N_PM, width=0.66, lw=1.25, pm_alpha=0.48):
    for i, (o, h, l, c) in enumerate(bars):
        color = UP if c >= o else DOWN
        alpha = pm_alpha if i < pm_end else 1.0
        ax.vlines(i, l, h, color=color, linewidth=lw, alpha=alpha, zorder=3)
        body_lo, body_hi = min(o, c), max(o, c)
        if abs(c - o) < 0.03:
            ax.hlines(i - width / 2 if False else c, i - width / 2, i + width / 2,
                      color=color, linewidth=lw + 0.1, alpha=alpha, zorder=4)
            ax.hlines(c, i - width / 2, i + width / 2, color=color, linewidth=lw + 0.1, alpha=alpha, zorder=4)
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


def hline(ax, y, color, ls, lw=1.1, xmin=XMIN, xmax=XMAX):
    ax.hlines(y, xmin, xmax, colors=color, linestyles=ls, linewidth=lw, zorder=2, alpha=0.95)


def right_label(ax, y, text, color, va="bottom", dy=0.22, fontsize=7.2):
    ax.text(
        XMAX - 0.12,
        y + dy,
        text,
        ha="right",
        va=va,
        color=color,
        fontproperties=fp_med,
        fontsize=fontsize,
        zorder=6,
        path_effects=stroke(),
    )


def add_orb_and_session(ax, y_pm_open=93.45):
    ax.add_patch(
        Rectangle((5.5, ORB_L), 3.0, ORB_H - ORB_L, facecolor=ORB_FILL, edgecolor="none", alpha=0.18, zorder=1)
    )
    ax.axvspan(XMIN, 5.5, facecolor="#0a0c11", alpha=0.55, zorder=0)
    ax.axvline(5.5, color=OPEN_COLOR, linewidth=0.85, linestyle=(0, (2.2, 3.0)), zorder=2, alpha=0.9)
    ax.text(2.35, y_pm_open, "Premarket", ha="center", va="center", color=TEXT_DIM, fontproperties=fp_med, fontsize=6.6, zorder=5)
    ax.text(5.75, y_pm_open, "Open", ha="left", va="center", color=TEXT_DIM, fontproperties=fp_med, fontsize=6.6, zorder=5)


def style_ax(ax, ylim=YLIM, yticks=None, fontsize_ticks=7.0):
    ax.set_facecolor(AX_BG)
    ax.set_xlim(XMIN, XMAX)
    ax.set_ylim(*ylim)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6, alpha=1)
    ax.xaxis.grid(False)
    ax.tick_params(axis="both", length=0, pad=3, colors=TEXT_MUTED)
    ticks = [0, 6, 12, 18, 24, 30]
    ax.set_xticks(ticks)
    ax.set_xticklabels([tlabel(i) for i in ticks], fontproperties=fp, fontsize=fontsize_ticks, color=TEXT_MUTED)
    if yticks is None:
        yticks = [PDL, PML, ORB_L, ORB_H, PMH, PDH, ADR_TOP, PWH]
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{y:.0f}" for y in yticks], fontproperties=fp_mono, fontsize=fontsize_ticks, color=TEXT_MUTED)
    for s in ax.spines.values():
        s.set_color(SPINE)
        s.set_linewidth(0.8)
    ax.spines["top"].set_visible(False)


def pill(ax, x, y, text, facecolor, edgecolor, fontsize=7.4, text_color=WHITE, font=None):
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        color=text_color,
        fontproperties=font or fp_semb,
        fontsize=fontsize,
        zorder=8,
        bbox=dict(
            boxstyle="round,pad=0.35,rounding_size=0.35",
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=0.9,
        ),
    )


def main():
    # 12 in * 200 dpi = 2400 px wide
    fig = plt.figure(figsize=(12.00, 10.15), dpi=200, facecolor=FIG_BG)

    # ----- Title -----
    fig.text(
        0.50,
        0.978,
        "Opening Range Breakout (ORB)  ·  Secondary Targets",
        ha="center",
        va="top",
        color=WHITE,
        fontproperties=fp_bold,
        fontsize=20.0,
    )
    fig.text(
        0.50,
        0.949,
        "After the opening range and premarket levels.    ·    Illustrative example, not real data.",
        ha="center",
        va="top",
        color=TEXT_MUTED,
        fontproperties=fp,
        fontsize=9.0,
    )

    # ----- Checklist banner -----
    fig.text(
        0.50,
        0.915,
        "A strong trend is only present if price is beyond all four:",
        ha="center",
        va="top",
        color=TEXT,
        fontproperties=fp_med,
        fontsize=9.0,
    )

    checks = [
        ("1", "ORB", ORB_COLOR),
        ("2", "Premarket high / low", PM_COLOR),
        ("3", "Prior day high / low", PD_COLOR),
        ("4", "Prior WEEK high / low", PW_COLOR),
    ]
    n = len(checks)
    left, right = 0.055, 0.945
    box_h = 0.042
    box_y = 0.857
    gap = 0.018
    usable = (right - left) - gap * (n - 1)
    box_w = usable / n
    for i, (num, label, color) in enumerate(checks):
        x = left + i * (box_w + gap)
        fig.patches.append(
            FancyBboxPatch(
                (x, box_y),
                box_w,
                box_h,
                boxstyle="round,pad=0.002,rounding_size=0.006",
                facecolor="#181c27",
                edgecolor=color,
                linewidth=1.15,
                transform=fig.transFigure,
                zorder=2,
            )
        )
        fig.text(
            x + box_w / 2 - 0.004,
            box_y + box_h / 2,
            f"{num}    {label}",
            ha="center",
            va="center",
            color=WHITE,
            fontproperties=fp_semb,
            fontsize=8.6,
            zorder=4,
        )
        if i < n - 1:
            fig.text(
                x + box_w + gap / 2,
                box_y + box_h / 2,
                "→",
                ha="center",
                va="center",
                color=TEXT_DIM,
                fontproperties=fp_med,
                fontsize=12.0,
                zorder=4,
            )

    # ----- Two chart panels -----
    gs = fig.add_gridspec(
        1,
        2,
        left=0.046,
        right=0.978,
        top=0.792,
        bottom=0.108,
        wspace=0.145,
    )

    # ===================== Panel A =====================
    axA = fig.add_subplot(gs[0, 0])
    style_ax(axA, yticks=[PDL, PML, ORB_L, ORB_H, PMH, PDH, ADR_TOP])
    add_orb_and_session(axA)
    # PDL / PDH
    hline(axA, PDL, PD_COLOR, (0, (4.5, 3.0)), 1.15)
    hline(axA, PDH, PD_COLOR, (0, (4.5, 3.0)), 1.2)
    # PM
    hline(axA, PMH, PM_COLOR, (0, (4.5, 3.0)), 1.15)
    hline(axA, PML, PM_COLOR, (0, (4.5, 3.0)), 1.15)
    # ORB
    hline(axA, ORB_H, ORB_COLOR, "-", 1.3)
    hline(axA, ORB_L, ORB_COLOR, "-", 1.3)
    # ADR top
    hline(axA, ADR_TOP, ADR_COLOR, (0, (5.5, 2.4)), 1.3)

    right_label(axA, ADR_TOP, "ADR top", ADR_COLOR, "bottom", 0.28, 7.3)
    right_label(axA, PDH, "PD High", PD_COLOR, "bottom", 0.26, 7.3)
    right_label(axA, PMH, "PM High", PM_COLOR, "bottom", 0.22, 7.2)
    right_label(axA, ORB_H, "ORB High", ORB_COLOR, "bottom", 0.20, 7.2)
    right_label(axA, ORB_L, "ORB Low", ORB_COLOR, "top", -0.20, 7.2)
    right_label(axA, PML, "PM Low  ·  day's low", PM_COLOR, "top", -0.22, 7.0)
    right_label(axA, PDL, "PD Low", PD_COLOR, "top", -0.22, 7.2)

    draw_candles(axA, A_BARS)

    # "Already through ORB + PM high" — empty pocket above PMH on the left (premarket only reaches 104)
    axA.annotate(
        "Already through\nORB + PM high",
        xy=(11.0, 104.65),
        xytext=(1.0, 107.15),
        ha="left",
        va="center",
        color=ACCENT,
        fontproperties=fp_med,
        fontsize=7.3,
        linespacing=1.25,
        zorder=7,
        arrowprops=dict(
            arrowstyle="-|>",
            color=ACCENT,
            lw=1.05,
            mutation_scale=8,
            shrinkA=0,
            shrinkB=3,
            connectionstyle="arc3,rad=0.08",
        ),
        path_effects=stroke(),
    )

    # Target 1 — keep the badge and caption in the empty pocket ABOVE PDH
    # and LEFT of the resume (bars 14–17 are still under 108).
    axA.annotate(
        "",
        xy=(18.0, 108.30),
        xytext=(14.6, 109.15),
        arrowprops=dict(
            arrowstyle="-|>",
            color=PD_COLOR,
            lw=1.3,
            mutation_scale=10,
            connectionstyle="arc3,rad=0.10",
        ),
        zorder=6,
    )
    axA.text(
        13.4,
        109.55,
        "Target 1  ·  Prior Day High",
        color=PD_COLOR,
        fontproperties=fp_med,
        fontsize=7.3,
        ha="center",
        va="center",
        zorder=7,
        path_effects=stroke(),
    )
    pill(
        axA,
        13.4,
        110.85,
        "TARGET 1  HIT",
        facecolor="#3a2612",
        edgecolor=PD_COLOR,
        fontsize=7.3,
        text_color=PD_COLOR,
    )

    # Run from PDH to ADR
    axA.annotate(
        "",
        xy=(27.0, 112.00),
        xytext=(20.2, 109.15),
        arrowprops=dict(
            arrowstyle="-|>",
            color=ADR_COLOR,
            lw=1.3,
            mutation_scale=10,
            connectionstyle="arc3,rad=-0.14",
        ),
        zorder=6,
    )
    axA.text(
        23.6,
        113.55,
        "Target 2  ·  ADR top",
        color=ADR_COLOR,
        fontproperties=fp_med,
        fontsize=7.3,
        ha="center",
        va="center",
        zorder=7,
        path_effects=stroke(),
    )
    pill(
        axA,
        29.4,
        114.35,
        "TARGET 2  HIT",
        facecolor="#3a3014",
        edgecolor=ADR_COLOR,
        fontsize=7.3,
        text_color=ADR_COLOR,
    )

    # ===================== Panel B =====================
    axB = fig.add_subplot(gs[0, 1])
    style_ax(axB, yticks=[PML, ORB_L, ORB_H, PMH, PDH, PWH])
    add_orb_and_session(axB)
    hline(axB, PMH, PM_COLOR, (0, (4.5, 3.0)), 1.15)
    hline(axB, PML, PM_COLOR, (0, (4.5, 3.0)), 1.15)
    hline(axB, ORB_H, ORB_COLOR, "-", 1.3)
    hline(axB, ORB_L, ORB_COLOR, "-", 1.3)
    hline(axB, PDH, PD_COLOR, (0, (4.5, 3.0)), 1.2)
    hline(axB, PWH, PW_COLOR, (0, (4.5, 3.0)), 1.25)

    # Right-edge labels only for levels that sit ABOVE the contrast inset
    # (inset occupies the lower-right, covering ORB / PM labels).
    right_label(axB, PWH, "PW High", PW_COLOR, "bottom", 0.28, 7.4)
    right_label(axB, PDH, "PD High", PD_COLOR, "bottom", 0.26, 7.4)

    draw_candles(axB, B_BARS)

    # Ladder card in the empty upper-left (premarket never trades here).
    # Stacked top-to-bottom like the price ladder, each level checked off.
    card_x0, card_x1 = 0.15, 11.15
    card_y0, card_y1 = 109.55, 115.55
    axB.add_patch(
        FancyBboxPatch(
            (card_x0, card_y0),
            card_x1 - card_x0,
            card_y1 - card_y0,
            boxstyle="round,pad=0.12,rounding_size=0.25",
            facecolor="#181c27",
            edgecolor="#2a2e39",
            linewidth=0.9,
            zorder=7,
            mutation_aspect=0.5,
        )
    )
    axB.text(
        (card_x0 + card_x1) / 2,
        card_y1 - 0.38,
        "Cleared  —  the 4-level ladder",
        ha="center",
        va="top",
        color=TEXT_MUTED,
        fontproperties=fp_med,
        fontsize=6.4,
        zorder=8,
    )
    ladder_rows = [
        (4, "Prior WEEK high", PW_COLOR),
        (3, "Prior day high", PD_COLOR),
        (2, "Premarket high", PM_COLOR),
        (1, "ORB", ORB_COLOR),
    ]
    # 4 rows in the remaining card body
    body_top = card_y1 - 1.15
    body_bot = card_y0 + 0.35
    for i, (num, lab, col) in enumerate(ladder_rows):
        y = body_top - i * (body_top - body_bot) / 3
        axB.text(
            card_x0 + 0.55,
            y,
            "✓",
            ha="center",
            va="center",
            color=TARGET_GREEN,
            fontproperties=fp_bold,
            fontsize=8.0,
            zorder=8,
        )
        axB.text(
            card_x0 + 1.25,
            y,
            f"{num}   {lab}",
            ha="left",
            va="center",
            color=col,
            fontproperties=fp_semb,
            fontsize=7.2,
            zorder=8,
        )

    # Confirmed badge just above the ladder card, still in the empty left pocket
    axB.text(
        (card_x0 + card_x1) / 2,
        117.55,
        "STRONG TREND CONFIRMED\nbeyond all 4",
        ha="center",
        va="center",
        color=WHITE,
        fontproperties=fp_bold,
        fontsize=7.5,
        linespacing=1.25,
        zorder=9,
        bbox=dict(
            boxstyle="round,pad=0.42,rounding_size=0.4",
            facecolor="#0f3d32",
            edgecolor=TARGET_GREEN,
            linewidth=1.15,
        ),
    )

    # ----- Contrast inset -----
    ins = axB.inset_axes([0.50, 0.048, 0.48, 0.36])
    ins.set_facecolor("#10141c")
    # Independent view of the stall: crop to late premarket through the stall
    # Show a slightly tighter y so PDH is the ceiling
    ins.set_xlim(5.0, 33.5)
    ins.set_ylim(99.4, 110.6)
    ins.set_axisbelow(True)
    ins.yaxis.grid(True, color=GRID, linewidth=0.5, alpha=1)
    ins.xaxis.grid(False)
    ins.tick_params(axis="both", length=0, pad=1.5, colors=TEXT_DIM, labelsize=5.4)
    ins.set_xticks([6, 18, 30])
    ins.set_xticklabels(["9:30", "10:30", "11:30"], fontproperties=fp, fontsize=5.4, color=TEXT_DIM)
    ins.set_yticks([ORB_H, PMH, PDH])
    ins.set_yticklabels(["102", "104", "108"], fontproperties=fp_mono, fontsize=5.4, color=TEXT_DIM)
    for s in ins.spines.values():
        s.set_color("#e35d6a")
        s.set_linewidth(1.15)
    # levels
    ins.add_patch(Rectangle((5.5, ORB_L), 3.0, ORB_H - ORB_L, facecolor=ORB_FILL, edgecolor="none", alpha=0.20, zorder=1))
    ins.hlines(ORB_H, 5.0, 33.5, colors=ORB_COLOR, linestyles="-", linewidth=0.9, zorder=2)
    ins.hlines(PMH, 5.0, 33.5, colors=PM_COLOR, linestyles=(0, (3.5, 2.2)), linewidth=0.9, zorder=2)
    ins.hlines(PDH, 5.0, 33.5, colors=PD_COLOR, linestyles=(0, (3.5, 2.2)), linewidth=1.05, zorder=2)
    ins.text(33.1, PDH + 0.22, "PDH", ha="right", va="bottom", color=PD_COLOR, fontproperties=fp_med, fontsize=5.8, path_effects=stroke(2.4, "#10141c"), zorder=6)
    draw_candles(ins, INSET_BARS, width=0.70, lw=0.85, pm_alpha=0.40)
    ins.set_title(
        "If it stalls under PDH",
        fontproperties=fp_semb,
        fontsize=6.6,
        color=WHITE,
        pad=3.0,
        loc="left",
    )
    ins.text(
        0.50,
        0.10,
        "NOT A STRONG TREND YET",
        transform=ins.transAxes,
        ha="center",
        va="center",
        color="#f3a0a8",
        fontproperties=fp_semb,
        fontsize=6.2,
        zorder=8,
        bbox=dict(
            boxstyle="round,pad=0.30,rounding_size=0.3",
            facecolor="#3a1d22",
            edgecolor=BADGE_RED,
            linewidth=0.8,
        ),
    )

    # ----- Panel headers + captions (figure coords) -----
    fig.canvas.draw()
    headers = [
        (
            axA,
            "Panel A  —  Secondary targets",
            "After ORB and premarket break, the next targets are prior day high / low, then ADR.",
            "ADR top  =  day's low  +  average daily range     (98 + 14 = 112)",
            ADR_COLOR,
            fp_mono_med,
        ),
        (
            axB,
            "Panel B  —  Strong trend check",
            "A strong trend is only present if price is beyond all four levels.",
            "Same idea in reverse for a downtrend, using the lows.",
            TEXT_MUTED,
            fp,
        ),
    ]
    for ax, title, rule, note, note_color, note_fp in headers:
        bbox = ax.get_position()
        x0, x1, y0, y1 = bbox.x0, bbox.x1, bbox.y0, bbox.y1
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
            y1 + 0.026,
            rule,
            ha="left",
            va="top",
            color=TEXT,
            fontproperties=fp,
            fontsize=7.15,
            zorder=4,
        )
        fig.text(
            (x0 + x1) / 2,
            y0 - 0.016,
            note,
            ha="center",
            va="top",
            color=note_color,
            fontproperties=note_fp,
            fontsize=6.8,
            zorder=4,
        )

    # ----- Legend + footer -----
    legend_items = [
        Line2D([0], [0], color=ORB_COLOR, lw=2.0, label="ORB high / ORB low"),
        Line2D([0], [0], color=PM_COLOR, lw=1.6, ls=(0, (4, 2.5)), label="Premarket high / low"),
        Line2D([0], [0], color=PD_COLOR, lw=1.6, ls=(0, (4, 2.5)), label="Prior day high / low"),
        Line2D([0], [0], color=ADR_COLOR, lw=1.6, ls=(0, (5, 2)), label="ADR top"),
        Line2D([0], [0], color=PW_COLOR, lw=1.6, ls=(0, (4, 2.5)), label="Prior week high"),
        Line2D([0], [0], color=UP, lw=6, solid_capstyle="butt", label="Up candle"),
        Line2D([0], [0], color=DOWN, lw=6, solid_capstyle="butt", label="Down candle"),
    ]
    fig.legend(
        handles=legend_items,
        loc="lower center",
        bbox_to_anchor=(0.50, 0.032),
        ncol=7,
        frameon=False,
        handlelength=1.7,
        handletextpad=0.40,
        columnspacing=1.15,
        labelcolor=TEXT_MUTED,
        prop=FontProperties(fname="fonts/Inter-Regular.ttf", size=7.2),
    )
    fig.text(
        0.50,
        0.014,
        "Illustrative example, not real data.    For education only — not financial advice.    Opening range = first 15 minutes after the 9:30 open  (three 5-min candles).",
        ha="center",
        va="bottom",
        color=TEXT_DIM,
        fontproperties=fp,
        fontsize=6.6,
    )

    out = "orb-secondary-targets-visual.png"
    fig.savefig(out, dpi=200, facecolor=FIG_BG, edgecolor="none")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
