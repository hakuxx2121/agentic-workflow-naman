# Grok Bot company org chart

How the agent fleet in this portfolio is organized. Naman is CEO. **CEO Bot** is the primary router and reviewer. **Manager Bot** coordinates the Creator Dashboard team. Specialist bots report to CEO Bot. **Tech Bot** is shown once: it is on the Creator Dashboard team (infra) and also reports to CEO Bot as a specialist.
How Ticker Tracker's nightly fetch, the dashboard refresh, the PC data sync, and the on-demand backfill job fit together is in [pipelines.md](pipelines.md).

![Grok Bot company org chart](org-chart.png)

## How to update the chart

1. Edit the source file: [`org.yaml`](org.yaml).
2. From this folder, run:

   ```bash
   python3 render.py
   ```

   That regenerates `org-chart.html`, this README's Mermaid block, and the canonical image `org-chart.png`.

Do not hand-edit `org-chart.html` or the Mermaid block; they are generated from `org.yaml`. The PNG is the only canonical image used in the top-level README.

`render.py` needs Python 3, PyYAML, Playwright, and a Chromium/Chrome binary, plus the Outfit and Geist font files already in this folder.

## Mermaid (renders on GitHub)

<!-- ORG_MERMAID_START -->
```mermaid
flowchart TB
    naman["Naman — CEO (human)"]
    ceo_bot["CEO Bot — Primary router and reviewer"]
    naman --> ceo_bot

    subgraph dash["Creator Dashboard team"]
        direction TB
        manager_bot["Manager Bot — Team lead"]
        business_logic_writer["Business Logic Writer — Owns the spec"]
        graph_bot["Graph Bot — Builds the dashboard"]
        dashboard_qa["Dashboard QA — Tests"]
        github_bot["GitHub Bot — Publishes"]
        tech_bot["Tech Bot — Infra · also a specialist"]
        manager_bot --> business_logic_writer & graph_bot & dashboard_qa & github_bot & tech_bot
    end

    subgraph specs["Specialists"]
        direction TB
        job_bot["Job Bot"]
        car_bot["Car Bot"]
        vlog_editor_helper["Vlog Editor Helper"]
        recipe_bot["Recipe Bot"]
        tradingview_bot["TradingViewBot"]
        tv_bot["TV Bot"]
        ticker_tracker["Ticker Tracker"]
        three_tier["3-Tier Stock Check"]
        earnings_call_bot["Earnings Call Bot"]
        ndtl_gains["NDTL - Gains"]
        medical_advice["Medical Advice"]
        workout_bot["Workout Bot"]
    end

    ceo_bot --> manager_bot
    ceo_bot --> specs
    ceo_bot -.->|also a specialist| tech_bot
```
<!-- ORG_MERMAID_END -->

No secrets, webhook URLs, account details, holdings, or machine paths are in these files.
