/* Creator Calls — Ticker Timeline. Reads ./data/*.json in the browser; no build step. */
(() => {
  "use strict";
  const cfg = Object.assign({
    dataUrl: "./data/mentions.json", scoresUrl: "./data/scores.json",
    insightsUrl: "./data/insights.json", pricesUrl: "./data/prices.json",
    holdings: [],
  }, window.DASHBOARD_CONFIG || {});
  const HOLDINGS = cfg.holdings || [];
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
    sort: { key: "date", dir: -1 }, scoreSort: { key: "date", dir: -1 }, splitSort: { key: "n5", dir: -1 },
  };
  const charts = {};
  const lw = { chart: null, close: null, s20: null, s50: null, markers: null, bars: [], barIdx: {} };

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
      rightPriceScale: { borderColor: "#232a37", scaleMargins: { top: 0.12, bottom: 0.12 } },
      timeScale: { borderColor: "#232a37", rightOffset: 3 },
      crosshair: { horzLine: { color: "#3a4356", labelBackgroundColor: "#232a37" }, vertLine: { color: "#3a4356", labelBackgroundColor: "#232a37" } },
    });
    const common = { priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
    lw.s50 = lw.chart.addSeries(L.LineSeries, { ...common, color: "#b18cff", lineWidth: 1, lineStyle: L.LineStyle.Dashed, title: "" });
    lw.s20 = lw.chart.addSeries(L.LineSeries, { ...common, color: "#6f9bff", lineWidth: 1, lineStyle: L.LineStyle.Dashed });
    lw.close = lw.chart.addSeries(L.LineSeries, { color: "#e9edf5", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
    lw.markers = L.createSeriesMarkers(lw.close, []);
    lw.chart.timeScale().subscribeVisibleLogicalRangeChange(() => requestAnimationFrame(drawOverlays));
    new ResizeObserver(() => requestAnimationFrame(drawOverlays)).observe($("chart"));
  }
  function snapDate(c) {
    // the bar on or before the video date (what the creator could see)
    if (c.price_asof_date && lw.barIdx[c.price_asof_date] != null) return c.price_asof_date;
    return null;
  }
  function focusCalls() { return fCalls({ ignoreTicker: true }).filter((c) => c.ticker === state.focus); }

  function renderFocus() {
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
      lw.close.setData(bars.map((b) => ({ time: b.date, value: b.close })));
      lw.s20.setData(smaLine(bars, 20));
      lw.s50.setData(smaLine(bars, 50));
      // aggregate ▲/▼ per bar so stacked markers stay readable
      const agg = new Map();
      calls.filter((c) => c.directional).forEach((c) => {
        const d = snapDate(c); if (!d) return;
        const k = `${d}|${c.sentiment}`; agg.set(k, (agg.get(k) || 0) + 1);
      });
      const mk = Array.from(agg.entries()).map(([k, n]) => {
        const [d, s] = k.split("|"); const bull = s === "bullish";
        return { time: d, position: bull ? "belowBar" : "aboveBar", shape: bull ? "arrowUp" : "arrowDown", color: COL[s], text: n > 1 ? `${GLYPH[s]}${n}` : GLYPH[s], size: 1 };
      }).sort((a, b) => a.time < b.time ? -1 : a.time > b.time ? 1 : (a.position === "aboveBar" ? 1 : -1));
      lw.markers.setMarkers(mk);
      const dates = calls.map((c) => snapDate(c)).filter(Boolean).sort();
      if (bars.length) {
        const fi = dates.length ? lw.barIdx[dates[0]] : bars.length - 40;
        const from = bars[Math.max(0, fi - 20)].date;
        lw.chart.timeScale().setVisibleRange({ from, to: bars[bars.length - 1].date });
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

  function drawOverlays() {
    const svg = $("chart-overlay"), lanes = $("lanes-svg");
    if (!state.focus) { svg.innerHTML = ""; lanes.innerHTML = ""; return; }
    const calls = focusCalls();
    const plotW = lw.chart ? lw.chart.timeScale().width() : $("lanes").clientWidth;
    // rings around flips on the price line
    let ring = "";
    if (lw.chart && lw.bars.length) {
      const seen = new Set();
      calls.filter((c) => c.is_flip).forEach((c) => {
        const d = snapDate(c); if (!d || seen.has(d)) return; seen.add(d);
        const x = lw.chart.timeScale().timeToCoordinate(d);
        const y = lw.close.priceToCoordinate(lw.bars[lw.barIdx[d]].close);
        if (x == null || y == null || x < 0 || x > plotW) return;
        ring += `<circle cx="${x}" cy="${y}" r="9" fill="none" stroke="${FLIP}" stroke-width="2"/>`;
      });
    }
    svg.innerHTML = ring;
    // swimlanes: one row per creator
    const byCh = new Map();
    calls.slice().sort((a, b) => (a.date || "").localeCompare(b.date || "") || a.i - b.i).forEach((c) => {
      if (!c.date) return;
      if (!byCh.has(c.channel)) byCh.set(c.channel, []);
      byCh.get(c.channel).push(c);
    });
    const chans = Array.from(byCh.keys()).sort((a, b) => byCh.get(b).length - byCh.get(a).length || a.localeCompare(b));
    const rowH = 40, top = 6;
    const ds = calls.map((c) => c.date).filter(Boolean).sort();
    const range = ds.length ? [ds[0], ds[ds.length - 1]] : null;
    let out = "";
    chans.forEach((ch, r) => {
      const y = top + r * rowH + 22;
      out += `<text x="2" y="${y - 11}" fill="#8b95a8" font-size="11">${esc(ch)} <tspan fill="#5f6a7d">(${byCh.get(ch).length})</tspan></text>`;
      out += `<line x1="0" x2="${plotW}" y1="${y}" y2="${y}" stroke="#1d2330"/>`;
      const pts = byCh.get(ch).map((c) => ({ c, x: xOf(c.date, plotW, range) })).filter((p) => p.x != null);
      pts.forEach((p, k) => {
        const nx = k + 1 < pts.length ? pts[k + 1].x : plotW;
        const x0 = Math.max(0, Math.min(plotW, p.x)), x1 = Math.max(0, Math.min(plotW, nx));
        if (x1 > x0) out += `<line x1="${x0}" x2="${x1}" y1="${y}" y2="${y}" stroke="${COL[p.c.sentiment] || COL.unknown}" stroke-width="3" stroke-opacity="${k + 1 < pts.length ? 0.55 : 0.22}"/>`;
      });
      let lastFlipX = null, lastBelow = false;
      pts.forEach((p) => {
        if (p.x < 0 || p.x > plotW) return;
        const s = p.c.sentiment;
        out += `<text x="${p.x}" y="${y + 4}" text-anchor="middle" font-size="12" fill="${COL[s] || COL.unknown}"><title>${esc(`${p.c.date} · ${s}${p.c.summary ? " · " + p.c.summary : ""}`)}</title>${GLYPH[s] || "·"}</text>`;
        if (p.c.is_flip) {
          out += `<circle cx="${p.x}" cy="${y}" r="8.5" fill="none" stroke="${FLIP}" stroke-width="1.6"/>`;
          const lab = SHORT_TAG[p.c.flip_tag] || "flip";
          // alternate above/below when flips sit close together so tags don't collide
          const below = lastFlipX != null && p.x - lastFlipX < 64 && !lastBelow;
          lastBelow = below; lastFlipX = p.x;
          out += `<text x="${Math.min(plotW - 4, Math.max(4, p.x))}" y="${below ? y + 20 : y - 11}" text-anchor="${p.x > plotW - 40 ? "end" : p.x < 40 ? "start" : "middle"}" font-size="10" fill="${FLIP}"><title>${esc(TAG_LABEL[p.c.flip_tag] || "flip")}</title>⟲ ${esc(lab)}</text>`;
        }
      });
    });
    lanes.setAttribute("height", String(top + chans.length * rowH + 8));
    lanes.innerHTML = out || `<text x="4" y="20" fill="#5f6a7d" font-size="12">No calls in view.</text>`;
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
  function flipDefText(short) {
    const f = (state.scores && state.scores.flip_config) || {};
    const N = f.forward_sessions ?? 5, P = f.prior_sessions ?? 5;
    const am = f.ahead_min_move ? ` by more than ${pct(f.ahead_min_move, 1)}` : "";
    const pm = f.prior_min_move ? ` by more than ${pct(f.prior_min_move, 1)}` : "";
    const sp = f.vs_spy ? " (measured vs SPY)" : "";
    if (short) return `Ahead = moved the new way in the ${N} sessions after; after = it had already moved that way in the ${P} sessions before and then didn’t follow through.`;
    return `A flip is the same creator switching a ticker between ▲ bullish and ▼ bearish. Tags${sp}: ahead of move = over the ${N} sessions after the flip the stock moved the new way${am}. ` +
      `After the move = it did not, but in the ${P} sessions before the flip it had already moved that way${pm} (the creator flipped late). No follow-through = neither. ` +
      `Pending = fewer than ${N} sessions of prices yet. Working definition, not yet confirmed; settings live in scripts/flip_config.json.`;
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
      ["Pending", String(cnt("pending") + cnt("no_price")), cnt("no_price") ? `${cnt("no_price")} with no price data` : "not enough sessions yet", 99],
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
  function focusTicker(t) { state.focus = t; if (state.ticker && state.ticker !== t) { state.ticker = ""; $("ticker").value = ""; } setTab("timeline"); }
  function writeHash() { const h = `#tab=${state.tab}${state.focus ? `&t=${encodeURIComponent(state.focus)}` : ""}`; if (location.hash !== h) history.replaceState(null, "", h); }
  function readHash() { const p = new URLSearchParams(location.hash.slice(1)); if (p.get("t")) state.focus = p.get("t").toUpperCase(); if (p.get("tab")) state.tab = p.get("tab"); }

  function bind() {
    const on = (id, ev, fn) => $(id).addEventListener(ev, fn);
    ["from", "to", "channel", "ticker", "sentiment"].forEach((id) => on(id, "change", (e) => { state[id] = e.target.value; renderActive(); }));
    on("holdings", "click", () => { state.holdings = !state.holdings; $("holdings").setAttribute("aria-pressed", String(state.holdings)); renderActive(); });
    const setBasis = (b) => { state.basis = b; $("basis-raw").classList.toggle("on", b === "raw"); $("basis-spy").classList.toggle("on", b === "spy");
      $("basis-raw").setAttribute("aria-pressed", String(b === "raw")); $("basis-spy").setAttribute("aria-pressed", String(b === "spy")); renderActive(); };
    on("basis-raw", "click", () => setBasis("raw")); on("basis-spy", "click", () => setBasis("spy"));
    on("reset", "click", () => {
      Object.assign(state, { from: state.minDate, to: state.maxDate, channel: "", ticker: "", sentiment: "", holdings: false, search: "" });
      $("from").value = state.from; $("to").value = state.to; ["channel", "ticker", "sentiment"].forEach((id) => { $(id).value = ""; });
      $("tsearch").value = ""; $("holdings").setAttribute("aria-pressed", "false"); setBasis("raw");
    });
    on("tsearch", "input", (e) => { state.search = e.target.value; renderList(); });
    $("tlist").addEventListener("click", (e) => { const it = e.target.closest(".titem"); if (it) { state.focus = it.dataset.t; renderTimeline(); writeHash(); } });
    $("tlist").addEventListener("keydown", (e) => { if (e.key === "Enter") { const it = e.target.closest(".titem"); if (it) { state.focus = it.dataset.t; renderTimeline(); writeHash(); } } });
    document.body.addEventListener("click", (e) => { const f = e.target.closest("[data-focus]"); if (f && !e.target.closest("a")) focusTicker(f.dataset.focus); });
    document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
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

  async function init() {
    if (typeof Chart !== "undefined") { Chart.defaults.font.family = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'; Chart.defaults.color = "#8b95a8"; Chart.defaults.animation = false; }
    readHash(); bind();
    try {
      const raw = await fetchJson(cfg.dataUrl);
      state.mentions = (Array.isArray(raw) ? raw : (raw && raw.mentions) || []).map((r, i) => r && typeof r === "object" ? {
        i, ticker: String(r.ticker || "").trim().toUpperCase() || "—", channel: String(r.channel || "").trim() || "Unknown", date: String(r.date || "").trim().slice(0, 10),
        sentiment: String(r.sentiment || "").trim().toLowerCase() || "unknown", price_talk: String(r.price_talk || "").trim(), summary: String(r.summary || "").trim(),
        url: String(r.url || "").trim() || String(r.video_url || "").trim() } : null).filter(Boolean);
    } catch (e) { status(`Could not load mentions from ${cfg.dataUrl}: ${e.message}`, true); return; }
    const [sc, ins, px] = await Promise.allSettled([fetchJson(cfg.scoresUrl), fetchJson(cfg.insightsUrl), fetchJson(cfg.pricesUrl)]);
    state.scores = sc.status === "fulfilled" ? sc.value : null;
    state.insights = ins.status === "fulfilled" ? ins.value : null;
    state.prices = px.status === "fulfilled" ? px.value : null;
    if (state.scores && state.scores.thin_n) THIN = state.scores.thin_n;
    const errs = [[sc, "scores"], [ins, "insights"], [px, "prices"]].filter(([r]) => r.status !== "fulfilled").map(([r, n]) => `${n} (${r.reason && r.reason.message})`);
    if (errs.length) status(`Some data did not load: ${errs.join("; ")}. Run ./scripts/run_all.sh, then refresh.`, true);
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
