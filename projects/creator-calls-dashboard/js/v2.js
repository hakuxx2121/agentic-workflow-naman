/* Creator Calls — Ticker Timeline. Reads ./data/*.json in the browser; no build step. */
(() => {
  "use strict";
  const cfg = Object.assign({
    dataUrl: "./data/mentions.json", scoresUrl: "./data/scores.json",
    insightsUrl: "./data/insights.json", pricesUrl: "./data/prices.json",
    // Example placeholder only. Replace with your own symbols, or use [].
    holdings: ["AAPL"],
  }, window.DASHBOARD_CONFIG || {});
  const DEFAULT_HOLDINGS = (cfg.holdings || ["AAPL"]).map((t) => String(t).trim().toUpperCase()).filter(Boolean);
  const LS_HOLD = "creatorCalls.holdings.v1";
  const LS_LEGEND = "creatorCalls.legend.v1";
  const LEGEND_KEYS = ["candles", "s20", "s50", "bullish", "bearish", "mixed", "flip"];
  const LEGEND_DEFAULT = { candles: true, s20: true, s50: true, bullish: true, bearish: true, mixed: true, flip: true };
  function loadHoldings() {
    try {
      const raw = localStorage.getItem(LS_HOLD);
      if (raw == null) return DEFAULT_HOLDINGS.slice();
      const arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return DEFAULT_HOLDINGS.slice();
      const out = [];
      arr.forEach((t) => { t = String(t || "").trim().toUpperCase(); if (t && !out.includes(t)) out.push(t); });
      return out;
    } catch (e) { return DEFAULT_HOLDINGS.slice(); }
  }
  function saveHoldings(list) {
    try { localStorage.setItem(LS_HOLD, JSON.stringify(list)); } catch (e) {}
  }
  function loadLegend() {
    try {
      const raw = localStorage.getItem(LS_LEGEND);
      if (raw == null) return { ...LEGEND_DEFAULT };
      const o = JSON.parse(raw);
      const out = { ...LEGEND_DEFAULT };
      LEGEND_KEYS.forEach((k) => { if (typeof o[k] === "boolean") out[k] = o[k]; });
      return out;
    } catch (e) { return { ...LEGEND_DEFAULT }; }
  }
  function saveLegend(leg) {
    try { localStorage.setItem(LS_LEGEND, JSON.stringify(leg)); } catch (e) {}
  }
  let HOLDINGS = loadHoldings();
  const SENT = ["bullish", "bearish", "mixed", "neutral", "unknown"];
  const COL = { bullish: "#3ecf8e", bearish: "#f06470", mixed: "#e0b34c", neutral: "#8a94a6", unknown: "#5f6a7d" };
  const GLYPH = { bullish: "▲", bearish: "▼", mixed: "◆", neutral: "●", unknown: "·" };
  const TAG_LABEL = { ahead: "ahead of move", after: "after the move", no_follow_through: "no follow-through", pending: "pending", no_price: "no price data" };
  const SHORT_TAG = { ahead: "ahead", after: "after", no_follow_through: "no follow", pending: "pending", no_price: "no price" };
  const FLIP = "#f5c451";
  let THIN = 10;

  const state = {
    mentions: [], scores: null, insights: null, prices: null, pricesErr: null,
    from: "", to: "", minDate: "", maxDate: "", channel: "", ticker: "", sentiment: "",
    holdings: false, basis: "raw", tab: "timeline", focus: null, search: "",
    legend: loadLegend(),
    sort: { key: "date", dir: -1 }, scoreSort: { key: "date", dir: -1 }, splitSort: { key: "n5", dir: -1 },
  };
  const charts = {};
  const SMA20 = "#4ea1ff", SMA50 = "#b07cff";
  const MARK_SCALE = 0.6;
  const lw = { chart: null, candles: null, s20: null, s50: null, bars: [], barIdx: {}, skipLogged: false };

  /* ---------- helpers ---------- */
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (x, d = 0) => (x == null || Number.isNaN(x)) ? "—" : `${(x * 100).toFixed(d)}%`;
  const spct = (x, d = 1) => (x == null || Number.isNaN(x)) ? "—" : `${x > 0 ? "+" : ""}${(x * 100).toFixed(d)}%`;
  const uniq = (a) => Array.from(new Set(a)).sort((x, y) => x.localeCompare(y));
  const isHold = (t) => HOLDINGS.includes(t);
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const fmtD = (d) => { if (!d) return "—"; const [, m, dd] = d.split("-"); return `${MON[+m - 1]} ${+dd}`; };
  const spy = () => state.basis === "spy";

  function status(msg, err) {
    const el = $("status");
    if (!msg) { el.hidden = true; return; }
    el.hidden = false; el.textContent = msg; el.classList.toggle("error", !!err);
  }
  async function fetchJson(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${url}`);
    return r.json();
  }
  function retCell(x, pending, extra = "") {
    if (pending) return `<span class="pending">pending</span>`;
    if (x == null) return `<span class="dim" title="missing data">—</span>`;
    const cls = x > 0 ? "pos" : x < 0 ? "neg" : "";
    return `<span class="${cls}">${spct(x)}</span>${extra}`;
  }
  function hitGlyph(c, key, pendKey) {
    if (!c.directional) return "";
    if (c[pendKey] || c[key] == null) return "";
    return c[key] ? ` <span class="pos" title="call was right">✓</span>` : ` <span class="neg" title="call was wrong">✗</span>`;
  }
  function hitCell(v, pending, directional = true) {
    if (!directional) return `<span class="dim">not scored</span>`;
    if (pending) return `<span class="pending">pending</span>`;
    if (v == null) return `<span class="dim">—</span>`;
    return v ? `<span class="pos">✓ hit</span>` : `<span class="neg">✗ miss</span>`;
  }
  const sentBadge = (s, flip) => `<span class="sent ${SENT.includes(s) ? s : "unknown"}">${GLYPH[s] || "·"} ${esc(s || "—")}</span>${flip ? `<span class="flipmark" title="flip: ${esc(TAG_LABEL[flip] || flip)}">⟲</span>` : ""}`;
  const tickerCell = (t) => `<b>${esc(t)}</b>${isHold(t) ? '<span class="held">★ held</span>' : ""}`;
  const link = (u, txt = "Watch") => u ? `<a href="${esc(u)}" target="_blank" rel="noreferrer">${txt}</a>` : "—";
  function maBadge(c) {
    const b = (v, n) => v == null ? `<span class="ma na" title="not enough history for the ${n}-day average">${n} ?</span>`
      : `<span class="ma ${v ? "up" : "dn"}" title="price was ${v ? "above" : "below"} its ${n}-day average at the call">${n}${v ? "▲" : "▼"}</span>`;
    if (!c.has_price) return `<span class="dim">no price</span>`;
    return b(c.above_sma20, 20) + b(c.above_sma50, 50);
  }
  function rate(rows, key) {
    const xs = rows.filter((c) => c[key] != null);
    return { r: xs.length ? xs.filter((c) => c[key]).length / xs.length : null, n: xs.length, k: xs.filter((c) => c[key]).length };
  }
  const thinBadge = (n) => n < THIN ? ` <span class="thin" title="fewer than ${THIN} scored calls">too few to trust</span>` : "";
  const rateTxt = (o) => o.n ? `${pct(o.r)} <span class="dim">(n=${o.n})</span>` : `<span class="dim">n=0</span>`;

  /* ---------- filters ---------- */
  function inFilters(row, { ignoreTicker = false, ignoreSent = false } = {}) {
    if (state.from && row.date && row.date < state.from) return false;
    if (state.to && row.date && row.date > state.to) return false;
    if (state.channel && row.channel !== state.channel) return false;
    if (!ignoreSent && state.sentiment && row.sentiment !== state.sentiment) return false;
    if (state.holdings && !isHold(row.ticker)) return false;
    if (!ignoreTicker && state.ticker && row.ticker !== state.ticker) return false;
    return true;
  }
  const allCalls = () => (state.scores && Array.isArray(state.scores.calls)) ? state.scores.calls : [];
  const fCalls = (o) => allCalls().filter((c) => inFilters(c, o));
  /* scored subsets, honoring the Raw / vs SPY basis */
  function scored(rows) {
    const d = rows.filter((c) => c.directional);
    return {
      d,
      h5: spy() ? rate(d.filter((c) => !c.pending_5d && c.ex_5d != null), "hit_5d_spy") : rate(d.filter((c) => !c.pending_5d), "hit_5d"),
      h1: spy() ? rate(d.filter((c) => !c.pending_1d && c.ex_1d != null), "hit_1d_spy") : rate(d.filter((c) => !c.pending_1d), "hit_1d"),
      hs: rate(d.filter((c) => !c.pending_5d && c.ex_5d != null), "hit_5d_spy"),
      ht: spy() ? rate(d.filter((c) => !c.pending_td && c.ex_td != null), "hit_td_spy") : rate(d.filter((c) => !c.pending_td), "hit_td"),
      pending: d.filter((c) => c.pending_5d).length,
    };
  }

  /* ---------- prices ---------- */
  const barsOf = (t) => (state.prices && state.prices.bars && state.prices.bars[t]) || null;
  function smaLine(bars, n) {
    const out = []; let sum = 0;
    for (let i = 0; i < bars.length; i++) {
      sum += bars[i].close; if (i >= n) sum -= bars[i - n].close;
      if (i >= n - 1) out.push({ time: bars[i].date, value: sum / n });
    }
    return out;
  }
  function chg(bars, k = 5) { return bars && bars.length > k ? bars[bars.length - 1].close / bars[bars.length - 1 - k].close - 1 : null; }
  function spark(vals, w = 76, h = 22) {
    if (!vals || vals.length < 2) return `<span class="dim" style="font-size:10px">no price data</span>`;
    const mn = Math.min(...vals), mx = Math.max(...vals), r = mx - mn || 1;
    const col = vals[vals.length - 1] >= vals[0] ? COL.bullish : COL.bearish;
    const pts = vals.map((v, i) => `${(i / (vals.length - 1) * w).toFixed(1)},${(h - 2 - (v - mn) / r * (h - 4)).toFixed(1)}`).join(" ");
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${col}" stroke-width="1.3" points="${pts}"/></svg>`;
  }

  /* ---------- timeline: ticker list ---------- */
  function tickerRows() {
    const src = allCalls().length ? allCalls() : state.mentions;
    const m = new Map();
    src.filter((c) => inFilters(c, { ignoreTicker: true, ignoreSent: true })).forEach((c) => {
      if (state.ticker && c.ticker !== state.ticker) return;
      if (!m.has(c.ticker)) m.set(c.ticker, { t: c.ticker, n: 0, bull: 0, bear: 0, flips: 0 });
      const r = m.get(c.ticker); r.n++;
      if (c.sentiment === "bullish") r.bull++; else if (c.sentiment === "bearish") r.bear++;
      if (c.is_flip) r.flips++;
    });
    return Array.from(m.values()).sort((a, b) => b.n - a.n || a.t.localeCompare(b.t));
  }
  function renderList() {
    const rows = tickerRows();
    if (state.ticker) state.focus = state.ticker;
    if (!state.focus || !rows.some((r) => r.t === state.focus)) {
      const first = rows.find((r) => barsOf(r.t)) || rows[0];
      state.focus = first ? first.t : null;
    }
    const q = state.search.trim().toUpperCase();
    const shown = q ? rows.filter((r) => r.t.includes(q)) : rows;
    $("tlist").innerHTML = shown.map((r) => {
      const b = barsOf(r.t);
      const c5 = chg(b);
      const tot = r.bull + r.bear;
      return `<div class="titem${r.t === state.focus ? " sel" : ""}" data-t="${esc(r.t)}" role="button" tabindex="0">
        <div><span class="tk">${esc(r.t)}${isHold(r.t) ? '<span class="star" title="in My holdings">★</span>' : ""}</span>
          <div class="meta">${r.n} mention${r.n === 1 ? "" : "s"}${r.flips ? ` · <span style="color:#f5c451" title="flips">⟲${r.flips}</span>` : ""}</div></div>
        <div class="sp">${spark(b ? b.slice(-30).map((x) => x.close) : null)}<div class="chg ${c5 > 0 ? "pos" : c5 < 0 ? "neg" : "dim"}">${c5 == null ? "" : spct(c5)}</div></div>
        <div class="row2"><span class="pos">▲${r.bull}</span><span class="split">${tot ? `<i class="b" style="width:${r.bull / tot * 100}%"></i><i class="s" style="width:${r.bear / tot * 100}%"></i>` : ""}</span><span class="neg">▼${r.bear}</span></div>
      </div>`;
    }).join("") || `<p class="caption">No tickers match.</p>`;
  }

  /* ---------- timeline: chart ---------- */
  function ensureChart() {
    if (lw.chart || typeof LightweightCharts === "undefined") return;
    const L = LightweightCharts;
    lw.chart = L.createChart($("chart"), {
      autoSize: true,
      layout: { background: { type: "solid", color: "transparent" }, textColor: "#8b95a8", fontSize: 11, attributionLogo: true,
        fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif' },
      grid: { vertLines: { visible: false }, horzLines: { color: "rgba(255,255,255,0.045)" } },
      rightPriceScale: { borderColor: "#232a37", scaleMargins: { top: 0.12, bottom: 0.12 }, autoScale: true },
      timeScale: { borderColor: "#232a37", rightOffset: 4, fixLeftEdge: false, fixRightEdge: false },
      crosshair: { horzLine: { color: "#3a4356", labelBackgroundColor: "#232a37" }, vertLine: { color: "#3a4356", labelBackgroundColor: "#232a37" } },
    });
    lw.chart.timeScale().subscribeVisibleLogicalRangeChange(() => requestAnimationFrame(drawOverlays));
    new ResizeObserver(() => requestAnimationFrame(drawOverlays)).observe($("chart"));
    startOverlayWatch();
  }
  function mappingKey() {
    if (!lw.chart || !lw.candles || !lw.bars.length) return "empty";
    try {
      const ts = lw.chart.timeScale();
      const ps = lw.chart.priceScale("right");
      const vr = ts.getVisibleLogicalRange();
      const pr = ps && ps.getVisibleRange && ps.getVisibleRange();
      const pane = lw.chart.paneSize ? lw.chart.paneSize(0) : { width: ts.width(), height: 0 };
      const mid = lw.bars[Math.min(lw.bars.length - 1, Math.max(0, Math.round((vr && vr.from) || 0)))];
      const last = lw.bars[lw.bars.length - 1];
      const x = (d) => { const v = ts.timeToCoordinate(d); return v == null ? "n" : v.toFixed(2); };
      const y = (price) => { const v = priceCoord(price); return v == null ? "n" : v.toFixed(2); };
      return [
        pane.width, pane.height, ts.width(),
        vr ? vr.from : "", vr ? vr.to : "",
        pr ? pr.from : "", pr ? pr.to : "",
        mid ? x(mid.date) : "", last ? x(last.date) : "",
        mid ? y(mid.high) : "", mid ? y(mid.low) : "", last ? y(last.close) : "",
        state.legend.candles, state.legend.s20, state.legend.s50,
        state.legend.bullish, state.legend.bearish, state.legend.mixed, state.legend.flip,
        state.focus, (lw.chartMarks || []).length,
      ].join("|");
    } catch (e) { return "err"; }
  }
  function startOverlayWatch() {
    if (lw.overlayWatch) return;
    lw.overlayWatch = true;
    const tick = () => {
      if (!lw.overlayWatch) return;
      requestAnimationFrame(tick);
      if (document.hidden) return;
      if (state.tab && state.tab !== "timeline") return;
      const key = mappingKey();
      if (key !== lw.mapKey) {
        lw.mapKey = key;
        drawOverlays();
      }
    };
    requestAnimationFrame(tick);
  }
  function viewSnapshot() {
    if (!lw.chart) return null;
    const ts = lw.chart.timeScale();
    const ps = lw.chart.priceScale("right");
    let auto = true, pr = null;
    try { auto = !!(ps.options() && ps.options().autoScale); } catch (e) {}
    try { pr = ps.getVisibleRange ? ps.getVisibleRange() : null; } catch (e) {}
    return {
      vr: ts.getVisibleLogicalRange(),
      pr: pr && pr.from != null && pr.to != null ? { from: pr.from, to: pr.to } : null,
      auto,
    };
  }
  function restoreView(snap) {
    if (!lw.chart || !snap) return;
    const ts = lw.chart.timeScale();
    if (snap.vr) {
      try { ts.setVisibleLogicalRange({ from: snap.vr.from, to: snap.vr.to }); } catch (e) {}
    }
    if (!snap.auto && snap.pr) {
      try { lw.chart.priceScale("right").setVisibleRange({ from: snap.pr.from, to: snap.pr.to }); } catch (e) {}
    }
  }
  function dropSeries() {
    if (!lw.chart) return;
    for (const k of ["s20", "s50", "candles"]) {
      if (lw[k]) { try { lw.chart.removeSeries(lw[k]); } catch (e) {} lw[k] = null; }
    }
  }
  function scaleIf(layer) {
    return (original) => (state.legend[layer] ? original() : null);
  }
  function attachSeries() {
    if (!lw.chart || typeof LightweightCharts === "undefined") return;
    const L = LightweightCharts;
    const common = { priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
    const solid = L.LineStyle.Solid;
    lw.s50 = lw.chart.addSeries(L.LineSeries, { ...common, color: SMA50, lineWidth: 2, lineStyle: solid, visible: !!state.legend.s50, autoscaleInfoProvider: scaleIf("s50") });
    lw.s20 = lw.chart.addSeries(L.LineSeries, { ...common, color: SMA20, lineWidth: 2, lineStyle: solid, visible: !!state.legend.s20, autoscaleInfoProvider: scaleIf("s20") });
    lw.candles = lw.chart.addSeries(L.CandlestickSeries, {
      upColor: COL.bullish, downColor: COL.bearish,
      borderUpColor: COL.bullish, borderDownColor: COL.bearish,
      wickUpColor: COL.bullish, wickDownColor: COL.bearish,
      priceLineVisible: false, lastValueVisible: true,
      visible: !!state.legend.candles,
      autoscaleInfoProvider: scaleIf("candles"),
    });
  }
  function setLegendSeries() {
    if (lw.s20) lw.s20.applyOptions({ visible: !!state.legend.s20 });
    if (lw.s50) lw.s50.applyOptions({ visible: !!state.legend.s50 });
    if (lw.candles) lw.candles.applyOptions({ visible: !!state.legend.candles });
    syncLegendButtons();
  }
  function applyLegendVisibility() {
    // Keep the user's time range and any hand-set price scale (I7-VIEW-01).
    const snap = viewSnapshot();
    setLegendSeries();
    restoreView(snap);
    requestAnimationFrame(() => {
      restoreView(snap);
      lw.mapKey = mappingKey();
      drawOverlays();
    });
  }
  function syncLegendButtons() {
    document.querySelectorAll("#chart-legend .leg-btn").forEach((b) => {
      const on = !!state.legend[b.dataset.layer];
      b.setAttribute("aria-pressed", String(on));
    });
  }
  function candleData(bars) {
    const out = [];
    let skipped = 0;
    for (const b of bars) {
      const o = b.open, h = b.high, l = b.low, c = b.close;
      if (![o, h, l, c].every((x) => typeof x === "number" && Number.isFinite(x))) { skipped++; continue; }
      out.push({ time: b.date, open: o, high: h, low: l, close: c });
    }
    if (skipped && !lw.skipLogged) {
      console.info(`Skipped ${skipped} price bar(s) missing open, high or low`);
      lw.skipLogged = true;
    }
    return out;
  }
  function priceCoord(price) {
    return lw.candles ? lw.candles.priceToCoordinate(price) : null;
  }
  function enableAutoScale() {
    if (!lw.chart) return;
    try { lw.chart.priceScale("right").applyOptions({ autoScale: true, scaleMargins: { top: 0.12, bottom: 0.12 } }); } catch (e) {}
    if (lw.candles) { try { lw.candles.priceScale().applyOptions({ autoScale: true }); } catch (e) {} }
  }
  function snapDate(c) {
    // the bar on or before the video date (what the creator could see)
    if (c.price_asof_date && lw.barIdx[c.price_asof_date] != null) return c.price_asof_date;
    return null;
  }
  function focusCalls() { return fCalls({ ignoreTicker: true }).filter((c) => c.ticker === state.focus); }

  function renderFocus() {
    closeCallPop();
    const t = state.focus;
    const calls = focusCalls();
    const all = allCalls().filter((c) => c.ticker === t && inFilters(c, { ignoreTicker: true, ignoreSent: true }));
    const bars = barsOf(t) || [];
    lw.bars = bars; lw.barIdx = {}; bars.forEach((b, i) => { lw.barIdx[b.date] = i; });
    const sc = scored(calls);
    const creators = uniq(all.map((c) => c.channel));
    const flips = calls.filter((c) => c.is_flip);
    const last = bars.length ? bars[bars.length - 1] : null;
    const c5 = chg(bars);
    $("focus-head").innerHTML = t ? `
      <span class="sym">${esc(t)}${isHold(t) ? ' <span class="held">★ held</span>' : ""}</span>
      ${last ? `<span class="px">$${last.close.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
        <span class="${c5 > 0 ? "pos" : "neg"}">${spct(c5)} last 5 sessions</span><span class="dim">close ${fmtD(last.date)}</span>`
        : `<span class="thin">no price data for this ticker</span>`}
      <div class="fstats">
        <div class="fstat"><div class="v">${calls.length}</div><div class="l">mentions</div></div>
        <div class="fstat"><div class="v"><span class="pos">▲${sc.d.filter((c) => c.sentiment === "bullish").length}</span> / <span class="neg">▼${sc.d.filter((c) => c.sentiment === "bearish").length}</span></div><div class="l">bullish / bearish calls</div></div>
        <div class="fstat"><div class="v">${pct(sc.h5.r)}</div><div class="l">5-session hit rate${spy() ? " vs SPY" : ""} (n=${sc.h5.n})${thinBadge(sc.h5.n)}</div></div>
        <div class="fstat"><div class="v">${sc.pending}</div><div class="l">pending, not misses</div></div>
        <div class="fstat"><div class="v">${flips.length}</div><div class="l">flips</div></div>
        <div class="fstat"><div class="v">${creators.length}</div><div class="l">creators</div></div>
      </div>` : `<span class="caption">No ticker in the current filters.</span>`;
    $("calls-title").textContent = t ? `${t} calls (${calls.length})` : "Calls";

    ensureChart();
    if (lw.chart) {
      // Always drop and rebuild series so a prior zoom or price-scale drag cannot stick.
      dropSeries();
      attachSeries();
      if (!bars.length) {
        lw.s20.setData([]); lw.s50.setData([]); lw.candles.setData([]);
        lw.chartMarks = [];
        setLegendSeries();
      } else {
        lw.candles.setData(candleData(bars));
        lw.s20.setData(smaLine(bars, 20));
        lw.s50.setData(smaLine(bars, 50));
        setLegendSeries();
        const agg = new Map();
        calls.filter((c) => c.sentiment === "bullish" || c.sentiment === "bearish" || c.sentiment === "mixed").forEach((c) => {
          const d = snapDate(c); if (!d) return;
          const k = `${d}|${c.sentiment}`; agg.set(k, (agg.get(k) || 0) + 1);
        });
        lw.chartMarks = Array.from(agg.entries()).map(([k, n]) => {
          const [d, s] = k.split("|");
          return { date: d, sentiment: s, n };
        }).sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : (a.sentiment < b.sentiment ? -1 : 1));
        const dates = calls.map((c) => snapDate(c)).filter(Boolean).sort();
        const fi = dates.length && dates[0] in lw.barIdx ? lw.barIdx[dates[0]] : Math.max(0, bars.length - 40);
        const fromIdx = Math.max(0, fi - 20);
        const ts = lw.chart.timeScale();
        const applyView = () => {
          if (!lw.chart) return;
          enableAutoScale();
          const vr = ts.getVisibleLogicalRange();
          if (!vr) return;
          const x0 = ts.timeToCoordinate(bars[fromIdx].date);
          const minPad = 24;
          if (x0 != null && x0 < minPad) {
            const plotW = ts.width() || 1;
            const barPx = plotW / Math.max(0.001, vr.to - vr.from);
            ts.setVisibleLogicalRange({ from: vr.from - (minPad - Math.max(0, x0)) / barPx, to: vr.to });
          }
        };
        enableAutoScale();
        ts.setVisibleLogicalRange({ from: fromIdx - 0.6, to: bars.length - 1 + 0.2 });
        requestAnimationFrame(() => { applyView(); requestAnimationFrame(() => { applyView(); drawOverlays(); }); });
      }
    }
    const miss = calls.filter((c) => !c.has_price).length;
    $("chart-note").textContent = !bars.length ? `No daily prices for ${t || "this ticker"} (feed has none), so no chart or returns. Calls are still listed.`
      : miss ? `${miss} call(s) have no price data and are not plotted.` : "";
    renderCallsTable(calls);
    requestAnimationFrame(drawOverlays);
  }

  function xOf(date, plotW, range) {
    if (lw.bars.length && lw.chart) {
      // snap to the bar on or before the date
      let d = date;
      if (lw.barIdx[d] == null) {
        const prior = lw.bars.filter((b) => b.date <= date); if (!prior.length) return null; d = prior[prior.length - 1].date;
      }
      return lw.chart.timeScale().timeToCoordinate(d);
    }
    if (!range) return null;
    const a = Date.parse(range[0]), b = Date.parse(range[1]);
    return b > a ? 30 + (Date.parse(date) - a) / (b - a) * (plotW - 60) : plotW / 2;
  }

  function laneTipText(c) {
    const bits = [c.channel, fmtD(c.date), c.sentiment];
    if (c.is_flip && c.flip_tag) bits.push(TAG_LABEL[c.flip_tag] || c.flip_tag);
    return bits.filter(Boolean).join(" · ");
  }
  function stripAxisTicks() {
    if (!lw.chart || !lw.bars.length) return [];
    const ts = lw.chart.timeScale();
    const vr = ts.getVisibleRange();
    if (!vr) return [];
    const vis = lw.bars.filter((b) => b.date >= vr.from && b.date <= vr.to);
    if (!vis.length) return [];
    const xOfBar = (b) => ts.timeToCoordinate(b.date);
    const x0 = xOfBar(vis[0]), x1 = xOfBar(vis[vis.length - 1]);
    if (x0 == null || x1 == null) return [];
    const minPx = 64;
    const maxN = Math.max(2, Math.floor(Math.abs(x1 - x0) / minPx) + 1);
    const n = Math.min(vis.length, maxN);
    const idxs = [];
    if (n <= 1) idxs.push(0);
    else {
      for (let k = 0; k < n; k++) idxs.push(Math.round(k * (vis.length - 1) / (n - 1)));
    }
    const seen = new Set();
    const ticks = [];
    idxs.forEach((i) => {
      if (seen.has(i)) return; seen.add(i);
      const b = vis[i];
      const x = xOfBar(b);
      if (x == null) return;
      const day = +b.date.slice(8, 10);
      const mon = MON[+b.date.slice(5, 7) - 1];
      ticks.push({ date: b.date, x, label: day === 1 ? mon : `${mon} ${day}` });
    });
    return ticks;
  }
  function axisLabelAnchor(x, plotW) {
    if (x < 18) return { anchor: "start", x: Math.max(0, x) };
    if (x > plotW - 18) return { anchor: "end", x: Math.min(plotW, x) };
    return { anchor: "middle", x };
  }
  function arrowPath(up, h) {
    const w = h * 0.72, stem = h * 0.28, head = h * 0.55;
    if (up) return `M 0 ${-h} L ${-w} ${-h + head} L ${-stem} ${-h + head} L ${-stem} ${0} L ${stem} ${0} L ${stem} ${-h + head} L ${w} ${-h + head} Z`;
    return `M 0 ${h} L ${-w} ${h - head} L ${-stem} ${h - head} L ${-stem} ${0} L ${stem} ${0} L ${stem} ${h - head} L ${w} ${h - head} Z`;
  }
  function diamondPath(h) {
    const s = h / 2;
    return `M 0 ${-s} L ${s} 0 L 0 ${s} L ${-s} 0 Z`;
  }
  function drawOverlays() {
    const svg = $("chart-overlay"), lanes = $("lanes-svg"), axisSvg = $("lane-axis-svg");
    const clearAxis = () => { if (axisSvg) { axisSvg.innerHTML = ""; axisSvg.removeAttribute("width"); } };
    if (!state.focus) { svg.innerHTML = ""; lanes.innerHTML = ""; clearAxis(); hideLaneTip(); return; }
    const calls = focusCalls();
    const plotW = lw.chart ? lw.chart.timeScale().width() : $("lanes").clientWidth;
    const chartW = $("chart") ? $("chart").clientWidth : plotW;
    let overlay = "";
    const markH = 12 * MARK_SCALE;
    const ringR = 9 * MARK_SCALE;
    if (lw.chart && lw.bars.length && lw.candles) {
      const ts = lw.chart.timeScale();
      const GAP = 6, STACK = 3, labPx = 8;
      const pane = (lw.chart.paneSize ? lw.chart.paneSize(0) : null) || { width: plotW, height: ($("chart") && $("chart").clientHeight) || 0 };
      const paneH = pane.height || 0;
      overlay += `<defs><clipPath id="plot-clip"><rect x="0" y="0" width="${plotW}" height="${paneH}"></rect></clipPath></defs>`;
      overlay += `<g clip-path="url(#plot-clip)">`;
      const vr = ts.getVisibleLogicalRange();
      const barW = (vr && Number.isFinite(vr.to - vr.from) && (vr.to - vr.from) !== 0)
        ? Math.abs((ts.width() || plotW) / (vr.to - vr.from)) : 6;
      const visBars = new Set();
      (lw.chartMarks || []).forEach((m) => { if (state.legend[m.sentiment]) visBars.add(m.date); });
      visBars.forEach((date) => {
        const i = lw.barIdx[date]; if (i == null) return;
        const b = lw.bars[i];
        const x = ts.timeToCoordinate(date);
        const hy = priceCoord(b.high), ly = priceCoord(b.low), oy = priceCoord(b.open), cy = priceCoord(b.close);
        if (x == null || hy == null || ly == null) return;
        const top = Math.min(hy, ly), h = Math.abs(ly - hy) || 1;
        overlay += `<rect class="chart-candle-box" data-date="${esc(date)}" x="${x - barW / 2}" y="${top}" width="${barW}" height="${h}" fill="none" pointer-events="none"/>`;
        if (oy != null && cy != null) {
          const bt = Math.min(oy, cy), bh = Math.abs(cy - oy) || 1;
          const bodyW = Math.max(1, barW * 0.7);
          overlay += `<rect class="chart-candle-body" data-date="${esc(date)}" x="${x - bodyW / 2}" y="${bt}" width="${bodyW}" height="${bh}" fill="none" pointer-events="none"/>`;
        }
      });
      const byDate = new Map();
      (lw.chartMarks || []).forEach((m) => {
        if (!state.legend[m.sentiment]) return;
        if (!byDate.has(m.date)) byDate.set(m.date, {});
        byDate.get(m.date)[m.sentiment] = m;
      });
      const addMark = (m, x, wickY, originY, tipLocalY, path, hitCy, labelY) => {
        const tipY = originY + tipLocalY;
        const gap = Math.abs(tipY - wickY);
        const label = m.n > 1 ? `${GLYPH[m.sentiment]}${m.n}` : "";
        overlay += `<g class="chart-mark" tabindex="0" role="button" data-kind="${esc(m.sentiment)}" data-date="${esc(m.date)}" data-n="${m.n}" data-gap="${gap.toFixed(2)}" data-bar-x="${x}" data-wick-y="${wickY}" data-tip-y="${tipY}" transform="translate(${x},${originY})">`;
        overlay += `<circle r="11" cx="0" cy="${hitCy}" fill="transparent"/>`;
        overlay += `<path class="chart-mark-shape" d="${path}" fill="${COL[m.sentiment]}"></path>`;
        if (label) overlay += `<text x="0" y="${labelY}" text-anchor="middle" font-size="8" fill="${COL[m.sentiment]}">${esc(label)}</text>`;
        overlay += `</g>`;
        overlay += `<line class="chart-mark-tip" data-kind="${esc(m.sentiment)}" data-date="${esc(m.date)}" x1="${x}" x2="${x}" y1="${tipY}" y2="${tipY}"/>`;
        overlay += `<line class="chart-wick-end" data-kind="${esc(m.sentiment)}" data-date="${esc(m.date)}" x1="${x}" x2="${x}" y1="${wickY}" y2="${wickY}"/>`;
        return gap;
      };
      byDate.forEach((kinds, date) => {
        const i = lw.barIdx[date]; if (i == null) return;
        const b = lw.bars[i];
        const x = ts.timeToCoordinate(date);
        if (x == null || x < -8 || x > plotW + 8) return;
        const lowY = priceCoord(b.low), highY = priceCoord(b.high);
        // Below the low: bullish. Tip 6px under the wick.
        if (kinds.bullish && lowY != null) {
          const m = kinds.bullish;
          const tipLocal = -markH;
          const originY = (lowY + GAP) - tipLocal;
          const hitCy = tipLocal + 11; // entirely on the far side of the tip
          addMark(m, x, lowY, originY, tipLocal, arrowPath(true, markH), hitCy, 9);
        }
        // Above the high: bearish first (nearest), then mixed beyond it.
        let aboveClear = (highY != null) ? highY - GAP : null; // y of the next available tip (or diamond near-edge)
        if (kinds.bearish && highY != null) {
          const m = kinds.bearish;
          const tipLocal = markH;
          const originY = (highY - GAP) - tipLocal;
          const hitCy = tipLocal - 11;
          addMark(m, x, highY, originY, tipLocal, arrowPath(false, markH), hitCy, -4);
          // extent away from the candle: path base at originY, label further up
          const labelTop = m.n > 1 ? (originY - 4 - labPx) : originY;
          aboveClear = Math.min(originY, labelTop) - STACK;
        }
        if (kinds.mixed && highY != null) {
          const m = kinds.mixed;
          const s = markH / 2; // bottom vertex at +s, top at -s
          const tipLocal = s; // nearest-to-wick vertex
          const desiredTip = (kinds.bearish && aboveClear != null) ? aboveClear : (highY - GAP);
          const originY = desiredTip - tipLocal;
          const hitCy = tipLocal - 11;
          addMark(m, x, highY, originY, tipLocal, diamondPath(markH), hitCy, -(s + 5));
        }
      });
      if (state.legend.flip) {
        const seen = new Set();
        calls.filter((c) => c.is_flip).forEach((c) => {
          const d = snapDate(c); if (!d || seen.has(d)) return; seen.add(d);
          const i = lw.barIdx[d]; if (i == null) return;
          const x = ts.timeToCoordinate(d);
          const y = priceCoord(lw.bars[i].close);
          if (x == null || y == null || x < 0 || x > plotW) return;
          overlay += `<g class="chart-flip-ring" tabindex="0" role="button" data-kind="flip" data-date="${esc(d)}" transform="translate(${x},${y})">`;
          overlay += `<circle r="11" fill="transparent"/>`;
          overlay += `<circle r="${ringR}" fill="none" stroke="${FLIP}" stroke-width="1.2"/>`;
          overlay += `</g>`;
        });
      }
      overlay += `</g>`;
    }
    svg.innerHTML = overlay;
    const byCh = new Map();
    calls.slice().sort((a, b) => (a.date || "").localeCompare(b.date || "") || a.i - b.i).forEach((c) => {
      if (!c.date) return;
      if (!byCh.has(c.channel)) byCh.set(c.channel, []);
      byCh.get(c.channel).push(c);
    });
    const chans = Array.from(byCh.keys()).sort((a, b) => byCh.get(b).length - byCh.get(a).length || a.localeCompare(b));
    const sparse = calls.length <= 3;
    const rowH = sparse ? 44 : 40;
    const top = 6;
    const ds = calls.map((c) => c.date).filter(Boolean).sort();
    const range = ds.length ? [ds[0], ds[ds.length - 1]] : null;
    let out = "";
    chans.forEach((ch, r) => {
      const y = top + r * rowH + (sparse ? 18 : 22);
      out += `<text x="2" y="${y - 12}" fill="#8b95a8" font-size="11">${esc(ch)} <tspan fill="#5f6a7d">(${byCh.get(ch).length})</tspan></text>`;
      out += `<line class="lane-base" x1="0" x2="${plotW}" y1="${y}" y2="${y}" stroke="${sparse ? "#455266" : "#2a3344"}" stroke-width="1"/>`;
      const pts = byCh.get(ch).map((c) => ({ c, x: xOf(c.date, plotW, range) })).filter((p) => p.x != null);
      pts.forEach((p, k) => {
        if (k + 1 >= pts.length) return;
        const x0 = Math.max(0, Math.min(plotW, p.x)), x1 = Math.max(0, Math.min(plotW, pts[k + 1].x));
        if (x1 > x0) out += `<line x1="${x0}" x2="${x1}" y1="${y}" y2="${y}" stroke="${COL[p.c.sentiment] || COL.unknown}" stroke-width="3" stroke-opacity="0.55"/>`;
      });
      pts.forEach((p) => {
        if (p.x < -8 || p.x > plotW + 8) return;
        const s = p.c.sentiment;
        const tip = laneTipText(p.c);
        out += `<g class="lane-mark" tabindex="0" role="img" data-tip="${esc(tip)}" transform="translate(${p.x},${y})">`;
        out += `<circle r="11" fill="transparent"/>`;
        out += `<text text-anchor="middle" dominant-baseline="central" font-size="16" fill="${COL[s] || COL.unknown}">${GLYPH[s] || "·"}</text>`;
        if (p.c.is_flip) out += `<circle r="10" fill="none" stroke="${FLIP}" stroke-width="1.6"/>`;
        out += `</g>`;
        if (sparse) {
          const lab = fmtD(p.c.date);
          const a = axisLabelAnchor(p.x, plotW);
          out += `<text class="lane-date" x="${a.x}" y="${y + 18}" text-anchor="${a.anchor}" font-size="10" fill="#8b95a8">${esc(lab)}</text>`;
        }
      });
    });
    const contentBottom = top + Math.max(chans.length, 1) * rowH + (sparse ? 6 : 2);
    lanes.setAttribute("width", String(chartW));
    lanes.setAttribute("height", String(contentBottom));
    lanes.setAttribute("viewBox", `0 0 ${chartW} ${contentBottom}`);
    lanes.style.width = chartW + "px";
    lanes.style.height = contentBottom + "px";
    lanes.innerHTML = out || `<text x="4" y="20" fill="#5f6a7d" font-size="12">No calls in view.</text>`;

    const ticks = stripAxisTicks();
    const approxW = (label) => label.length * 6.4 + 6;
    const layoutTick = (t) => {
      const w = approxW(t.label);
      let anchor = "middle", lx = t.x, left = t.x - w / 2, right = t.x + w / 2;
      if (left < 1) { anchor = "start"; lx = Math.max(0, t.x); left = lx; right = lx + w; }
      else if (right > plotW - 1) { anchor = "end"; lx = Math.min(plotW, t.x); right = lx; left = lx - w; }
      return { ...t, anchor, lx, left, right, w };
    };
    const visTicks = ticks.filter((t) => t.x >= 0 && t.x <= plotW).map(layoutTick);
    const chosen = visTicks.slice();
    const axisH = 28;
    let axisOut = `<line x1="0" x2="${plotW}" y1="10" y2="10" stroke="#2d3545"/>`;
    chosen.forEach((t) => {
      axisOut += `<line class="strip-tick-line" data-date="${esc(t.date)}" data-x="${t.x}" x1="${t.x}" x2="${t.x}" y1="10" y2="16" stroke="#5f6a7d"/>`;
      axisOut += `<text class="strip-tick" data-date="${esc(t.date)}" x="${t.lx}" y="26" text-anchor="${t.anchor}" font-size="11" fill="#8b95a8">${esc(t.label)}</text>`;
      // Invisible alignment mark on the chart overlay at the same date-to-x mapping.
      overlay += `<line class="chart-date-x" data-date="${esc(t.date)}" x1="${t.x}" x2="${t.x}" y1="0" y2="0"/>`;
    });
    svg.innerHTML = overlay;
    stampOverlayView(svg);
    reanchorCallPop();
    lw.mapKey = mappingKey();
    if (axisSvg) {
      axisSvg.setAttribute("width", String(chartW));
      axisSvg.setAttribute("height", String(axisH));
      axisSvg.setAttribute("viewBox", `0 0 ${chartW} ${axisH}`);
      axisSvg.style.width = chartW + "px";
      axisSvg.style.height = axisH + "px";
      axisSvg.innerHTML = axisOut;
    }
  }
  function stampOverlayView(svg) {
    if (!svg || !lw.chart) return;
    try {
      const snap = viewSnapshot();
      if (snap && snap.vr) {
        svg.setAttribute("data-logical-from", String(snap.vr.from));
        svg.setAttribute("data-logical-to", String(snap.vr.to));
      }
      if (snap && snap.pr) {
        svg.setAttribute("data-price-from", String(snap.pr.from));
        svg.setAttribute("data-price-to", String(snap.pr.to));
      } else {
        svg.removeAttribute("data-price-from");
        svg.removeAttribute("data-price-to");
      }
      if (snap) svg.setAttribute("data-autoscale", String(!!snap.auto));
    } catch (e) {}
  }
  function reanchorCallPop() {
    if (!popState || !popState.key) return;
    const pop = $("call-pop");
    if (!pop || pop.hidden) return;
    const parts = popState.key.split("|");
    const kind = parts[0], date = parts.slice(1).join("|");
    const el = document.querySelector(kind === "flip"
      ? `.chart-flip-ring[data-date="${CSS.escape(date)}"]`
      : `.chart-mark[data-kind="${CSS.escape(kind)}"][data-date="${CSS.escape(date)}"]`);
    if (el) placeCallPop(el);
    else closeCallPop();
  }
  function hideLaneTip() {
    const tip = $("lane-tip");
    if (tip) { tip.hidden = true; tip.textContent = ""; }
  }
  function showLaneTip(el, ev) {
    const tip = $("lane-tip");
    if (!tip || !el || !el.dataset.tip) return;
    tip.textContent = el.dataset.tip;
    tip.hidden = false;
    tip.style.left = "0px"; tip.style.top = "0px";
    const er = el.getBoundingClientRect();
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = er.left + er.width / 2 - tw / 2;
    left = Math.min(Math.max(8, left), Math.max(8, window.innerWidth - tw - 8));
    let top = er.top - th - 8;
    if (top < 8) top = er.bottom + 8;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  function bindLaneTips() {
    const host = $("lanes");
    if (!host || host.dataset.tipBound) return;
    host.dataset.tipBound = "1";
    const markFrom = (e) => e.target.closest && e.target.closest(".lane-mark");
    host.addEventListener("pointerover", (e) => { const m = markFrom(e); if (m) showLaneTip(m, e); });
    host.addEventListener("pointerout", (e) => { if (!host.contains(e.relatedTarget)) hideLaneTip(); const m = markFrom(e); if (m && !m.contains(e.relatedTarget)) hideLaneTip(); });
    host.addEventListener("click", (e) => { const m = markFrom(e); if (m) { e.preventDefault(); showLaneTip(m, e); } else hideLaneTip(); });
    host.addEventListener("focusin", (e) => { const m = markFrom(e); if (m) showLaneTip(m, e); });
    host.addEventListener("focusout", (e) => { if (!host.contains(e.relatedTarget)) hideLaneTip(); });
  }
  function updateCallsScrollCue() {
    const sc = $("calls-scroll"), wrap = $("calls-scroll-wrap"), cue = $("calls-scroll-cue");
    if (!sc || !wrap) return;
    const overflow = sc.scrollWidth - sc.clientWidth > 2;
    const remain = sc.scrollWidth - sc.clientWidth - sc.scrollLeft;
    const more = overflow && remain > 2;
    wrap.classList.toggle("more-right", more);
    if (cue) cue.hidden = !more;
  }


  function renderCallsTable(calls) {
    const rows = calls.slice().sort((a, b) => (b.date || "").localeCompare(a.date || "") || b.i - a.i);
    $("calls-body").innerHTML = rows.map((c) => `
      <tr class="${isHold(c.ticker) ? "holding" : ""}">
        <td>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noreferrer" title="watch the video at this moment">${fmtD(c.date)}</a>` : fmtD(c.date)}</td>
        <td class="ch" title="${esc(c.channel)}: ${esc(c.summary)}">${esc(c.channel)}</td>
        <td>${sentBadge(c.sentiment, c.is_flip ? c.flip_tag : null)}</td>
        <td class="r">${retCell(spy() ? c.ex_1d : c.ret_1d, c.has_price && c.pending_1d)}</td>
        <td class="r">${retCell(spy() ? c.ex_5d : c.ret_5d, c.has_price && c.pending_5d, hitGlyph(c, spy() ? "hit_5d_spy" : "hit_5d", "pending_5d"))}</td>
        <td class="r">${retCell(c.ret_td, c.has_price && c.pending_td)}</td>
        <td class="r">${retCell(c.ex_td, c.has_price && c.pending_td)}</td>
        <td>${maBadge(c)}</td>
      </tr>`).join("") || `<tr><td colspan="8" class="dim">No calls match these filters.</td></tr>`;
    requestAnimationFrame(updateCallsScrollCue);
  }

  function renderTimeline() { renderList(); renderFocus(); }

  /* ---------- Chart.js shared ---------- */
  function destroy(name) { if (charts[name]) { charts[name].destroy(); delete charts[name]; } }
  const axis = (extra = {}) => Object.assign({ ticks: { color: "#8b95a8", font: { size: 11 } }, grid: { color: "rgba(255,255,255,0.04)" }, border: { color: "#232a37" } }, extra);
  const tip = { backgroundColor: "#181d27", titleColor: "#e7ecf3", bodyColor: "#e7ecf3", borderColor: "#2d3545", borderWidth: 1 };
  function baseOpts() {
    return { responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { labels: { boxWidth: 10, boxHeight: 10, color: "#8b95a8", font: { size: 11 } } }, tooltip: { ...tip } },
      scales: { x: axis(), y: axis() } };
  }
  const halfLine = { id: "halfLine", afterDatasetsDraw(ch) {
    const xs = ch.scales.x; if (!xs || ch.options.indexAxis !== "y") return;
    const x = xs.getPixelForValue(0.5), { top, bottom } = ch.chartArea, g = ch.ctx;
    g.save(); g.strokeStyle = "rgba(231,236,243,0.35)"; g.setLineDash([4, 4]); g.beginPath(); g.moveTo(x, top); g.lineTo(x, bottom); g.stroke(); g.restore();
  } };

  /* ---------- Creators (scorecard) ---------- */
  function renderCreators() {
    $("basis-note").textContent = spy() ? "Showing vs SPY: a call counts as right only if the stock beat (or, for ▼, lagged) the whole market over the same days." : "Showing raw moves. Switch to vs SPY to remove the market’s own move.";
    if (!state.scores) { $("score-kpis").innerHTML = `<p class="status">Scores are missing. Run ./scripts/run_all.sh then refresh.</p>`; return; }
    const rows = fCalls();
    const sc = scored(rows);
    const noPx = rows.filter((c) => !c.has_price).length;
    const lab = spy() ? " vs SPY" : "";
    $("score-kpis").innerHTML = [
      [`5-session hit rate${lab}`, pct(sc.h5.r), `${sc.h5.k} of n=${sc.h5.n} scored calls`, sc.h5.n],
      [`Next-session hit rate${lab}`, pct(sc.h1.r), `${sc.h1.k} of n=${sc.h1.n}`, sc.h1.n],
      ["5-session vs SPY", pct(sc.hs.r), `beat/lagged the market as called · n=${sc.hs.n}`, sc.hs.n],
      [`Right so far (since the call)${lab}`, pct(sc.ht.r), `n=${sc.ht.n} · still open, changes daily`, sc.ht.n],
      ["Pending 5-session", String(sc.pending), "not enough sessions yet; not misses", 99],
      ["Calls with no price data", String(noPx), "shown as missing, never guessed", 99],
    ].map(([l, v, h, n]) => `<div class="panel"><p class="label">${l}</p><p class="value">${v}</p><p class="hint">${h}${n < THIN ? ' · <span class="thin">too few to trust</span>' : ""}</p></div>`).join("");

    const by = new Map();
    rows.filter((c) => c.directional).forEach((c) => { if (!by.has(c.channel)) by.set(c.channel, []); by.get(c.channel).push(c); });
    const labels = Array.from(by.keys()).sort();
    const st = labels.map((l) => scored(by.get(l)));
    $("cap-score-ch").textContent = `5-session and next-session hit rates${lab}. n = scored calls; “thin” = under ${THIN}. Dashed line = 50% (a coin flip).`;
    destroy("scoreCh");
    charts.scoreCh = new Chart($("chart-score-channel"), {
      type: "bar",
      data: { labels: labels.map((l, i) => `${l}  n=${st[i].h5.n}${st[i].h5.n < THIN ? " · thin" : ""}`),
        datasets: [
          { label: `5-session${lab}`, data: st.map((s) => s.h5.r), backgroundColor: "#7aa2ff", borderWidth: 0, barPercentage: 0.8 },
          { label: `Next session${lab}`, data: st.map((s) => s.h1.r), backgroundColor: "rgba(62,207,142,0.75)", borderWidth: 0, barPercentage: 0.8 },
        ] },
      plugins: [halfLine],
      options: Object.assign(baseOpts(), {
        indexAxis: "y",
        scales: { x: axis({ min: 0, max: 1, ticks: { color: "#8b95a8", callback: (v) => `${Math.round(v * 100)}%` } }), y: axis({ grid: { display: false }, ticks: { color: "#e7ecf3", font: { size: 11 } } }) },
        plugins: { legend: baseOpts().plugins.legend, tooltip: { ...tip, callbacks: { label: (c) => {
          const s = st[c.dataIndex]; const o = c.datasetIndex === 0 ? s.h5 : s.h1;
          return `${c.dataset.label}: ${pct(c.raw)} (${o.k} of n=${o.n})${o.n < THIN ? " — too few to trust" : ""}`;
        } } } },
      }),
    });
    renderSplits(rows);
    renderScoredTable(rows);
  }

  function renderSplits(rows) {
    const g = new Map();
    rows.filter((c) => c.directional).forEach((c) => { const k = `${c.channel}\u0000${c.ticker}`; if (!g.has(k)) g.set(k, []); g.get(k).push(c); });
    const out = Array.from(g.entries()).map(([k, rs]) => {
      const [channel, ticker] = k.split("\u0000"); const s = scored(rs);
      return { channel, ticker, directional: rs.length, bull: rs.filter((c) => c.sentiment === "bullish").length, bear: rs.filter((c) => c.sentiment === "bearish").length,
        h1: s.h1, h5: s.h5, hs: s.hs, ht: s.ht, hit1: s.h1.r, hit5: s.h5.r, hitspy: s.hs.r, hittd: s.ht.r, n5: s.h5.n, pending: s.pending };
    });
    const { key, dir } = state.splitSort;
    out.sort((a, b) => cmp(a, b, key, dir) || b.directional - a.directional || a.channel.localeCompare(b.channel));
    const solid = out.filter((r) => r.n5 >= THIN).length;
    $("split-count").textContent = `${out.length} creator–ticker pairs · ${solid} with ${THIN}+ scored calls`;
    document.querySelectorAll("th[data-sort-split]").forEach((th) => th.classList.toggle("sorted", th.dataset.sortSplit === key));
    $("split-body").innerHTML = out.map((r) => `<tr class="click ${isHold(r.ticker) ? "holding" : ""}" data-focus="${esc(r.ticker)}">
      <td>${esc(r.channel)}</td><td>${tickerCell(r.ticker)}</td>
      <td><span class="pos">▲${r.bull}</span> <span class="neg">▼${r.bear}</span></td>
      <td class="r">${rateTxt(r.h1)}</td><td class="r">${rateTxt(r.h5)}</td><td class="r">${rateTxt(r.hs)}</td><td class="r">${rateTxt(r.ht)}</td>
      <td class="r">${r.pending || '<span class="dim">0</span>'}</td>
      <td>${r.n5 < THIN ? `<span class="thin">too few to trust</span>` : `<span class="dim">n=${r.n5}</span>`}</td></tr>`).join("") || `<tr><td colspan="9" class="dim">No directional calls in view.</td></tr>`;
  }

  function cmp(a, b, key, dir) {
    const va = a[key], vb = b[key];
    if (va == null && vb == null) return 0; if (va == null) return 1; if (vb == null) return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    if (typeof va === "boolean") return ((va ? 1 : 0) - (vb ? 1 : 0)) * dir;
    return String(va).localeCompare(String(vb)) * dir;
  }

  function renderScoredTable(rows) {
    const { key, dir } = state.scoreSort;
    const sorted = rows.slice().sort((a, b) => cmp(a, b, key, dir) || cmp(a, b, "ticker", 1));
    const s = state.scores.summary || {};
    $("score-count").textContent = `${rows.length} rows in view · overall 5-session hit rate ${pct(s.hit_rate_5d)} (n=${s.n_5d || 0})`;
    document.querySelectorAll("th[data-sort-score]").forEach((th) => th.classList.toggle("sorted", th.dataset.sortScore === key));
    $("score-body").innerHTML = sorted.map((c) => `<tr class="${isHold(c.ticker) ? "holding" : ""}">
      <td>${esc(c.date || "—")}</td><td>${esc(c.channel)}</td><td class="click" data-focus="${esc(c.ticker)}">${tickerCell(c.ticker)}</td>
      <td>${sentBadge(c.sentiment, c.is_flip ? c.flip_tag : null)}</td>
      <td class="r">${retCell(c.ret_1d, c.has_price && c.pending_1d)}</td><td class="r">${retCell(c.ret_5d, c.has_price && c.pending_5d)}</td>
      <td>${c.has_price ? hitCell(spy() ? c.hit_5d_spy : c.hit_5d, c.pending_5d, c.directional) : '<span class="dim">no price</span>'}</td>
      <td class="r">${retCell(c.ex_5d, c.has_price && c.pending_5d)}</td>
      <td class="r">${retCell(c.ret_td, c.has_price && c.pending_td)}</td><td class="r">${retCell(c.ex_td, c.has_price && c.pending_td)}</td>
      <td>${maBadge(c)}</td><td>${link(c.url)}</td></tr>`).join("") || `<tr><td colspan="12" class="dim">No calls match these filters.</td></tr>`;
  }

  /* ---------- Flips ---------- */
  const FLIP_RULE = "A flip is tagged ahead, after, no follow-through, or pending, judged over 5 sessions, with any size of move counting, on raw price moves (not vs SPY).";
  function flipDefText(short) {
    const f = (state.scores && state.scores.flip_config) || {};
    const N = f.forward_sessions ?? 5, P = f.prior_sessions ?? 5;
    if (short) return `Ahead = moved the new way in the ${N} sessions after; after = it had already moved that way in the ${P} sessions before and then didn’t follow through.`;
    return FLIP_RULE;
  }
  function renderFlips() {
    $("flip-def").textContent = flipDefText(false);
    if (!state.scores) { $("flip-body").innerHTML = `<tr><td colspan="10">Run ./scripts/run_all.sh to build flips.</td></tr>`; return; }
    const f = state.scores.flip_config || {};
    $("th-prior").textContent = `${f.prior_sessions ?? 5} sessions before`;
    $("th-fwd").textContent = `${f.forward_sessions ?? 5} sessions after`;
    const flips = (state.scores.flips || []).filter((x) => inFilters({ date: x.date, channel: x.channel, ticker: x.ticker, sentiment: x.to }));
    const cnt = (t) => flips.filter((x) => x.tag === t).length;
    const n5 = flips.filter((x) => x.hit_5d != null), n1 = flips.filter((x) => x.hit_1d != null);
    const h5 = n5.filter((x) => x.hit_5d).length, h1 = n1.filter((x) => x.hit_1d).length;
    $("flip-kpis").innerHTML = [
      ["Flips in view", String(flips.length), `${(state.scores.flips || []).length} in the full file`, 99],
      ["Ahead of move", String(cnt("ahead")), "moved the new way after", 99],
      ["After the move", String(cnt("after")), "had already moved; no follow-through", 99],
      ["No follow-through", String(cnt("no_follow_through")), "didn’t move the new way either side", 99],
      ["Pending", String(cnt("pending")), "not enough sessions yet", 99],
      ["No price data", String(cnt("no_price")), "no daily prices to judge the flip", 99],
      ["Flip hit rate, next session / 5 sessions", `${n1.length ? pct(h1 / n1.length) : "—"} / ${n5.length ? pct(h5 / n5.length) : "—"}`, `n=${n1.length} / n=${n5.length}`, n5.length],
    ].map(([l, v, h, n]) => `<div class="panel"><p class="label">${l}</p><p class="value">${v}</p><p class="hint">${h}${n < THIN ? ' · <span class="thin">too few to trust</span>' : ""}</p></div>`).join("");
    $("flip-count").textContent = `${flips.length} flips`;
    const rows = flips.slice().sort((a, b) => b.date.localeCompare(a.date));
    const signed = (m, to) => m == null ? `<span class="dim">—</span>` : retCell(m, false);
    $("flip-body").innerHTML = rows.map((x) => `<tr class="${isHold(x.ticker) ? "holding" : ""}">
      <td>${esc(x.date)}</td><td>${esc(x.channel)}</td><td class="click" data-focus="${esc(x.ticker)}">${tickerCell(x.ticker)}</td>
      <td>${sentBadge(x.from)} → ${sentBadge(x.to)}</td><td>${esc(x.prev_date || "—")}</td>
      <td class="r">${signed(x.prior_move, x.to)}</td><td class="r">${x.tag === "pending" ? '<span class="pending">pending</span>' : signed(x.fwd_move, x.to)}</td>
      <td><span class="tag ${esc(x.tag || "pending")}">${esc(TAG_LABEL[x.tag] || "—")}</span></td>
      <td>${hitCell(x.hit_1d, x.hit_1d == null)} / ${hitCell(x.hit_5d, x.hit_5d == null)}</td><td>${link(x.url)}</td></tr>`).join("") || `<tr><td colspan="10" class="dim">No flips match these filters.</td></tr>`;
  }

  /* ---------- Mentions ---------- */
  function stacked(rows, key, limit) {
    const m = new Map();
    rows.forEach((r) => { const k = r[key] || "—"; if (!m.has(k)) m.set(k, { total: 0, by: {} }); const x = m.get(k); x.total++; x.by[r.sentiment] = (x.by[r.sentiment] || 0) + 1; });
    let labels = Array.from(m.keys()).sort((a, b) => m.get(b).total - m.get(a).total || a.localeCompare(b));
    if (limit) labels = labels.slice(0, limit);
    return { labels, datasets: SENT.filter((s) => labels.some((l) => m.get(l).by[s])).map((s) => ({ label: `${GLYPH[s]} ${s[0].toUpperCase()}${s.slice(1)}`, data: labels.map((l) => m.get(l).by[s] || 0), backgroundColor: COL[s], borderWidth: 0 })) };
  }
  function hbar(id, name, data, onPick) {
    destroy(name);
    charts[name] = new Chart($(id), { type: "bar", data, options: Object.assign(baseOpts(), {
      indexAxis: "y",
      scales: { x: axis({ stacked: true, ticks: { color: "#8b95a8", precision: 0 } }), y: axis({ stacked: true, grid: { display: false }, ticks: { color: "#e7ecf3", font: { size: 11, weight: "600" } } }) },
      onClick: (e, els) => { if (els.length) onPick(data.labels[els[0].index]); },
    }) });
  }
  function days(a, b) { const out = []; if (!a || !b) return out; for (let d = new Date(a + "T00:00:00"); d <= new Date(b + "T00:00:00"); d.setDate(d.getDate() + 1)) out.push(d.toISOString().slice(0, 10)); return out; }
  function renderMentions() {
    const rows = state.mentions.filter((r) => inFilters(r));
    const tk = stacked(rows, "ticker", 15);
    $("cap-tickers").textContent = tk.labels.length ? `Top ${tk.labels.length} tickers by mentions, split by sentiment. Click a bar to filter.` : "No mentions in the current filters";
    hbar("chart-tickers", "tickers", tk, (l) => { state.ticker = l; $("ticker").value = l; renderActive(); });
    hbar("chart-channels", "channels", stacked(rows, "channel"), (l) => { state.channel = l; $("channel").value = l; renderActive(); });
    const ds = days(state.from || state.minDate, state.to || state.maxDate);
    destroy("time");
    charts.time = new Chart($("chart-time"), { type: "bar", data: { labels: ds, datasets: SENT.filter((s) => rows.some((r) => r.sentiment === s)).map((s) => ({
      label: `${GLYPH[s]} ${s[0].toUpperCase()}${s.slice(1)}`, data: ds.map((d) => rows.filter((r) => r.date === d && r.sentiment === s).length), backgroundColor: COL[s], borderWidth: 0 })) },
      options: Object.assign(baseOpts(), { scales: { x: axis({ stacked: true, grid: { display: false }, ticks: { color: "#8b95a8", font: { size: 10 }, maxRotation: 60, autoSkip: true } }), y: axis({ stacked: true, beginAtZero: true, ticks: { color: "#8b95a8", precision: 0 } }) } }) });
    const { key, dir } = state.sort;
    const sorted = rows.slice().sort((a, b) => cmp(a, b, key, dir) || cmp(a, b, "ticker", 1) || a.i - b.i);
    $("table-count").textContent = `${rows.length} of ${state.mentions.length} mentions`;
    document.querySelectorAll("th[data-sort]").forEach((th) => th.classList.toggle("sorted", th.dataset.sort === key));
    $("mentions-body").innerHTML = sorted.map((r) => `<tr class="${isHold(r.ticker) ? "holding" : ""}"><td>${esc(r.date || "—")}</td><td>${esc(r.channel)}</td>
      <td class="click" data-focus="${esc(r.ticker)}">${tickerCell(r.ticker)}</td><td>${sentBadge(r.sentiment)}</td><td class="pt">${esc(r.price_talk || "—")}</td>
      <td class="sum">${esc(r.summary || "—")}</td><td>${link(r.url)}</td></tr>`).join("") || `<tr><td colspan="7" class="dim">No mentions match these filters.</td></tr>`;
  }

  /* ---------- Reaction ---------- */
  function renderReaction() {
    const k = spy() ? "ex_1d" : "ret_1d";
    $("react-basis").textContent = spy() ? "Showing vs SPY: each move minus the market’s move that same session." : "Showing raw moves.";
    if (!state.scores) return;
    const rows = fCalls().filter((c) => c[k] != null);
    const by = {}; rows.forEach((c) => { (by[c.sentiment] = by[c.sentiment] || []).push(c[k]); });
    const labels = SENT.filter((s) => (by[s] || []).length);
    const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
    const means = labels.map((s) => mean(by[s])), pos = labels.map((s) => by[s].filter((x) => x > 0).length / by[s].length), ns = labels.map((s) => by[s].length);
    const all = rows.map((c) => c[k]);
    $("react-kpis").innerHTML = [
      ["Mentions with a next session", String(all.length), ""],
      [`Average next-session return${spy() ? " vs SPY" : ""}`, all.length ? spct(mean(all), 2) : "—", "all sentiments"],
      [`Share up next session${spy() ? " vs SPY" : ""}`, all.length ? pct(all.filter((x) => x > 0).length / all.length) : "—", ""],
    ].map(([l, v, h]) => `<div class="panel"><p class="label">${l}</p><p class="value">${v}</p><p class="hint">${h}</p></div>`).join("");
    const xl = labels.map((s, i) => `${GLYPH[s]} ${s[0].toUpperCase()}${s.slice(1)} (n=${ns[i]})`);
    const mk = (id, name, data, fmt, yopt) => { destroy(name); charts[name] = new Chart($(id), { type: "bar",
      data: { labels: xl, datasets: [{ data, backgroundColor: labels.map((s) => COL[s]), borderWidth: 0 }] },
      options: Object.assign(baseOpts(), { plugins: { legend: { display: false }, tooltip: { ...tip, callbacks: { label: (c) => `${fmt(c.raw)} (n=${ns[c.dataIndex]})` } } },
        scales: { x: axis({ grid: { display: false }, ticks: { color: "#e7ecf3" } }), y: axis(yopt) } }) }); };
    mk("chart-react-mean", "rMean", means, (v) => spct(v, 2), { ticks: { color: "#8b95a8", callback: (v) => `${(v * 100).toFixed(1)}%` } });
    mk("chart-react-pos", "rPos", pos, (v) => `${pct(v)} up`, { min: 0, max: 1, ticks: { color: "#8b95a8", callback: (v) => `${Math.round(v * 100)}%` } });
  }

  /* ---------- Insights ---------- */
  function renderInsights() {
    Object.keys(charts).filter((k) => k.startsWith("ins-")).forEach(destroy);
    const list = $("insights-list");
    if (!state.insights || !Array.isArray(state.insights.findings)) { list.innerHTML = `<p class="status">Insights are missing. Run ./scripts/run_all.sh then refresh.</p>`; return; }
    if (state.insights.disclaimer) $("insights-disclaimer").textContent = state.insights.disclaimer;
    const nMin = state.insights.n_min || THIN;
    list.innerHTML = state.insights.findings.map((f, i) => {
      const badges = [`<span class="badge">#${f.rank || i + 1}</span>`, `<span class="badge">n=${f.n}</span>`];
      if (f.horizon) badges.push(`<span class="badge">${esc(f.horizon)} horizon</span>`);
      if (f.p_value != null) badges.push(`<span class="badge">p=${Number(f.p_value).toFixed(f.p_value < 0.01 ? 4 : 2)}</span>`);
      if (f.too_few || (f.n != null && f.n < nMin)) badges.push(`<span class="badge warn">too few to trust</span>`);
      if (f.flag) badges.push(`<span class="badge warn">${esc(f.flag)}</span>`);
      else if (f.significant) badges.push(`<span class="badge note">unlikely to be luck alone</span>`);
      return `<article class="panel insight"><div class="meta">${badges.join("")}</div><h2>${esc(f.title)}</h2>
        <p class="sentence">${esc(f.sentence)}</p>${f.chart ? `<div class="chart-box"><canvas id="ins-c-${i}"></canvas></div>` : ""}</article>`;
    }).join("");
    state.insights.findings.forEach((f, i) => { const cv = $(`ins-c-${i}`); if (cv && f.chart) charts[`ins-${i}`] = insightChart(cv, f.chart); });
  }
  function insightChart(canvas, spec) {
    const fmt = spec.y_format || "percent", nl = spec.n_labels;
    const tick = (v) => fmt === "percent" ? `${Math.round(v * 100)}%` : v;
    const many = (spec.labels || []).some((l) => String(l).length > 14) || (spec.labels || []).length > 6;
    const labels = (spec.labels || []).map((l, i) => nl && nl[i] != null ? `${l} (n=${nl[i]})` : l);
    return new Chart(canvas, { type: spec.type || "bar",
      data: { labels, datasets: (spec.datasets || []).map((d) => ({ label: d.label, data: d.values, backgroundColor: d.colors && d.colors.length ? d.colors : "#7aa2ff", borderWidth: 0 })) },
      options: Object.assign(baseOpts(), { indexAxis: many ? "y" : "x",
        plugins: { legend: { display: (spec.datasets || []).length > 1, labels: baseOpts().plugins.legend.labels }, tooltip: { ...tip, callbacks: { label: (c) => {
          const n = nl ? nl[c.dataIndex] : null; return `${c.dataset.label}: ${fmt === "percent" ? pct(c.raw) : c.raw}${n != null ? ` (n=${n}${n < THIN ? ", too few to trust" : ""})` : ""}`; } } } },
        scales: many ? { x: axis({ beginAtZero: true, ticks: { color: "#8b95a8", callback: tick } }), y: axis({ grid: { display: false }, ticks: { color: "#e7ecf3", font: { size: 11 } } }) }
          : { x: axis({ grid: { display: false }, ticks: { color: "#8b95a8", maxRotation: 30 } }), y: axis({ beginAtZero: true, ticks: { color: "#8b95a8", callback: tick } }) } }) });
  }

  /* ---------- wiring ---------- */
  function renderActive() {
    ({ timeline: renderTimeline, creators: renderCreators, flips: renderFlips, mentions: renderMentions, reaction: renderReaction, insights: renderInsights }[state.tab] || renderTimeline)();
    writeHash();
  }
  function setTab(tab) {
    state.tab = tab;
    document.querySelectorAll(".tabs button").forEach((b) => { b.classList.toggle("active", b.dataset.tab === tab); b.setAttribute("aria-selected", String(b.dataset.tab === tab)); });
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
    renderActive();
  }
  const TABS = ["timeline", "creators", "flips", "mentions", "reaction", "insights"];
  let writingHash = false;
  function focusTicker(t) { state.focus = t; if (state.ticker && state.ticker !== t) { state.ticker = ""; $("ticker").value = ""; } setTab("timeline"); }
  function writeHash() {
    const h = `#tab=${state.tab}${state.focus ? `&t=${encodeURIComponent(state.focus)}` : ""}`;
    if (location.hash === h) return;
    writingHash = true;
    history.replaceState(null, "", h);
    writingHash = false;
  }
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    const t = p.get("t");
    if (t) state.focus = t.toUpperCase();
    const tab = p.get("tab");
    if (tab && TABS.includes(tab)) state.tab = tab;
  }
  function applyHash() {
    if (writingHash) return;
    const prevTab = state.tab, prevFocus = state.focus;
    readHash();
    if (state.focus && state.ticker && state.ticker !== state.focus) { state.ticker = ""; $("ticker").value = ""; }
    if (state.tab === prevTab && state.focus === prevFocus) return;
    setTab(state.tab);
  }


  /* ---------- chart popover ---------- */
  const popState = { pinned: false, key: null };
  function callsForMarker(kind, date) {
    const calls = focusCalls();
    if (kind === "flip") return calls.filter((c) => c.is_flip && snapDate(c) === date);
    return calls.filter((c) => snapDate(c) === date && c.sentiment === kind);
  }
  function closeCallPop() {
    const pop = $("call-pop");
    if (pop) { pop.hidden = true; pop.innerHTML = ""; }
    popState.pinned = false;
    popState.key = null;
  }
  function placeCallPop(anchor) {
    const pop = $("call-pop");
    if (!pop || pop.hidden || !anchor) return;
    const r = anchor.getBoundingClientRect();
    const pad = 8;
    const pw = pop.offsetWidth, ph = pop.offsetHeight;
    let left = r.left + r.width / 2 - pw / 2;
    let top = r.bottom + 8;
    left = Math.min(Math.max(pad, left), Math.max(pad, window.innerWidth - pw - pad));
    if (top + ph > window.innerHeight - pad) top = r.top - ph - 8;
    top = Math.min(Math.max(pad, top), Math.max(pad, window.innerHeight - ph - pad));
    pop.style.left = left + "px";
    pop.style.top = top + "px";
  }
  function openCallPop(kind, date, anchor, pinned) {
    const pop = $("call-pop");
    if (!pop || !anchor) return;
    const rows = callsForMarker(kind, date);
    if (!rows.length) return;
    const key = kind + "|" + date;
    popState.pinned = !!pinned;
    popState.key = key;
    pop.style.pointerEvents = pinned ? "auto" : "none";
    pop.innerHTML = rows.map((c) => {
      const tag = c.is_flip && c.flip_tag ? ` · ${esc(TAG_LABEL[c.flip_tag] || c.flip_tag)}` : "";
      const href = c.url || c.video_url || "";
      const watch = href
        ? `<a href="${esc(href)}" target="_blank" rel="noopener">Watch</a>`
        : `<span class="novid">no video link</span>`;
      return `<div class="call-pop-row"><div>${esc(c.channel)} · ${esc(fmtD(c.date))} · ${GLYPH[c.sentiment] || ""} ${esc(c.sentiment)}${tag}</div>${watch}</div>`;
    }).join("");
    pop.hidden = false;
    placeCallPop(anchor);
  }
  function bindCallPop() {
    const overlay = $("chart-overlay");
    if (!overlay || overlay.dataset.popBound) return;
    overlay.dataset.popBound = "1";
    const targetOf = (e) => e.target.closest && (e.target.closest(".chart-flip-ring") || e.target.closest(".chart-mark"));
    overlay.addEventListener("click", (e) => {
      const el = targetOf(e);
      if (!el) return;
      e.preventDefault();
      e.stopPropagation();
      openCallPop(el.getAttribute("data-kind"), el.getAttribute("data-date"), el, true);
    });
    overlay.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const el = targetOf(e);
      if (!el) return;
      e.preventDefault();
      openCallPop(el.getAttribute("data-kind"), el.getAttribute("data-date"), el, true);
    });
    overlay.addEventListener("pointerover", (e) => {
      if (popState.pinned) return;
      const el = targetOf(e);
      if (el) openCallPop(el.getAttribute("data-kind"), el.getAttribute("data-date"), el, false);
    });
    overlay.addEventListener("pointerout", (e) => {
      if (popState.pinned) return;
      const pop = $("call-pop");
      const next = e.relatedTarget;
      if (pop && next && (pop.contains(next) || overlay.contains(next))) return;
      closeCallPop();
    });
  }

  /* ---------- holdings editor ---------- */
  function renderHoldingsList() {
    const ul = $("holdings-list");
    if (!ul) return;
    ul.innerHTML = HOLDINGS.map((t) => `<li data-t="${esc(t)}"><span>★ ${esc(t)}</span><button type="button" data-remove="${esc(t)}" aria-label="Remove ${esc(t)}">Remove</button></li>`).join("")
      || `<li class="dim">No tickers in holdings.</li>`;
    const btn = $("holdings"), filter = $("holdings-filter");
    if (btn) btn.setAttribute("aria-pressed", String(!!state.holdings));
    if (filter) filter.checked = !!state.holdings;
  }
  function refreshHoldingsUI() {
    renderHoldingsList();
    const sel = $("ticker");
    if (sel) {
      const cur = sel.value;
      fill(sel, uniq(state.mentions.map((r) => r.ticker)), "All tickers");
      sel.value = cur;
    }
    renderActive();
  }
  function addHolding(raw) {
    const t = String(raw || "").trim().toUpperCase();
    if (!t) return;
    if (!HOLDINGS.includes(t)) {
      HOLDINGS = HOLDINGS.concat([t]);
      saveHoldings(HOLDINGS);
      refreshHoldingsUI();
    } else {
      renderHoldingsList();
    }
  }
  function removeHolding(t) {
    t = String(t || "").trim().toUpperCase();
    const next = HOLDINGS.filter((x) => x !== t);
    if (next.length === HOLDINGS.length) return;
    HOLDINGS = next;
    saveHoldings(HOLDINGS);
    refreshHoldingsUI();
  }
  function resetHoldings() {
    if (!confirm("Reset holdings to the default list (AAPL)?")) return;
    HOLDINGS = DEFAULT_HOLDINGS.slice();
    saveHoldings(HOLDINGS);
    refreshHoldingsUI();
  }
  function setHoldingsPanel(open) {
    const panel = $("holdings-panel"), btn = $("holdings");
    if (!panel) return;
    panel.hidden = !open;
    if (btn) btn.setAttribute("aria-expanded", String(!!open));
    if (open) {
      renderHoldingsList();
      // keep the panel inside the viewport
      const r = panel.getBoundingClientRect();
      if (r.right > window.innerWidth - 8) panel.style.left = "auto", panel.style.right = "0";
      else panel.style.left = "0", panel.style.right = "auto";
    }
  }
  function holdingsPanelOpen() {
    const panel = $("holdings-panel");
    return !!(panel && !panel.hidden);
  }

  function bind() {
    const on = (id, ev, fn) => $(id).addEventListener(ev, fn);
    ["from", "to", "channel", "ticker", "sentiment"].forEach((id) => on(id, "change", (e) => { state[id] = e.target.value; renderActive(); }));
    const holdBtn = $("holdings");
    if (holdBtn) holdBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      setHoldingsPanel(!holdingsPanelOpen());
    });
    const holdFilter = $("holdings-filter");
    if (holdFilter) holdFilter.addEventListener("change", () => {
      state.holdings = !!holdFilter.checked;
      if ($("holdings")) $("holdings").setAttribute("aria-pressed", String(state.holdings));
      renderActive();
    });
    const holdAdd = $("holdings-add");
    if (holdAdd) holdAdd.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = $("holdings-input");
      addHolding(input ? input.value : "");
      if (input) input.value = "";
    });
    const holdList = $("holdings-list");
    if (holdList) holdList.addEventListener("click", (e) => {
      const b = e.target.closest("[data-remove]");
      if (b) removeHolding(b.getAttribute("data-remove"));
    });
    const holdReset = $("holdings-reset");
    if (holdReset) holdReset.addEventListener("click", resetHoldings);
    bindCallPop();
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if ($("call-pop") && !$("call-pop").hidden) { closeCallPop(); e.preventDefault(); return; }
      if (holdingsPanelOpen()) { setHoldingsPanel(false); e.preventDefault(); }
    });
    document.addEventListener("pointerdown", (e) => {
      const pop = $("call-pop");
      if (pop && !pop.hidden && !pop.contains(e.target) && !(e.target.closest && e.target.closest("#chart-overlay .chart-mark, #chart-overlay .chart-flip-ring"))) {
        closeCallPop();
      }
      if (holdingsPanelOpen() && !(e.target.closest && e.target.closest(".hold-wrap"))) setHoldingsPanel(false);
    });
    document.querySelectorAll("#chart-legend .leg-btn").forEach((b) => {
      b.addEventListener("click", () => {
        const k = b.dataset.layer;
        if (!LEGEND_KEYS.includes(k)) return;
        state.legend[k] = !state.legend[k];
        saveLegend(state.legend);
        applyLegendVisibility();
      });
    });
    syncLegendButtons();
    renderHoldingsList();
    const setBasis = (b) => { state.basis = b; $("basis-raw").classList.toggle("on", b === "raw"); $("basis-spy").classList.toggle("on", b === "spy");
      $("basis-raw").setAttribute("aria-pressed", String(b === "raw")); $("basis-spy").setAttribute("aria-pressed", String(b === "spy")); renderActive(); };
    on("basis-raw", "click", () => setBasis("raw")); on("basis-spy", "click", () => setBasis("spy"));
    on("reset", "click", () => {
      Object.assign(state, { from: state.minDate, to: state.maxDate, channel: "", ticker: "", sentiment: "", holdings: false, search: "" });
      $("from").value = state.from; $("to").value = state.to; ["channel", "ticker", "sentiment"].forEach((id) => { $(id).value = ""; });
      $("tsearch").value = ""; $("holdings").setAttribute("aria-pressed", "false");
      if ($("holdings-filter")) $("holdings-filter").checked = false; setBasis("raw");
    });
    on("tsearch", "input", (e) => { state.search = e.target.value; renderList(); });
    $("tlist").addEventListener("click", (e) => { const it = e.target.closest(".titem"); if (it) { state.focus = it.dataset.t; renderTimeline(); writeHash(); } });
    $("tlist").addEventListener("keydown", (e) => { if (e.key === "Enter") { const it = e.target.closest(".titem"); if (it) { state.focus = it.dataset.t; renderTimeline(); writeHash(); } } });
    document.body.addEventListener("click", (e) => { const f = e.target.closest("[data-focus]"); if (f && !e.target.closest("a")) focusTicker(f.dataset.focus); });
    document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
    window.addEventListener("hashchange", applyHash);
    bindLaneTips();
    if ($("calls-scroll")) {
      $("calls-scroll").addEventListener("scroll", updateCallsScrollCue, { passive: true });
      new ResizeObserver(updateCallsScrollCue).observe($("calls-scroll"));
    }

    const sorter = (sel, attr, sk, fn) => document.querySelectorAll(sel).forEach((th) => th.addEventListener("click", (e) => {
      e.stopPropagation(); const key = th.dataset[attr];
      if (state[sk].key === key) state[sk].dir *= -1; else state[sk] = { key, dir: ["date", "channel", "ticker", "sentiment"].includes(key) ? (key === "date" ? -1 : 1) : -1 };
      fn();
    }));
    sorter("th[data-sort]", "sort", "sort", renderMentions);
    sorter("th[data-sort-score]", "sortScore", "scoreSort", renderCreators);
    sorter("th[data-sort-split]", "sortSplit", "splitSort", renderCreators);
  }
  function fill(sel, vals, all) {
    sel.innerHTML = `<option value="">${all}</option>` + vals.map((v) => `<option value="${esc(v)}">${esc(v)}${isHold(v) ? " ★" : ""}</option>`).join("");
  }

  function applyFreshness(scores) {
    const el = $("freshness");
    if (!el || typeof freshnessBanner !== "function") return;
    const msg = freshnessBanner(scores && scores.generated_at);
    if (!msg) { el.hidden = true; el.textContent = ""; return; }
    el.textContent = msg;
    el.hidden = false;
  }

  async function init() {
    if (typeof Chart !== "undefined") { Chart.defaults.font.family = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'; Chart.defaults.color = "#8b95a8"; Chart.defaults.animation = false; }
    readHash(); bind();
    try {
      const raw = await fetchJson(cfg.dataUrl);
      state.mentions = (Array.isArray(raw) ? raw : (raw && raw.mentions) || []).map((r, i) => r && typeof r === "object" ? {
        i, ticker: String(r.ticker || "").trim().toUpperCase() || "—", channel: String(r.channel || "").trim() || "Unknown", date: String(r.date || "").trim().slice(0, 10),
        sentiment: String(r.sentiment || "").trim().toLowerCase() || "unknown", price_talk: String(r.price_talk || "").trim(), summary: String(r.summary || "").trim(),
        url: String(r.url || "").trim() || String(r.video_url || "").trim() } : null).filter(Boolean);
    } catch (e) { status(`Could not load mentions from ${cfg.dataUrl}: ${e.message}`, true); applyFreshness(null); return; }
    const [sc, ins, px] = await Promise.allSettled([fetchJson(cfg.scoresUrl), fetchJson(cfg.insightsUrl), fetchJson(cfg.pricesUrl)]);
    state.scores = sc.status === "fulfilled" ? sc.value : null;
    state.insights = ins.status === "fulfilled" ? ins.value : null;
    state.prices = px.status === "fulfilled" ? px.value : null;
    if (state.scores && state.scores.thin_n) THIN = state.scores.thin_n;
    const errs = [[sc, "scores"], [ins, "insights"], [px, "prices"]].filter(([r]) => r.status !== "fulfilled").map(([r, n]) => `${n} (${r.reason && r.reason.message})`);
    if (errs.length) status(`Some data did not load: ${errs.join("; ")}. Run ./scripts/run_all.sh, then refresh.`, true);
    applyFreshness(state.scores);
    const dates = state.mentions.map((r) => r.date).filter(Boolean).sort();
    state.minDate = state.from = dates[0] || ""; state.maxDate = state.to = dates[dates.length - 1] || "";
    $("from").value = state.from; $("to").value = state.to;
    fill($("channel"), uniq(state.mentions.map((r) => r.channel)), "All creators");
    fill($("ticker"), uniq(state.mentions.map((r) => r.ticker)), "All tickers");
    $("flip-def-short").textContent = flipDefText(true);
    const spyBars = barsOf("SPY");
    const gen = state.scores && state.scores.generated_at ? new Date(state.scores.generated_at) : null;
    $("stamp").innerHTML = `${state.mentions.length} mentions · ${uniq(state.mentions.map((r) => r.channel)).length} creators<br>prices through ${spyBars ? fmtD(spyBars[spyBars.length - 1].date) : "—"}${gen ? ` · scored ${gen.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" })}` : ""}`;
    setTab(state.tab);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
