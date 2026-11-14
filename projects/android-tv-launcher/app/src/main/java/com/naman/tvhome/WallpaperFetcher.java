package com.naman.tvhome;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.BitmapFactory;
import android.util.Log;
import org.json.*;
import java.io.*;
import java.net.*;
import java.util.*;

/**
 * Weekly Wikimedia Commons Featured-pictures wallpaper fetcher. Plain Thread, no libraries.
 * Gentle on the API: one generator=categorymembers+imageinfo call per group (6 groups, ~6-8 calls),
 * >=1s between requests, honours Retry-After, backs off 5s/15s/45s.
 */
final class WallpaperFetcher {
    static final String UA = "NamanTVHome/1.0 (personal TV launcher; com.naman.tvhome)";
    static final String TAG = "TVHomeWall";
    static final String API = "https://commons.wikimedia.org/w/api.php?";
    static final long WEEK = 7L * 24 * 3600 * 1000, RETRY = 6L * 3600 * 1000, RETRY_429 = 3600L * 1000;
    static final long MIN_GAP_MS = 1000, THUMB_GAP_MS = 1500;
    static final long[] BACKOFF_MS = {5000, 15000, 45000};
    static final int COUNT = 8, MIN_OK = 4, PER_CALL = 50, MAX_API_CALLS = 10;
    static final int RECENT_KEEP = 40; // ~5 weeks
    static volatile boolean running;
    static int apiCalls, httpRequests;
    static long lastRequestAt;

    /** Thrown when Commons rate-limits us; triggers the shorter 1h retry. */
    static final class RateLimited extends IOException { RateLimited(String m) { super(m); } }

    // Each group: label, then candidate categories (one is chosen at random per refresh => 1 call per group).
    static final String[][] GROUPS = {
        {"Landscapes", "Featured pictures of landscapes", "Featured pictures of mountains", "Featured pictures of lakes", "Featured pictures of coasts"},
        {"Nature", "Featured pictures of waterfalls", "Featured pictures of forests", "Featured pictures of astronomy"},
        {"Architecture", "Featured pictures of buildings", "Featured pictures of architecture"},
        {"Cars", "Featured pictures of automobiles"},
        {"Flowers", "Featured pictures of flowers"},
        // Featured pictures of birds holds only subcategories; these were verified to exist (Nov 2026).
        {"Birds", "Featured pictures of birds in flight", "Featured pictures of Accipitriformes", "Featured pictures of Anseriformes",
                  "Featured pictures of Charadriiformes", "Featured pictures of Pelecaniformes", "Featured pictures of Coraciiformes",
                  "Featured pictures of Psittaciformes", "Featured pictures of Strigiformes", "Featured pictures of Phoenicopteriformes",
                  "Featured pictures of Passeriformes"},
    };
    static final java.util.regex.Pattern BAD = java.util.regex.Pattern.compile("(?i)\\bmaps?\\b|diagram|chart|portrait|\\bplan\\b");

    static File cacheDir(Context c) { return new File(c.getFilesDir(), "wall"); }

    static List<File> cached(Context c) {
        List<File> out = new ArrayList<>();
        File[] fs = cacheDir(c).listFiles();
        if (fs != null) for (File f : fs) if (f.getName().endsWith(".jpg")) out.add(f);
        Collections.sort(out);
        return out;
    }

    static Map<String, String> captions(Context c) {
        Map<String, String> m = new HashMap<>();
        try {
            JSONObject o = new JSONObject(readAll(new FileInputStream(new File(cacheDir(c), "meta.json"))));
            for (Iterator<String> it = o.keys(); it.hasNext(); ) { String k = it.next(); m.put(k, o.getString(k)); }
        } catch (Exception ignored) {}
        return m;
    }

    static void maybeRefresh(final Context ctx, boolean force, final Runnable onDone) {
        final SharedPreferences p = ctx.getSharedPreferences("home", Context.MODE_PRIVATE);
        long now = System.currentTimeMillis();
        boolean have = !cached(ctx).isEmpty();
        if (!force) {
            long ok = p.getLong("wallOk", 0), fail = p.getLong("wallFail", 0), wait = p.getLong("wallFailWait", RETRY);
            if (have && now - ok < WEEK) { Log.i(TAG, "skip: last success " + (now - ok) / 3600000 + "h ago"); return; }
            if (now - fail < wait) { Log.i(TAG, "skip: last failure " + (now - fail) / 60000 + "min ago (retry after " + wait / 60000 + "min)"); return; }
        }
        if (running) { Log.i(TAG, "skip: fetch already running"); return; }
        Log.i(TAG, "start fetch force=" + force + " haveCache=" + have);
        running = true;
        final Context app = ctx.getApplicationContext();
        Thread t = new Thread(() -> {
            try {
                long t0 = System.currentTimeMillis();
                fetch(app);
                Log.i(TAG, "SUCCESS in " + (System.currentTimeMillis() - t0) / 1000 + "s, " + apiCalls + " API calls, " + httpRequests + " HTTP requests");
                p.edit().putLong("wallOk", System.currentTimeMillis()).remove("wallFail").remove("wallFailWait").apply();
                if (onDone != null) onDone.run();
            } catch (Throwable e) {
                boolean rl = e instanceof RateLimited;
                Log.e(TAG, "FAILED (" + (rl ? "rate-limited, retry in 1h" : "retry in 6h") + "): " + e, e);
                p.edit().putLong("wallFail", System.currentTimeMillis()).putLong("wallFailWait", rl ? RETRY_429 : RETRY).apply();
            } finally { running = false; }
        }, "wall-fetch");
        t.setPriority(Thread.MIN_PRIORITY);
        t.start();
    }

