/* Freshness banner: scores.json generated_at vs now. No network. */
(function (root) {
  const STALE_AFTER_HOURS = 26;
  function freshnessBanner(generatedAt, nowMs) {
    if (nowMs == null) nowMs = Date.now();
    if (generatedAt == null || generatedAt === "") return "Data age unknown";
    const then = Date.parse(generatedAt);
    if (!Number.isFinite(then)) return "Data age unknown";
    const hoursExact = (nowMs - then) / 3600000;
    if (hoursExact > STALE_AFTER_HOURS) {
      return "Data is stale: last scored " + Math.floor(hoursExact) + " hours ago.";
    }
    return null;
  }
  root.freshnessBanner = freshnessBanner;
  root.STALE_AFTER_HOURS = STALE_AFTER_HOURS;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { freshnessBanner, STALE_AFTER_HOURS };
  }
})(typeof window !== "undefined" ? window : globalThis);
