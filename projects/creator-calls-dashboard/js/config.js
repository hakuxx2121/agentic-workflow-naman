/* Data paths. Copy mentions.json into ./data/ (and
   regenerate scores/insights with scripts/run_all.sh). */
window.DASHBOARD_CONFIG = {
  dataUrl: "./data/mentions.json",
  scoresUrl: "./data/scores.json",
  insightsUrl: "./data/insights.json",
  pricesUrl: "./data/prices.json",
  // Example placeholder only. Replace with your own symbols, or use [].
  holdings: ["AAPL"]
};
