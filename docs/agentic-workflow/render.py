#!/usr/bin/env python3
"""Render the Grok Bot org chart from org.yaml.

Run from this folder:

    python3 render.py

Reads org.yaml and writes:
  - org-chart.html  (generated; do not hand-edit)
  - org-chart.png   (canonical image for GitHub)
  - the Mermaid block in README.md between ORG_MERMAID markers
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import yaml
from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
YAML_PATH = HERE / "org.yaml"
HTML_PATH = HERE / "org-chart.html"
PNG_PATH = HERE / "org-chart.png"
README_PATH = HERE / "README.md"
MAX_PNG_BYTES = 2 * 1024 * 1024

CHROME_CANDIDATES = (
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)


def load_org() -> dict:
    data = yaml.safe_load(YAML_PATH.read_text())
    if not data or "ceo" not in data or "router" not in data:
        raise SystemExit(f"org.yaml is missing required keys: {YAML_PATH}")
    return data


def esc(value: str) -> str:
    return html.escape(value, quote=True)


# --- Mermaid -----------------------------------------------------------------

def mermaid_id(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", raw)


def mermaid_label(text: str) -> str:
    # Mermaid node labels: keep quotes safe, no HTML.
    return text.replace('"', "'").replace("[", "(").replace("]", ")")


def build_mermaid(org: dict) -> str:
    ceo = org["ceo"]
    router = org["router"]
    team = org["teams"][0]
    lead = team["lead"]
    specialists = org["specialists"]

    tech = next(m for m in team["members"] if m.get("dual_role"))
    others = [m for m in team["members"] if not m.get("dual_role")]

    lines = [
        "flowchart TB",
        f'    {mermaid_id(ceo["id"])}["{mermaid_label(ceo["name"] + " — " + ceo["role"] + " (human)")}"]',
        f'    {mermaid_id(router["id"])}["{mermaid_label(router["name"] + " — " + router["role"])}"]',
        f'    {mermaid_id(ceo["id"])} --> {mermaid_id(router["id"])}',
        "",
        f'    subgraph dash["{mermaid_label(team["name"])}"]',
        "        direction TB",
        f'        {mermaid_id(lead["id"])}["{mermaid_label(lead["name"] + " — " + lead["role"])}"]',
    ]
    for m in others:
        lines.append(
            f'        {mermaid_id(m["id"])}["{mermaid_label(m["name"] + " — " + m["role"])}"]'
        )
    lines.append(
        f'        {mermaid_id(tech["id"])}["{mermaid_label(tech["name"] + " — " + tech["role"] + " · also a specialist")}"]'
    )
    member_ids = " & ".join(mermaid_id(m["id"]) for m in others + [tech])
    lines.append(f'        {mermaid_id(lead["id"])} --> {member_ids}')
    lines.append("    end")
    lines.append("")
    lines.append(f'    subgraph specs["{mermaid_label(specialists["name"])}"]')
    lines.append("        direction TB")
    spec_ids = []
    for m in specialists["members"]:
        sid = mermaid_id(m["id"])
        spec_ids.append(sid)
        lines.append(f'        {sid}["{mermaid_label(m["name"])}"]')
    lines.append("    end")
    lines.append("")
    lines.append(f'    {mermaid_id(router["id"])} --> {mermaid_id(lead["id"])}')
    # Link to the specialists subgraph (not each member) so GitHub rendering stays readable.
    lines.append(f'    {mermaid_id(router["id"])} --> specs')
    lines.append(
        f'    {mermaid_id(router["id"])} -.->|{mermaid_label("also a specialist")}| {mermaid_id(tech["id"])}'
    )
    return "\n".join(lines) + "\n"


def update_readme_mermaid(mermaid_src: str) -> None:
    start = "<!-- ORG_MERMAID_START -->"
    end = "<!-- ORG_MERMAID_END -->"
    block = f"{start}\n```mermaid\n{mermaid_src}```\n{end}"
    text = README_PATH.read_text()
    if start not in text or end not in text:
        raise SystemExit("README.md is missing ORG_MERMAID_START/END markers")
    updated = re.sub(
        re.escape(start) + r".*?" + re.escape(end),
        block,
        text,
        count=1,
        flags=re.S,
    )
    README_PATH.write_text(updated)


# --- HTML --------------------------------------------------------------------

ICON_USER = """
<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="8" r="3.2"/>
  <path d="M5.5 19c1.2-3.1 3.6-4.6 6.5-4.6S16.8 15.9 18 19"/>
