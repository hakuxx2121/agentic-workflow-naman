# Ticker mentions dashboard (v1, archived)

This is the previous dashboard. The live dashboard is the Ticker Timeline at the parent folder (`../index.html`).

Serve it from the **parent** folder so data paths resolve:

```bash
cd creator-calls-dashboard
./serve.sh
```

Then open http://localhost:8000/v1/

`js/config.js` points at `../data/mentions.json`, `../data/scores.json`, and `../data/insights.json` — the same data files the live dashboard uses. Do not run a server from inside this `v1/` folder, or those paths will fail.

A bullish call hits when the forward return is positive; a bearish call hits when it is negative. Calls without enough future bars are pending, not misses. Insights cards with n&lt;10 are flagged **too few calls to trust**. Non-significant results say **could be chance**.

You can list ticker symbols in `js/app.js` (`HOLDINGS`) to isolate them with the **My holdings** filter. This copy ships with an empty list.
