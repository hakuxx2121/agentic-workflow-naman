
(() => {
  const HOLDINGS = [];
  const SENT_ORDER = ["bullish", "bearish", "mixed", "neutral", "unknown"];
  const SENT_COLOR = {
    bullish: "#3ecf8e",
    bearish: "#f06470",
    mixed: "#e0b34c",
    neutral: "#7f8b9c",
    unknown: "#5c6573",
  };
  const cfg = Object.assign(
    { dataUrl: "../data/mentions.json", scoresUrl: "../data/scores.json", insightsUrl: "../data/insights.json" },
    window.DASHBOARD_CONFIG || {}
  );

  const state = {
    mentions: [],
    scores: null,
    insights: null,
    from: "",
    to: "",
    minDate: "",
    maxDate: "",
    channel: "",
    ticker: "",
    sentiment: "",
    holdings: false,
    sort: { key: "date", dir: -1 },
    scoreSort: { key: "date", dir: -1 },
    tab: "mentions",
  };
  const charts = {};

  function $(id) { return document.getElementById(id); }

  function showStatus(msg, isError) {
    const el = $("status");
    if (!msg) { el.hidden = true; el.textContent = ""; return; }
    el.hidden = false;
    el.textContent = msg;
    el.classList.toggle("error", !!isError);
  }

  function normalize(raw, i) {
    if (!raw || typeof raw !== "object") return null;
    const ticker = String(raw.ticker || "").trim().toUpperCase() || "—";
    const channel = String(raw.channel || "").trim() || "Unknown";
    const date = String(raw.date || "").trim();
    const sentiment = String(raw.sentiment || "").trim().toLowerCase() || "unknown";
    const price_talk = String(raw.price_talk || "").trim();
    const summary = String(raw.summary || "").trim();
    const title = String(raw.title || "").trim();
    let t = raw.t;
    t = t === null || t === undefined || t === "" ? null : Number(t);
    if (!Number.isFinite(t)) t = null;
    let url = String(raw.url || "").trim();
    const video_url = String(raw.video_url || "").trim();
    const video_id = String(raw.video_id || "").trim();
    if (!url) {
      const base = video_url || (video_id ? `https://www.youtube.com/watch?v=${video_id}` : "");
      if (base) url = t != null && t > 0 ? `${base}${base.includes("?") ? "&" : "?"}t=${t}s` : base;
    }
    return { i, ticker, channel, date, sentiment, price_talk, summary, title, t, url, holding: HOLDINGS.includes(ticker) };
  }

  function loadList(raw) {
    if (Array.isArray(raw)) return raw;
    if (raw && Array.isArray(raw.mentions)) return raw.mentions;
    return [];
  }

  async function fetchJson(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
    return res.json();
  }

  function uniqueSorted(arr) {
    return Array.from(new Set(arr)).sort((a, b) => a.localeCompare(b));
  }

  function fillSelect(sel, values, allLabel) {
    const cur = sel.value;
    sel.innerHTML = "";
    const opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = allLabel;
    sel.appendChild(opt0);
    values.forEach((v) => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = HOLDINGS.includes(v) ? `${v} · holding` : v;
      sel.appendChild(o);
    });
    if (values.includes(cur)) sel.value = cur;
  }

  function inFilters(row, { ignoreTicker = false } = {}) {
    if (state.from && row.date && row.date < state.from) return false;
    if (state.to && row.date && row.date > state.to) return false;
    if (state.channel && row.channel !== state.channel) return false;
    if (state.sentiment && row.sentiment !== state.sentiment) return false;
    if (state.holdings && !HOLDINGS.includes(row.ticker)) return false;
    if (!ignoreTicker && state.ticker && row.ticker !== state.ticker) return false;
    return true;
  }

  function filteredMentions() {
    return state.mentions.filter((r) => inFilters(r));
  }

  function ymd(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function daysBetween(from, to) {
    const out = [];
    if (!from || !to) return out;
    const a = new Date(from + "T00:00:00");
    const b = new Date(to + "T00:00:00");
    for (let d = new Date(a); d <= b; d.setDate(d.getDate() + 1)) {
      out.push(ymd(d));
    }
    return out;
  }

  function destroyChart(name) {
    if (charts[name]) { charts[name].destroy(); delete charts[name]; }
  }

  function baseOpts() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { labels: { boxWidth: 10, boxHeight: 10, color: "#8b95a8", font: { size: 11 } } },
        tooltip: {
          backgroundColor: "#1b212c",
          titleColor: "#e7ecf3",
          bodyColor: "#e7ecf3",
          borderColor: "#2a3140",
          borderWidth: 1,
        },
      },
      scales: {
        x: {
          ticks: { color: "#8b95a8", font: { size: 11 }, maxRotation: 40 },
          grid: { color: "rgba(255,255,255,0.04)" },
          border: { color: "#2a3140" },
        },
        y: {
          ticks: { color: "#8b95a8", font: { size: 11 } },
          grid: { color: "rgba(255,255,255,0.04)" },
          border: { color: "#2a3140" },
        },
      },
    };
  }

  function stackedCounts(rows, key, keys, limit) {
    const map = new Map();
    rows.forEach((r) => {
      const k = r[key] || "—";
      if (!map.has(k)) map.set(k, { total: 0, by: Object.fromEntries(SENT_ORDER.map((s) => [s, 0])) });
      const rec = map.get(k);
      rec.total += 1;
      rec.by[r.sentiment] = (rec.by[r.sentiment] || 0) + 1;
    });
    let labels = Array.from(map.keys());
    labels.sort((a, b) => map.get(b).total - map.get(a).total || a.localeCompare(b));
    if (limit) labels = labels.slice(0, limit);
    const datasets = keys.map((s) => ({
      label: s[0].toUpperCase() + s.slice(1),
      data: labels.map((l) => map.get(l).by[s] || 0),
      backgroundColor: SENT_COLOR[s],
      borderWidth: 0,
      stacked: true,
    }));
    return { labels, datasets, map };
  }

  function renderMentionsCharts(rows) {
    const tick = stackedCounts(rows, "ticker", SENT_ORDER, 15);
    $("cap-tickers").textContent = tick.labels.length
      ? `Top ${tick.labels.length} tickers by mention count, split by sentiment`
      : "No mentions in the current filters";
    destroyChart("tickers");
    charts.tickers = new Chart($("chart-tickers"), {
      type: "bar",
      data: { labels: tick.labels, datasets: tick.datasets },
      options: Object.assign(baseOpts(), {
        indexAxis: "y",
        scales: {
          x: { stacked: true, ticks: { color: "#8b95a8", font: { size: 11 }, precision: 0 }, grid: { color: "rgba(255,255,255,0.04)" }, border: { color: "#2a3140" } },
          y: { stacked: true, ticks: { color: "#e7ecf3", font: { size: 11, weight: "600" } }, grid: { display: false }, border: { color: "#2a3140" } },
        },
        onClick: (evt, els) => {
          if (!els.length) return;
          const label = charts.tickers.data.labels[els[0].index];
          $("ticker").value = label;
          state.ticker = label;
          renderAll();
        },
      }),
    });

    const ch = stackedCounts(rows, "channel", SENT_ORDER);
    destroyChart("channels");
    charts.channels = new Chart($("chart-channels"), {
      type: "bar",
      data: { labels: ch.labels, datasets: ch.datasets },
      options: Object.assign(baseOpts(), {
        indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: {
          x: { stacked: true, ticks: { color: "#8b95a8", font: { size: 11 }, precision: 0 }, grid: { color: "rgba(255,255,255,0.04)" }, border: { color: "#2a3140" } },
          y: { stacked: true, ticks: { color: "#e7ecf3", font: { size: 11, weight: "600" } }, grid: { display: false }, border: { color: "#2a3140" } },
        },
        onClick: (evt, els) => {
          if (!els.length) return;
          const label = charts.channels.data.labels[els[0].index];
          $("channel").value = label;
          state.channel = label;
          renderAll();
        },
      }),
    });

    const from = state.from || state.minDate;
    const to = state.to || state.maxDate;
    const days = daysBetween(from, to);
    const byDay = Object.fromEntries(SENT_ORDER.map((s) => [s, Object.fromEntries(days.map((d) => [d, 0]))]));
    rows.forEach((r) => {
      if (r.date && byDay[r.sentiment] && byDay[r.sentiment][r.date] !== undefined) {
        byDay[r.sentiment][r.date] += 1;
      } else if (r.date && days.includes(r.date)) {
        byDay.unknown[r.date] += 1;
      }
    });
    destroyChart("time");
    charts.time = new Chart($("chart-time"), {
      type: "bar",
      data: {
        labels: days,
        datasets: SENT_ORDER.filter((s) => s !== "unknown" || days.some((d) => byDay.unknown[d])).map((s) => ({
          label: s[0].toUpperCase() + s.slice(1),
          data: days.map((d) => byDay[s][d] || 0),
          backgroundColor: SENT_COLOR[s],
          borderWidth: 0,
        })),
      },
      options: Object.assign(baseOpts(), {
        scales: {
          x: { stacked: true, ticks: { color: "#8b95a8", font: { size: 10 }, maxRotation: 60, autoSkip: true }, grid: { display: false }, border: { color: "#2a3140" } },
          y: { stacked: true, ticks: { color: "#8b95a8", font: { size: 11 }, precision: 0 }, grid: { color: "rgba(255,255,255,0.04)" }, border: { color: "#2a3140" }, beginAtZero: true },
        },
      }),
    });
  }

  function cmp(a, b, key, dir) {
    const va = a[key], vb = b[key];
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va).localeCompare(String(vb)) * dir;
  }

  function sentBadge(s) {
    const cls = SENT_ORDER.includes(s) ? s : "unknown";
    return `<span class="sent ${cls}">${esc(s || "—")}</span>`;
  }

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function tickerCell(t) {
    const hold = HOLDINGS.includes(t);
    return `<span class="ticker">${esc(t)}</span>${hold ? '<span class="hold-mark">held</span>' : ""}`;
  }

  function linkCell(url) {
    if (!url) return "—";
    return `<a href="${esc(url)}" target="_blank" rel="noreferrer">Watch</a>`;
  }

  function renderMentionsTable(rows) {
    const key = state.sort.key, dir = state.sort.dir;
    const sorted = rows.slice().sort((a, b) => cmp(a, b, key, dir) || cmp(a, b, "ticker", 1) || a.i - b.i);
    $("table-count").textContent = `${rows.length} of ${state.mentions.length} mentions`;
    document.querySelectorAll("#tab-mentions th[data-sort]").forEach((th) => {
      th.classList.toggle("sorted", th.dataset.sort === key);
    });
    $("mentions-body").innerHTML = sorted.map((r) => `
      <tr class="${r.holding ? "holding" : ""}">
        <td>${esc(r.date || "—")}</td>
        <td>${esc(r.channel)}</td>
        <td class="ticker">${tickerCell(r.ticker)}</td>
        <td>${sentBadge(r.sentiment)}</td>
        <td class="price">${esc(r.price_talk || "—")}</td>
        <td class="summary">${esc(r.summary || "—")}</td>
        <td>${linkCell(r.url)}</td>
      </tr>
    `).join("") || `<tr><td colspan="7">No mentions match these filters.</td></tr>`;
  }

  function pct(x, d = 0) {
    if (x == null || Number.isNaN(x)) return "—";
    return `${(x * 100).toFixed(d)}%`;
  }

  function retCell(x) {
    if (x == null) return `<span class="pending">—</span>`;
    const cls = x > 0 ? "pos" : x < 0 ? "neg" : "";
    const sign = x > 0 ? "+" : "";
    return `<span class="num ${cls}">${sign}${(x * 100).toFixed(1)}%</span>`;
  }

  function hitCell(v, pending) {
    if (pending || v == null) return `<span class="pending">pending</span>`;
    return v ? `<span class="pos">hit</span>` : `<span class="neg">miss</span>`;
  }

  function scoreRows() {
    if (!state.scores || !Array.isArray(state.scores.calls)) return [];
    return state.scores.calls.filter((c) => inFilters({
      date: c.date, channel: c.channel, ticker: c.ticker, sentiment: c.sentiment,
    }));
  }

  function renderScorecard() {
    const box = $("score-kpis");
    if (!state.scores) {
      box.innerHTML = "";
      $("score-count").textContent = "";
      $("score-body").innerHTML = `<tr><td colspan="9">Scorecard data is missing. From this folder run <code>./scripts/run_all.sh</code> then refresh.</td></tr>`;
      destroyChart("scoreCh");
      return;
    }
    const rows = scoreRows();
    const d5 = rows.filter((c) => c.directional && c.hit_5d != null && !c.pending_5d);
    const d1 = rows.filter((c) => c.directional && c.hit_1d != null && !c.pending_1d);
    const hr = (xs, k) => xs.length ? xs.filter((c) => c[k]).length / xs.length : null;
    const s = state.scores.summary || {};
    box.innerHTML = [
      ["5d hit rate", pct(hr(d5, "hit_5d"), 0), `${d5.length} scored calls`],
      ["1d hit rate", pct(hr(d1, "hit_1d"), 0), `${d1.length} scored calls`],
      ["5d vs SPY", pct(hr(d5.filter((c) => c.hit_5d_spy != null), "hit_5d_spy"), 0), "excess-return hits"],
      ["Pending 5d", String(rows.filter((c) => c.directional && c.pending_5d).length), "not enough sessions yet"],
    ].map(([label, value, hint]) => `<div class="card"><p class="label">${label}</p><p class="value">${value}</p><p class="hint">${hint}</p></div>`).join("");

    // hit rate by channel from filtered rows
    const by = new Map();
    d5.concat([]);
    rows.forEach((c) => {
      if (!c.channel) return;
      if (!by.has(c.channel)) by.set(c.channel, { n5: 0, h5: 0, n1: 0, h1: 0 });
      const rec = by.get(c.channel);
      if (c.directional && c.hit_5d != null && !c.pending_5d) { rec.n5 += 1; if (c.hit_5d) rec.h5 += 1; }
      if (c.directional && c.hit_1d != null && !c.pending_1d) { rec.n1 += 1; if (c.hit_1d) rec.h1 += 1; }
    });
    const labels = Array.from(by.keys()).sort();
    destroyChart("scoreCh");
    charts.scoreCh = new Chart($("chart-score-channel"), {
      type: "bar",
      data: {
        labels,
        datasets: [
          { label: "5d hit rate", data: labels.map((l) => by.get(l).n5 ? by.get(l).h5 / by.get(l).n5 : null), backgroundColor: "#7aa2ff", borderWidth: 0 },
          { label: "1d hit rate", data: labels.map((l) => by.get(l).n1 ? by.get(l).h1 / by.get(l).n1 : null), backgroundColor: "#3ecf8e", borderWidth: 0 },
        ],
      },
      options: Object.assign(baseOpts(), {
        indexAxis: "y",
        scales: {
          x: { min: 0, max: 1, ticks: { color: "#8b95a8", callback: (v) => `${Math.round(v * 100)}%` }, grid: { color: "rgba(255,255,255,0.04)" }, border: { color: "#2a3140" } },
          y: { ticks: { color: "#e7ecf3", font: { size: 11, weight: "600" } }, grid: { display: false }, border: { color: "#2a3140" } },
        },
        plugins: Object.assign(baseOpts().plugins, {
          tooltip: Object.assign(baseOpts().plugins.tooltip, {
            callbacks: {
              label: (ctx) => {
                const rec = by.get(ctx.label);
                const n = ctx.dataset.label.startsWith("5d") ? rec.n5 : rec.n1;
                return `${ctx.dataset.label}: ${pct(ctx.raw, 0)} (n=${n})`;
              },
            },
          }),
        }),
      }),
    });

    const key = state.scoreSort.key, dir = state.scoreSort.dir;
    const sorted = rows.slice().sort((a, b) => cmp(a, b, key, dir) || cmp(a, b, "ticker", 1));
    $("score-count").textContent = `${rows.length} rows in view · overall 5d ${pct(s.hit_rate_5d, 0)} (n=${s.n_5d || 0})`;
    $("score-body").innerHTML = sorted.map((c) => `
      <tr class="${HOLDINGS.includes(c.ticker) ? "holding" : ""}">
        <td>${esc(c.date || "—")}</td>
        <td>${esc(c.channel)}</td>
        <td class="ticker">${tickerCell(c.ticker)}</td>
        <td>${sentBadge(c.sentiment)}</td>
        <td>${retCell(c.ret_1d)}</td>
        <td>${retCell(c.ret_5d)}</td>
        <td>${hitCell(c.hit_5d, c.pending_5d)}</td>
        <td>${retCell(c.ex_5d)}</td>
        <td>${linkCell(c.url)}</td>
      </tr>
    `).join("") || `<tr><td colspan="9">No scored calls match these filters.</td></tr>`;
  }

  function renderFlips() {
    const box = $("flip-kpis");
    if (!state.scores) {
      box.innerHTML = "";
      $("flip-body").innerHTML = `<tr><td colspan="8">Run <code>./scripts/run_all.sh</code> to build flip scores, then refresh.</td></tr>`;
      return;
    }
    let flips = (state.scores.flips || []).filter((f) => inFilters({
      date: f.date, channel: f.channel, ticker: f.ticker, sentiment: f.to,
    }));
    const n1 = flips.filter((f) => f.hit_1d != null).length;
    const h1 = flips.filter((f) => f.hit_1d).length;
    const n5 = flips.filter((f) => f.hit_5d != null).length;
    const h5 = flips.filter((f) => f.hit_5d).length;
    box.innerHTML = [
      ["Flips in view", String(flips.length), `${(state.scores.flips || []).length} in the full file`],
      ["1d hit rate", n1 ? pct(h1 / n1, 0) : "—", n1 ? `${h1} of n=${n1}` : "not enough sessions"],
      ["5d hit rate", n5 ? pct(h5 / n5, 0) : "—", n5 ? `${h5} of n=${n5}` : "too few finished 5d flips"],
    ].map(([label, value, hint]) => `<div class="card"><p class="label">${label}</p><p class="value">${value}</p><p class="hint">${hint}</p></div>`).join("");
    $("flip-count").textContent = `${flips.length} flips`;
    $("flip-body").innerHTML = flips.map((f) => `
      <tr class="${HOLDINGS.includes(f.ticker) ? "holding" : ""}">
        <td>${esc(f.date || "—")}</td>
        <td>${esc(f.channel)}</td>
        <td class="ticker">${tickerCell(f.ticker)}</td>
        <td>${sentBadge(f.from)}</td>
        <td>${sentBadge(f.to)}</td>
        <td>${esc(f.prev_date || "—")}</td>
        <td>${hitCell(f.hit_1d, f.hit_1d == null)} / ${hitCell(f.hit_5d, f.hit_5d == null)}</td>
        <td>${linkCell(f.url)}</td>
      </tr>
    `).join("") || `<tr><td colspan="8">No flips match these filters.</td></tr>`;
  }

  function renderReaction() {
    const box = $("react-kpis");
    if (!state.scores) {
      box.innerHTML = "";
      destroyChart("reactMean"); destroyChart("reactPos");
      showStatus($("status").textContent, $("status").classList.contains("error"));
      return;
    }
    const rows = scoreRows().filter((c) => c.ret_1d != null);
    const by = {};
    SENT_ORDER.forEach((s) => { by[s] = []; });
    rows.forEach((c) => { (by[c.sentiment] || (by[c.sentiment] = [])).push(c.ret_1d); });
    const labels = SENT_ORDER.filter((s) => (by[s] || []).length);
    const means = labels.map((s) => { const xs = by[s]; return xs.reduce((a, b) => a + b, 0) / xs.length; });
    const pos = labels.map((s) => { const xs = by[s]; return xs.filter((x) => x > 0).length / xs.length; });
    const ns = labels.map((s) => by[s].length);
    const all = rows.map((c) => c.ret_1d);
    const meanAll = all.length ? all.reduce((a, b) => a + b, 0) / all.length : null;
    box.innerHTML = [
      ["Mentions with a next session", String(all.length), ""],
      ["Mean next-session return", meanAll == null ? "—" : `${meanAll >= 0 ? "+" : ""}${(meanAll * 100).toFixed(2)}%`, "all sentiments"],
      ["Share up next session", all.length ? pct(all.filter((x) => x > 0).length / all.length, 0) : "—", ""],
    ].map(([label, value, hint]) => `<div class="card"><p class="label">${label}</p><p class="value">${value}</p><p class="hint">${hint}</p></div>`).join("");

    destroyChart("reactMean");
    charts.reactMean = new Chart($("chart-react-mean"), {
      type: "bar",
      data: { labels: labels.map((s) => s[0].toUpperCase() + s.slice(1)), datasets: [{ label: "Mean return", data: means, backgroundColor: labels.map((s) => SENT_COLOR[s]), borderWidth: 0 }] },
      options: Object.assign(baseOpts(), {
        plugins: { legend: { display: false }, tooltip: Object.assign(baseOpts().plugins.tooltip, { callbacks: { label: (c) => `mean ${pct(c.raw, 2)} (n=${ns[c.dataIndex]})` } }) },
        scales: {
          x: { ticks: { color: "#e7ecf3" }, grid: { display: false }, border: { color: "#2a3140" } },
          y: { ticks: { color: "#8b95a8", callback: (v) => `${(v * 100).toFixed(1)}%` }, grid: { color: "rgba(255,255,255,0.04)" }, border: { color: "#2a3140" } },
        },
      }),
    });
    destroyChart("reactPos");
    charts.reactPos = new Chart($("chart-react-pos"), {
      type: "bar",
      data: { labels: labels.map((s) => s[0].toUpperCase() + s.slice(1)), datasets: [{ label: "Share up", data: pos, backgroundColor: labels.map((s) => SENT_COLOR[s]), borderWidth: 0 }] },
      options: Object.assign(baseOpts(), {
        plugins: { legend: { display: false }, tooltip: Object.assign(baseOpts().plugins.tooltip, { callbacks: { label: (c) => `${pct(c.raw, 0)} up (n=${ns[c.dataIndex]})` } }) },
        scales: {
          x: { ticks: { color: "#e7ecf3" }, grid: { display: false }, border: { color: "#2a3140" } },
          y: { min: 0, max: 1, ticks: { color: "#8b95a8", callback: (v) => `${Math.round(v * 100)}%` }, grid: { color: "rgba(255,255,255,0.04)" }, border: { color: "#2a3140" } },
        },
      }),
    });
  }

  function insightChart(canvas, spec) {
    const fmt = spec.y_format || "percent";
    const nLabels = spec.n_labels;
    const tick = (v) => fmt === "percent" ? `${Math.round(v * 100)}%` : v;
    const datasets = (spec.datasets || []).map((d) => ({
      label: d.label,
      data: d.values,
      backgroundColor: d.colors && d.colors.length ? d.colors : "#7aa2ff",
      borderWidth: 0,
    }));
    const manyLabels = (spec.labels || []).some((l) => String(l).length > 14) || (spec.labels || []).length > 6;
    return new Chart(canvas, {
      type: spec.type || "bar",
      data: { labels: spec.labels || [], datasets },
      options: Object.assign(baseOpts(), {
        indexAxis: manyLabels ? "y" : "x",
        plugins: Object.assign(baseOpts().plugins, {
          tooltip: Object.assign(baseOpts().plugins.tooltip, {
            callbacks: {
              label: (c) => {
                const n = nLabels ? nLabels[c.dataIndex] : null;
                const val = fmt === "percent" ? pct(c.raw, 0) : c.raw;
                return `${c.dataset.label}: ${val}${n != null ? ` (n=${n})` : ""}`;
              },
            },
          }),
        }),
        scales: manyLabels ? {
          x: { ticks: { color: "#8b95a8", callback: tick, font: { size: 11 } }, grid: { color: "rgba(255,255,255,0.04)" }, border: { color: "#2a3140" }, beginAtZero: true },
          y: { ticks: { color: "#e7ecf3", font: { size: 11 } }, grid: { display: false }, border: { color: "#2a3140" } },
        } : {
          x: { ticks: { color: "#8b95a8", font: { size: 11 }, maxRotation: 30 }, grid: { display: false }, border: { color: "#2a3140" } },
          y: { ticks: { color: "#8b95a8", callback: tick }, grid: { color: "rgba(255,255,255,0.04)" }, border: { color: "#2a3140" }, beginAtZero: true },
        },
      }),
    });
  }

  function renderInsights() {
    const list = $("insights-list");
    // destroy previous insight charts
    Object.keys(charts).filter((k) => k.startsWith("ins-")).forEach(destroyChart);
    if (!state.insights || !Array.isArray(state.insights.findings)) {
      list.innerHTML = `<p class="status">Insights are missing. From this folder run <code>./scripts/run_all.sh</code> then refresh.</p>`;
      return;
    }
    const d = $("insights-disclaimer");
    d.textContent = state.insights.disclaimer || d.textContent;
    list.innerHTML = state.insights.findings.map((f, i) => {
      const flag = f.flag ? `<span class="badge warn">${esc(f.flag)}</span>` : (f.significant ? `<span class="badge note">statistically notable</span>` : "");
      const pv = f.p_value == null ? "" : `<span class="badge">p=${Number(f.p_value).toFixed(2)}</span>`;
      const hv = f.horizon ? `<span class="badge">${esc(f.horizon)} horizon</span>` : "";
      return `<article class="card insight">
        <div class="meta">
          <span class="badge">#${f.rank || i + 1}</span>
          <span class="badge">n=${f.n}</span>
          ${hv}${pv}${flag}
        </div>
        <h2>${esc(f.title)}</h2>
        <p class="sentence">${esc(f.sentence)}</p>
        <div class="chart-box"><canvas id="ins-c-${i}"></canvas></div>
      </article>`;
    }).join("");
    state.insights.findings.forEach((f, i) => {
      const canvas = $(`ins-c-${i}`);
      if (canvas && f.chart) charts[`ins-${i}`] = insightChart(canvas, f.chart);
    });
  }

  function renderStats() {
    const rows = state.mentions;
    const dates = rows.map((r) => r.date).filter(Boolean).sort();
    const ch = uniqueSorted(rows.map((r) => r.channel));
    const tk = uniqueSorted(rows.map((r) => r.ticker));
    $("stats").innerHTML = [
      `${rows.length} mentions`,
      dates.length ? `${dates[0]} → ${dates[dates.length - 1]}` : "no dates",
      `${ch.length} channels`,
      `${tk.length} tickers`,
    ].map((t) => `<span class="chip"><strong>${esc(t.split(" ")[0])}</strong> ${esc(t.split(" ").slice(1).join(" "))}</span>`).join("");
    // The chip split is clumsy when the first token is a date range. Just use plain chips:
    $("stats").innerHTML = [
      `<strong>${rows.length}</strong> mentions`,
      dates.length ? `<strong>${dates[0]}</strong> to <strong>${dates[dates.length - 1]}</strong>` : "no dates",
      `<strong>${ch.length}</strong> channels`,
      `<strong>${tk.length}</strong> tickers`,
    ].map((t) => `<span class="chip">${t}</span>`).join("");
  }

  function renderAll() {
    const rows = filteredMentions();
    renderMentionsCharts(rows);
    renderMentionsTable(rows);
    if (state.tab === "scorecard" || charts.scoreCh) renderScorecard();
    if (state.tab === "flips") renderFlips();
    if (state.tab === "reaction" || charts.reactMean) renderReaction();
    // insights are not filter-dependent (precomputed); already drawn once
  }

  function bind() {
    $("from").addEventListener("change", (e) => { state.from = e.target.value; renderAll(); });
    $("to").addEventListener("change", (e) => { state.to = e.target.value; renderAll(); });
    $("channel").addEventListener("change", (e) => { state.channel = e.target.value; renderAll(); });
    $("ticker").addEventListener("change", (e) => { state.ticker = e.target.value; renderAll(); });
    $("sentiment").addEventListener("change", (e) => { state.sentiment = e.target.value; renderAll(); });
    $("holdings").addEventListener("click", () => {
      state.holdings = !state.holdings;
      $("holdings").setAttribute("aria-pressed", String(state.holdings));
      renderAll();
    });
    $("reset").addEventListener("click", () => {
      state.from = state.minDate;
      state.to = state.maxDate;
      state.channel = state.ticker = state.sentiment = "";
      state.holdings = false;
      $("from").value = state.from;
      $("to").value = state.to;
      $("channel").value = "";
      $("ticker").value = "";
      $("sentiment").value = "";
      $("holdings").setAttribute("aria-pressed", "false");
      renderAll();
    });
    document.querySelectorAll("#tab-mentions th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (state.sort.key === key) state.sort.dir *= -1;
        else state.sort = { key, dir: key === "date" ? -1 : 1 };
        renderMentionsTable(filteredMentions());
      });
    });
    document.querySelectorAll("#tab-scorecard th[data-sort-score]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sortScore;
        if (state.scoreSort.key === key) state.scoreSort.dir *= -1;
        else state.scoreSort = { key, dir: key === "date" ? -1 : 1 };
        renderScorecard();
      });
    });
    document.querySelectorAll(".tabs button").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.tab = btn.dataset.tab;
        document.querySelectorAll(".tabs button").forEach((b) => {
          b.classList.toggle("active", b === btn);
          b.setAttribute("aria-selected", String(b === btn));
        });
        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${state.tab}`));
        if (state.tab === "scorecard") renderScorecard();
        if (state.tab === "flips") renderFlips();
        if (state.tab === "reaction") renderReaction();
        if (state.tab === "insights") renderInsights();
      });
    });
  }

  async function init() {
    if (typeof Chart !== "undefined") {
      Chart.defaults.font.family = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
      Chart.defaults.color = "#8b95a8";
      Chart.defaults.animation = false;
    }
    bind();
    try {
      const raw = await fetchJson(cfg.dataUrl);
      const list = loadList(raw);
      state.mentions = list.map(normalize).filter(Boolean);
      if (!state.mentions.length) showStatus("No mentions in the data file.", true);
    } catch (err) {
      showStatus(`Could not load mentions from ${cfg.dataUrl}: ${err.message}`, true);
      return;
    }
    try { state.scores = await fetchJson(cfg.scoresUrl); }
    catch (err) { state.scores = null; console.warn("scores not loaded", err); }
    try { state.insights = await fetchJson(cfg.insightsUrl); }
    catch (err) { state.insights = null; console.warn("insights not loaded", err); }

    const dates = state.mentions.map((r) => r.date).filter(Boolean).sort();
    state.minDate = dates[0] || "";
    state.maxDate = dates[dates.length - 1] || "";
    state.from = state.minDate;
    state.to = state.maxDate;
    $("from").value = state.from;
    $("to").value = state.to;
    fillSelect($("channel"), uniqueSorted(state.mentions.map((r) => r.channel)), "All channels");
    fillSelect($("ticker"), uniqueSorted(state.mentions.map((r) => r.ticker)), "All tickers");
    renderStats();
    renderAll();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