</svg>
""".strip()

ICON_ROUTER = """
<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"/>
  <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.2 2.2M16.2 16.2l2.2 2.2M18.4 5.6l-2.2 2.2M7.8 16.2l-2.2 2.2"/>
</svg>
""".strip()

ICON_LEAD = """
<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="8"/>
  <path d="m8.5 12 2.3 2.3 4.7-5"/>
</svg>
""".strip()

ROLE_ICONS = {
    "specs": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4h10v16H7z"/><path d="M10 8h4M10 12h4M10 16h2"/></svg>""",
    "builds": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19V5h7l8 7-8 7H4Z"/></svg>""",
    "tests": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3h8v6l-2.5 3.5L16 16v5H8v-5l2.5-3.5L8 9V3Z"/></svg>""",
    "infra": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01"/></svg>""",
    "publishing": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M3 12h6M15 12h6M12 3v6M12 15v6"/></svg>""",
}

FOOTER_ICONS = [
    """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 5 6v6c0 5 3.2 8 7 9 3.8-1 7-4 7-9V6l-7-3Z"/></svg>""",
    """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><path d="M8 12h8"/></svg>""",
    """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19V5h7l8 7-8 7H4Z"/></svg>""",
]


def build_html(org: dict) -> str:
    ceo = org["ceo"]
    router = org["router"]
    team = org["teams"][0]
    lead = team["lead"]
    members = team["members"]
    specialists = org["specialists"]
    footer = org.get("footer") or []

    member_cards = []
    for m in members:
        role_key = m["role"].lower()
        icon = ROLE_ICONS.get(role_key, ROLE_ICONS["infra"])
        dual = ""
        extra_class = ""
        if m.get("dual_role"):
            extra_class = " dual"
            label = m.get("dual_label") or "Dual role"
            dual = f'<div class="dual-badge">{esc(label)}</div>'
        member_cards.append(
            f"""
            <article class="member{extra_class}" id="{esc(m['id'])}">
              <div class="bot-icon">{icon}</div>
              <div class="bot-body">
                <h4>{esc(m['name'])}</h4>
                <p class="role">{esc(m['role'])}</p>
                {dual}
              </div>
            </article>"""
        )

    specialist_cards = []
    for m in specialists["members"]:
        specialist_cards.append(
            f"""
            <article class="specialist" id="{esc(m['id'])}">
              <h4>{esc(m['name'])}</h4>
            </article>"""
        )

    footer_items = []
    for i, text in enumerate(footer):
        icon = FOOTER_ICONS[i] if i < len(FOOTER_ICONS) else FOOTER_ICONS[0]
        footer_items.append(f'<div class="guard">{icon}{esc(text)}</div>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>{esc(org['title'])}</title>
<style>
  @font-face {{
    font-family: "Outfit";
    src: url("Outfit-VariableFont_wght.ttf") format("truetype");
    font-weight: 100 900;
    font-style: normal;
    font-display: block;
  }}
  @font-face {{
    font-family: "Geist";
    src: url("Geist-VariableFont_wght.ttf") format("truetype");
    font-weight: 100 900;
    font-style: normal;
    font-display: block;
  }}

  :root {{
    --bg: #0A0C10;
    --card: #161A23;
    --card-2: #1C212C;
    --line: rgba(255,255,255,0.09);
    --text: #F3F5F8;
    --muted: #C8CED7;
    --dim: #A8B0BB;
    --gold: #E8C36A;
    --gold-2: #F3D58A;
    --dashboard: #3DD68C;
    --specialists: #7AADFF;
    --qc: #FF9F43;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ background: #000; color: var(--text); }}

  #poster {{
    position: relative;
    width: 1400px;
    background:
      radial-gradient(ellipse 900px 520px at 50% 180px, rgba(232,195,106,0.11), transparent 70%),
      radial-gradient(ellipse 640px 460px at 8% 100%, rgba(61,214,140,0.06), transparent 60%),
      radial-gradient(ellipse 600px 440px at 94% 88%, rgba(122,173,255,0.06), transparent 60%),
      linear-gradient(180deg, #0E1118 0%, var(--bg) 200px, var(--bg) 100%);
    padding: 64px 80px 52px;
    overflow: hidden;
    font-family: "Geist", sans-serif;
  }}

  #poster::before {{
    content: "";
    position: absolute;
    inset: 0;
    background-image: radial-gradient(rgba(255,255,255,0.045) 1px, transparent 1px);
    background-size: 28px 28px;
    mask-image: linear-gradient(180deg, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.25) 300px, rgba(0,0,0,0.12) 100%);
    pointer-events: none;
  }}

  .frame {{
    position: absolute;
    inset: 20px;
    border: 1px solid rgba(232,195,106,0.18);
    pointer-events: none;
    z-index: 2;
  }}

  .inner {{ position: relative; z-index: 1; }}

  header {{
    text-align: center;
    margin-bottom: 36px;
  }}

  .kicker {{
    display: inline-flex;
    align-items: center;
    gap: 10px;
    font-family: "Outfit", sans-serif;
    font-weight: 600;
    font-size: 13px;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--gold);
    margin-bottom: 16px;
  }}
  .kicker::before,
  .kicker::after {{
    content: "";
    width: 28px;
    height: 1px;
    background: var(--gold);
    opacity: 0.7;
  }}

  h1 {{
    font-family: "Outfit", sans-serif;
    font-weight: 650;
    font-size: 56px;
    letter-spacing: -0.03em;
    line-height: 1.05;
    color: #fff;
    margin-bottom: 14px;
  }}

  .subtitle {{
    font-size: 20px;
    font-weight: 400;
    color: var(--muted);
    letter-spacing: -0.01em;
    line-height: 1.4;
    max-width: 920px;
    margin: 0 auto;
  }}

  .chain {{
    display: flex;
    flex-direction: column;
    align-items: center;
  }}

  .human, .router {{
    width: 720px;
    text-align: center;
    border-radius: 18px;
    padding: 22px 36px 24px;
  }}

  .human {{
    background:
      linear-gradient(180deg, rgba(232,195,106,0.16), rgba(232,195,106,0.04) 48%, rgba(22,26,35,0.95)),
      var(--card);
    border: 1.5px solid rgba(232,195,106,0.55);
    box-shadow:
      0 0 0 1px rgba(232,195,106,0.08),
      0 18px 50px rgba(0,0,0,0.35),
      0 0 80px rgba(232,195,106,0.10);
  }}

  .router {{
    background:
      linear-gradient(180deg, rgba(232,195,106,0.09), rgba(232,195,106,0.02) 48%, rgba(22,26,35,0.95)),
      var(--card);
    border: 1px solid rgba(232,195,106,0.35);
    box-shadow:
      0 0 0 1px rgba(232,195,106,0.06),
      0 14px 36px rgba(0,0,0,0.30);
  }}

  .icon-wrap {{
    width: 52px;
    height: 52px;
    margin: 0 auto 10px;
    border-radius: 50%;
    border: 1.5px solid rgba(232,195,106,0.7);
    background: rgba(232,195,106,0.10);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--gold-2);
  }}
  .router .icon-wrap {{
    width: 46px;
    height: 46px;
  }}

  .label {{
    font-family: "Outfit", sans-serif;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--gold);
    margin-bottom: 6px;
  }}

  .human h2, .router h2 {{
    font-family: "Outfit", sans-serif;
    font-weight: 650;
    letter-spacing: -0.03em;
    color: #fff;
    margin-bottom: 8px;
  }}
  .human h2 {{ font-size: 34px; }}
  .router h2 {{ font-size: 30px; }}

  .human p, .router p {{
    font-size: 16.5px;
    line-height: 1.5;
    color: var(--muted);
    max-width: 640px;
    margin: 0 auto;
  }}

  .stem {{
    width: 1.6px;
    height: 28px;
    background: var(--gold);
  }}

  .fork {{
    position: relative;
    width: 100%;
    height: 40px;
  }}
  .fork-v {{
    position: absolute;
    left: 50%;
    top: 0;
    width: 1.6px;
    height: 20px;
    background: var(--gold);
    transform: translateX(-50%);
  }}
  .fork-h {{
    position: absolute;
    /* column centers at 25%-7px and 75%+7px when gap is 28px */
    left: calc(25% - 7px);
    right: calc(25% - 7px);
    top: 20px;
    height: 1.6px;
    background: var(--gold);
  }}
  .fork-down-l,
  .fork-down-r {{
    position: absolute;
    top: 20px;
    width: 1.6px;
    height: 20px;
    background: var(--gold);
  }}
  .fork-down-l {{ left: calc(25% - 7px); }}
  .fork-down-r {{ right: calc(25% - 7px); }}

  .columns {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 28px;
    width: 100%;
    align-items: start;
  }}

  .floor {{
    background: rgba(20,24,32,0.88);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 22px;
    position: relative;
  }}
  .floor::before {{
    content: "";
    position: absolute;
    left: 22px;
    right: 22px;
    top: 0;
    height: 3px;
    border-radius: 0 0 2px 2px;
  }}
  .floor.dashboard::before {{ background: var(--dashboard); }}
  .floor.specialists::before {{ background: var(--specialists); }}

  .floor-head {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
  }}
  .floor-head .swatch {{
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex: none;
  }}
  .floor.dashboard .swatch {{ background: var(--dashboard); box-shadow: 0 0 8px var(--dashboard); }}
  .floor.specialists .swatch {{ background: var(--specialists); box-shadow: 0 0 8px var(--specialists); }}

  .floor h3 {{
    font-family: "Outfit", sans-serif;
    font-weight: 650;
    font-size: 15px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }}
  .floor.dashboard h3 {{ color: var(--dashboard); }}
  .floor.specialists h3 {{ color: var(--specialists); }}

  .floor-note {{
    margin-left: auto;
    font-size: 13px;
    color: var(--dim);
  }}

  .lead {{
    display: flex;
    gap: 14px;
    align-items: flex-start;
    background:
      linear-gradient(180deg, rgba(61,214,140,0.10), rgba(28,33,44,0.95));
    border: 1px solid rgba(61,214,140,0.32);
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 16px;
  }}
  .lead .bot-icon {{
    flex: none;
    width: 40px;
    height: 40px;
    border-radius: 9px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(61,214,140,0.14);
    color: var(--dashboard);
  }}
  .lead h4 {{
    font-family: "Outfit", sans-serif;
    font-weight: 650;
    font-size: 22px;
    letter-spacing: -0.02em;
    color: #fff;
    margin-bottom: 2px;
  }}
  .lead .role {{
    font-family: "Outfit", sans-serif;
    font-weight: 620;
    font-size: 12px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--dashboard);
    margin-bottom: 6px;
  }}
  .lead p.blurb {{
    font-size: 14.5px;
    line-height: 1.45;
    color: var(--muted);
  }}

  .members {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }}
  .member.dual {{
    grid-column: 1 / -1;
  }}

  .member {{
    background: var(--card-2);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 14px 16px;
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }}
  .member.dual {{
    border-color: rgba(255,159,67,0.45);
    background:
      linear-gradient(180deg, rgba(255,159,67,0.08), rgba(28,33,44,0.96));
  }}
  .member .bot-icon {{
    flex: none;
    width: 34px;
    height: 34px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(61,214,140,0.12);
    color: var(--dashboard);
  }}
  .member.dual .bot-icon {{
    background: rgba(255,159,67,0.14);
    color: var(--qc);
  }}
  .member h4 {{
    font-family: "Outfit", sans-serif;
    font-weight: 650;
    font-size: 17px;
    letter-spacing: -0.02em;
    color: #fff;
    margin-bottom: 2px;
  }}
  .member .role {{
    font-size: 13.5px;
    color: var(--muted);
  }}
  .dual-badge {{
    display: inline-flex;
    margin-top: 8px;
    font-family: "Outfit", sans-serif;
    font-weight: 650;
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--qc);
    background: rgba(255,159,67,0.12);
    border: 1px solid rgba(255,159,67,0.4);
    border-radius: 999px;
    padding: 4px 10px;
  }}

  .spec-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }}
  .specialist {{
    background: var(--card-2);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 13px 14px;
  }}
  .specialist h4 {{
    font-family: "Outfit", sans-serif;
    font-weight: 620;
    font-size: 16.5px;
    letter-spacing: -0.02em;
    color: #fff;
  }}

  .spec-footnote {{
    margin-top: 14px;
    font-size: 13.5px;
    line-height: 1.45;
    color: var(--dim);
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px dashed rgba(255,159,67,0.35);
    color: #E8D0B0;
  }}
  .spec-footnote strong {{
    color: var(--qc);
    font-weight: 600;
  }}

  footer {{
    margin-top: 32px;
    display: flex;
    justify-content: space-evenly;
    align-items: center;
    gap: 12px;
    background: rgba(20,24,32,0.88);
    border: 1px solid rgba(232,195,106,0.22);
    border-radius: 14px;
    padding: 14px 20px;
  }}
  .guard {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 14.5px;
    color: var(--muted);
    white-space: nowrap;
  }}
  .guard svg {{ color: var(--gold); flex: none; }}
  footer .guard + .guard {{
    border-left: 1px solid var(--line);
    padding-left: 18px;
  }}