    static final class Cand { String title, url, caption, group; }

    /** One API call: up to 50 files of a category with size, mime, 1920px thumb URL and attribution. */
    static List<Cand> listGroup(String group, String cat, Random rnd, Set<String> recent) throws Exception {
        // Random window into the category so each week sees different files without extra calls.
        String[] sorts = {"&gcmsort=timestamp&gcmdir=" + (rnd.nextBoolean() ? "asc" : "desc"), "&gcmsort=sortkey&gcmdir=" + (rnd.nextBoolean() ? "asc" : "desc")};
        String sort = sorts[rnd.nextInt(2)];
        if (sort.contains("timestamp")) {
            long from = 1199145600000L, to = System.currentTimeMillis(); // 2008-01-01 .. now
            long ts = from + (long) (rnd.nextDouble() * (to - from));
            sort += "&gcmstart=" + new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US) {{ setTimeZone(TimeZone.getTimeZone("UTC")); }}.format(new Date(ts));
        } else {
            sort += "&gcmstartsortkeyprefix=" + (char) ('A' + rnd.nextInt(26));
        }
        List<Cand> out = parse(group, apiCall(base(cat) + sort), recent);
        Log.i(TAG, "group " + group + " [" + cat + "]: " + out.size() + " usable candidates");
        return out;
    }

    static String base(String cat) throws Exception {
        return API + "action=query&format=json&generator=categorymembers&gcmtype=file&gcmlimit=" + PER_CALL
                + "&gcmtitle=" + enc("Category:" + cat)
                + "&prop=imageinfo&iiprop=" + enc("size|mime|url|extmetadata") + "&iiurlwidth=1920"
                + "&iiextmetadatafilter=" + enc("LicenseShortName|Artist|ObjectName");
    }

    static List<Cand> parse(String group, JSONObject r, Set<String> recent) throws JSONException {
        List<Cand> out = new ArrayList<>();
        JSONObject q = r.optJSONObject("query");
        if (q == null) return out;
        JSONObject pages = q.getJSONObject("pages");
        for (Iterator<String> it = pages.keys(); it.hasNext(); ) {
            JSONObject pg = pages.getJSONObject(it.next());
            JSONArray ia = pg.optJSONArray("imageinfo");
            String t = pg.optString("title");
            if (ia == null || recent.contains(t) || BAD.matcher(t).find()) continue;
            JSONObject ii = ia.getJSONObject(0);
            int w = ii.optInt("width"), h = ii.optInt("height");
            String url = ii.optString("thumburl", "");
            if (!"image/jpeg".equals(ii.optString("mime")) || url.isEmpty() || w < 3000 || h <= 0 || w < h * 1.5 || w > h * 2.4) continue;
            JSONObject m = ii.optJSONObject("extmetadata");
            String title = clean(meta(m, "ObjectName"));
            if (title.isEmpty()) title = t.substring(5).replaceAll("\\.[A-Za-z]+$", "").replace('_', ' ');
            String artist = clean(meta(m, "Artist")), lic = clean(meta(m, "LicenseShortName"));
            Cand c = new Cand();
            c.title = t; c.url = url; c.group = group;
            c.caption = cut(title, 70) + (artist.isEmpty() ? "" : " · " + cut(artist, 40)) + (lic.isEmpty() ? "" : " · " + lic) + " · Wikimedia Commons";
            out.add(c);
        }
        return out;
    }

    static void fetch(Context c) throws Exception {
        apiCalls = 0; httpRequests = 0;
        SharedPreferences prefs = c.getSharedPreferences("home", Context.MODE_PRIVATE);
        List<String> recent = new ArrayList<>(Arrays.asList(prefs.getString("wallRecent", "").split("\n")));
        Set<String> recentSet = new HashSet<>(recent);
        Random rnd = new Random();
        List<String[]> groups = new ArrayList<>(Arrays.asList(GROUPS));
        Collections.shuffle(groups, rnd);

        // 1. one call per group; a failing group is skipped (partial success)
        List<List<Cand>> perGroup = new ArrayList<>();
        Exception lastErr = null;
        for (String[] g : groups) {
            if (apiCalls >= MAX_API_CALLS) break;
            String cat = g[1 + rnd.nextInt(g.length - 1)];
            try {
                List<Cand> l = listGroup(g[0], cat, rnd, recentSet);
                if (l.size() < 2 && apiCalls < MAX_API_CALLS - 1) { // window too thin: retry once from the start of the category
                    l.addAll(parse(g[0], apiCall(base(cat)), recentSet));
                    Log.i(TAG, "group " + g[0] + " refill from start: " + l.size() + " candidates");
                }
                Collections.shuffle(l, rnd);
                perGroup.add(l);
            } catch (RateLimited e) {
                Log.e(TAG, "group " + g[0] + " rate-limited, stopping API calls: " + e.getMessage());
                lastErr = e; break; // don't keep hammering
            } catch (Exception e) {
                Log.e(TAG, "group " + g[0] + " failed: " + e);
                lastErr = e;
            }
        }

        // 2. round-robin across groups for an even mix; groups with spare candidates fill gaps
        List<Cand> picks = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (int round = 0; picks.size() < COUNT; round++) {
            boolean any = false;
            for (List<Cand> l : perGroup) {
                if (picks.size() >= COUNT) break;
                while (round < l.size() && seen.contains(l.get(round).title)) l.remove(round);
                if (round < l.size()) { Cand cd = l.get(round); seen.add(cd.title); picks.add(cd); any = true; }
            }
            if (!any) break;
        }
        StringBuilder sb = new StringBuilder();
        for (Cand cd : picks) sb.append(cd.group).append(", ");
        Log.i(TAG, "picked " + picks.size() + " from " + perGroup.size() + "/" + groups.size() + " groups (" + apiCalls + " API calls): " + sb);
        if (picks.size() < MIN_OK) {
            if (lastErr != null) throw lastErr;
            throw new IOException("too few images: " + picks.size());
        }
        Collections.shuffle(picks, rnd);

        // 3. sequential thumbnail downloads with a pause; a failed thumb is skipped if enough remain
        File files = c.getFilesDir();
        File tmp = new File(files, "wall_tmp");
        deleteTree(tmp);
        if (!tmp.mkdirs()) throw new IOException("mkdir");
        JSONObject meta = new JSONObject();
        List<String> shown = new ArrayList<>();
        int n = 0;
        for (Cand cd : picks) {
            String name = String.format(Locale.US, "w%02d.jpg", n);
            File f = new File(tmp, name);
            try {
                download(cd.url, f);
                BitmapFactory.Options o = new BitmapFactory.Options();
                o.inJustDecodeBounds = true;
                BitmapFactory.decodeFile(f.getPath(), o);
                if (o.outWidth <= 0) throw new IOException("not decodable");
                Log.i(TAG, "downloaded " + name + " " + f.length() / 1024 + "KB " + o.outWidth + "x" + o.outHeight + " [" + cd.group + "] " + cd.title);
                meta.put(name, cd.caption); shown.add(cd.title); n++;
            } catch (RateLimited e) {
                Log.e(TAG, "thumb rate-limited, stopping downloads: " + e.getMessage());
                f.delete(); break;
            } catch (Exception e) {
                Log.e(TAG, "thumb failed, skipping: " + cd.url + " " + e);
                f.delete();
            }
        }
        if (n < MIN_OK) { deleteTree(tmp); throw new IOException("only " + n + " thumbnails downloaded"); }
        writeAll(new File(tmp, "meta.json"), meta.toString());

        // 4. swap: wall -> wall_old, tmp -> wall, delete old
        File cur = cacheDir(c), old = new File(files, "wall_old");
        deleteTree(old);
        if (cur.exists() && !cur.renameTo(old)) throw new IOException("rename cur");
        if (!tmp.renameTo(cur)) { old.renameTo(cur); throw new IOException("rename tmp"); }
        deleteTree(old);
        Log.i(TAG, "swapped in " + n + " images -> " + cur);

        for (String t : shown) recent.add(0, t);
        recent.removeAll(Collections.singleton(""));
        while (recent.size() > RECENT_KEEP) recent.remove(recent.size() - 1);
        StringBuilder rb = new StringBuilder();
        for (String t : recent) { if (rb.length() > 0) rb.append('\n'); rb.append(t); }
        prefs.edit().putString("wallRecent", rb.toString()).apply();
    }

    static String meta(JSONObject m, String k) {
        if (m == null) return "";
        JSONObject o = m.optJSONObject(k);
        return o == null ? "" : o.optString("value", "");
    }

    static String clean(String s) { return s.replaceAll("<[^>]+>", " ").replace("&amp;", "&").replace("&quot;", "\"").replace("&#039;", "'").replaceAll("\\s+", " ").trim(); }
    static String cut(String s, int n) { return s.length() <= n ? s : s.substring(0, n - 1).trim() + "…"; }
    static String enc(String s) throws UnsupportedEncodingException { return URLEncoder.encode(s, "UTF-8"); }

    static void pace(long gap) throws IOException {
        long wait = lastRequestAt + gap - System.currentTimeMillis();
        if (wait > 0) sleep(wait);
    }

    static void sleep(long ms) throws IOException { try { Thread.sleep(ms); } catch (InterruptedException e) { throw new IOException(e); } }

    /** GET with pacing, manual redirects, Retry-After / 5s-15s-45s backoff on 429/5xx. */
    static HttpURLConnection open(String url, long gap) throws IOException {
        for (int attempt = 0, hops = 0; ; ) {
            pace(gap);
            lastRequestAt = System.currentTimeMillis();
            httpRequests++;
            HttpURLConnection h = (HttpURLConnection) new URL(url).openConnection();
            h.setRequestProperty("User-Agent", UA);
            h.setRequestProperty("Api-User-Agent", UA);
            h.setConnectTimeout(15000); h.setReadTimeout(30000);
            h.setInstanceFollowRedirects(false);
            int code = h.getResponseCode();
            String shortUrl = url.length() > 140 ? url.substring(0, 140) + "…" : url;
            Log.i(TAG, "HTTP " + code + " " + shortUrl);
            if (code == 200) return h;
            String loc = h.getHeaderField("Location");
            if (code >= 300 && code < 400 && loc != null && hops++ < 5) { h.disconnect(); url = new URL(new URL(url), loc).toString(); continue; }
            if (code == 429 || code == 503 || code >= 500) {
                long waitMs = attempt < BACKOFF_MS.length ? BACKOFF_MS[attempt] : -1;
                String ra = h.getHeaderField("Retry-After");
                if (ra != null) try { waitMs = Math.max(waitMs, Long.parseLong(ra.trim()) * 1000); } catch (NumberFormatException ignored) {}
                h.disconnect();
                if (attempt < BACKOFF_MS.length && waitMs <= 120_000) {
                    Log.i(TAG, "backing off " + waitMs / 1000 + "s (attempt " + (attempt + 1) + ", Retry-After=" + ra + ")");
                    attempt++;
                    sleep(waitMs);
                    continue;
                }
                if (code == 429) throw new RateLimited("HTTP 429 after " + attempt + " retries (Retry-After=" + ra + ") " + shortUrl);
                throw new IOException("HTTP " + code + " after retries " + shortUrl);
            }
            String body = "";
            try { InputStream es = h.getErrorStream(); if (es != null) body = readAll(es); } catch (Exception ignored) {}
            h.disconnect();
            throw new IOException("HTTP " + code + " for " + shortUrl + " " + cut(body.replaceAll("\\s+", " "), 200));
        }
    }

    static JSONObject apiCall(String url) throws Exception {
        apiCalls++;
        HttpURLConnection h = open(url, MIN_GAP_MS);
        try {
            JSONObject o = new JSONObject(readAll(h.getInputStream()));
            if (o.has("error")) {
                String code = o.getJSONObject("error").optString("code");
                if ("ratelimited".equals(code) || "maxlag".equals(code)) throw new RateLimited("API " + code);
                throw new IOException("API error: " + o.getJSONObject("error").optString("info"));
            }
            return o;
        } finally { h.disconnect(); }
    }

    static void download(String url, File f) throws IOException {
        HttpURLConnection h = open(url, THUMB_GAP_MS);
        try (InputStream in = h.getInputStream(); OutputStream out = new FileOutputStream(f)) {
            byte[] buf = new byte[16384]; int n; long total = 0;
            while ((n = in.read(buf)) > 0) { out.write(buf, 0, n); total += n; if (total > 8_000_000) throw new IOException("too big"); }
        } finally { h.disconnect(); }
    }

    static String readAll(InputStream in) throws IOException {
        try (InputStream i = in) {
            ByteArrayOutputStream b = new ByteArrayOutputStream(); byte[] buf = new byte[8192]; int n;
            while ((n = i.read(buf)) > 0) b.write(buf, 0, n);
            return b.toString("UTF-8");
        }
    }

    static void writeAll(File f, String s) throws IOException { try (OutputStream o = new FileOutputStream(f)) { o.write(s.getBytes("UTF-8")); } }

    static void deleteTree(File f) {
        File[] k = f.listFiles();
        if (k != null) for (File x : k) deleteTree(x);
        f.delete();
    }
}
