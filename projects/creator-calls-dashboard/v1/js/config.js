/* Data paths. This archived v1 UI must be served from the parent folder
   (http://localhost:8000/v1/). On Naman's machine the JSON lives in ../data/.
   On this box, ../data/mentions.json is a symlink to the Ticker Tracker file. */
window.DASHBOARD_CONFIG = {
  dataUrl: "../data/mentions.json",
  scoresUrl: "../data/scores.json",
  insightsUrl: "../data/insights.json"
};
