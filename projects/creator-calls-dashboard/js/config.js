/* Data paths. On Naman's machine, copy mentions.json into ./data/ (and
   regenerate scores/insights with scripts/run_all.sh). On this box,
   ./data/mentions.json is a symlink to the Ticker Tracker file. */
window.DASHBOARD_CONFIG = {
  dataUrl: "./data/mentions.json",
  scoresUrl: "./data/scores.json",
  insightsUrl: "./data/insights.json",
  pricesUrl: "./data/prices.json",
  holdings: []
};