</style>
</head>
<body>
  <div id="poster">
    <div class="frame"></div>
    <div class="inner">
      <header>
        <div class="kicker">{esc(org['kicker'])}</div>
        <h1>{esc(org['title'])}</h1>
        <p class="subtitle">{esc(org['subtitle'])}</p>
      </header>

      <div class="chain">
        <article class="human" id="{esc(ceo['id'])}">
          <div class="icon-wrap">{ICON_USER}</div>
          <div class="label">{esc(ceo['role'])} · human</div>
          <h2>{esc(ceo['name'])}</h2>
          <p>{esc(ceo.get('blurb') or '')}</p>
        </article>

        <div class="stem" aria-hidden="true"></div>

        <article class="router" id="{esc(router['id'])}">
          <div class="icon-wrap">{ICON_ROUTER}</div>
          <div class="label">{esc(router['role'])}</div>
          <h2>{esc(router['name'])}</h2>
          <p>{esc(router.get('blurb') or '')}</p>
        </article>

      </div>

      <div class="fork" aria-hidden="true">
        <div class="fork-v"></div>
        <div class="fork-h"></div>
        <div class="fork-down-l"></div>
        <div class="fork-down-r"></div>
      </div>

      <div class="columns">
        <section class="floor dashboard">
          <div class="floor-head">
            <span class="swatch"></span>
            <h3>{esc(team['name'])}</h3>
          </div>

          <article class="lead" id="{esc(lead['id'])}">
            <div class="bot-icon">{ICON_LEAD}</div>
            <div>
              <h4>{esc(lead['name'])}</h4>
              <div class="role">{esc(lead['role'])}</div>
              <p class="blurb">{esc(lead.get('blurb') or '')}</p>
            </div>
          </article>

          <div class="members">
            {''.join(member_cards)}
          </div>
        </section>

        <section class="floor specialists">
          <div class="floor-head">
            <span class="swatch"></span>
            <h3>{esc(specialists['name'])}</h3>
            <span class="floor-note">Report to CEO Bot</span>
          </div>
          <div class="spec-grid">
            {''.join(specialist_cards)}
          </div>
          <p class="spec-footnote"><strong>Tech Bot</strong> is shown once, on the Creator Dashboard team. It also reports to CEO Bot as a specialist.</p>
        </section>
      </div>

      <footer>
        {''.join(footer_items)}
      </footer>
    </div>
  </div>
</body>
</html>
"""


# --- Screenshot --------------------------------------------------------------

def find_chrome() -> str | None:
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def render_png() -> tuple[int, int]:
    chrome = find_chrome()
    launch_kwargs = {
        "args": ["--no-sandbox", "--disable-gpu", "--font-render-hinting=full"]
    }
    if chrome:
        launch_kwargs["executable_path"] = chrome

    html_url = "file://" + str(HTML_PATH)

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page(device_scale_factor=2)
        page.goto(html_url, wait_until="networkidle")
        page.evaluate("() => document.fonts.ready")
        page.wait_for_timeout(300)
        dims = page.evaluate(
            """() => {
              const el = document.getElementById('poster');
              const r = el.getBoundingClientRect();
              return {width: Math.ceil(r.width), height: Math.ceil(r.height)};
            }"""
        )
        page.set_viewport_size({"width": dims["width"], "height": dims["height"]})
        page.wait_for_timeout(200)
        page.locator("#poster").screenshot(path=str(PNG_PATH), type="png")
        browser.close()
    return dims["width"], dims["height"]


def maybe_compress(path: Path) -> None:
    size = path.stat().st_size
    if size <= MAX_PNG_BYTES:
        return
    im = Image.open(path)
    # Drop to a slightly smaller canvas if the raw capture is huge,
    # then recompress. Keep enough resolution for GitHub retina.
    max_w = 2800
    if im.width > max_w:
        h = int(im.height * (max_w / im.width))
        im = im.resize((max_w, h), Image.Resampling.LANCZOS)
    im.save(path, format="PNG", optimize=True)
    if path.stat().st_size > MAX_PNG_BYTES:
        # Last resort: palette quantize, still lossless-ish for this UI.
        im = im.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
        im.save(path, format="PNG", optimize=True)


def main() -> None:
    org = load_org()
    HTML_PATH.write_text(build_html(org))
    mermaid = build_mermaid(org)
    update_readme_mermaid(mermaid)
    css_w, css_h = render_png()
    maybe_compress(PNG_PATH)
    im = Image.open(PNG_PATH)
    print(f"wrote {HTML_PATH.name}")
    print(f"wrote {PNG_PATH.name}  css={css_w}x{css_h}  pixels={im.size}  bytes={PNG_PATH.stat().st_size}")
    print(f"updated mermaid in {README_PATH.name}")


if __name__ == "__main__":
    main()
