package com.naman.tvhome;

import android.app.Activity;
import android.content.*;
import android.content.pm.*;
import android.graphics.*;
import android.graphics.drawable.*;
import android.os.*;
import android.text.TextUtils;
import android.view.*;
import android.widget.*;
import java.util.*;

public class MainActivity extends Activity {
    static final String DEFAULT_DOCK = "com.google.android.youtube.tv,com.netflix.ninja,com.amazon.amazonvideo.livingroom,com.disney.disneyplus,com.hulu.livingroomplus,com.wbd.stream,com.spotify.tv.android";
    static final String SETTINGS_KEY = "__settings__";
    static final int[] WALLS = {R.drawable.wp_1, R.drawable.wp_2, R.drawable.wp_3, R.drawable.wp_4, R.drawable.wp_5, R.drawable.wp_6, R.drawable.wp_7, R.drawable.wp_8};
    static final long WALL_INTERVAL = 60_000, FADE_MS = 1500;

    static class App { String pkg, label; Intent launch; }

    SharedPreferences prefs;
    PackageManager pm;
    float dp;
    ImageView wallFront, wallBack;
    Bitmap bmpFront;
    int wallIndex;
    List<java.io.File> wallFiles = new ArrayList<>();
    Map<String, String> wallCaps = new HashMap<>();
    TextView caption;
    boolean forceWall;
    LinearLayout dockRow;
    GridLayout grid;
    ScrollView scroller;
    int scrW, scrH, safeX, safeY, gridGap, gridTileW, gridTileH;
    static final int GRID_COLS = 6;
    final Handler h = new Handler(Looper.getMainLooper());
    final Map<String, App> apps = new LinkedHashMap<>();
    boolean receiverOn;

    final BroadcastReceiver pkgReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context c, Intent i) { rebuild(); }
    };
    final Runnable wallTick = new Runnable() { @Override public void run() { nextWallpaper(); } };

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = getSharedPreferences("home", MODE_PRIVATE);
        pm = getPackageManager();
        dp = getResources().getDisplayMetrics().density;
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        buildUi();
        handleIntent(getIntent());
        loadWallList();
        wallIndex = prefs.getInt("wall", 0) % wallCount();
        bmpFront = decodeWall(wallIndex);
        wallFront.setImageBitmap(bmpFront);
        showCaption(wallIndex);
        rebuild();
    }

    void triggerWallRefresh(String why) {
        boolean f = forceWall;
        forceWall = false;
        android.util.Log.i("TVHomeWall", "check (" + why + ") force=" + f + " cached=" + WallpaperFetcher.cached(this).size());
        WallpaperFetcher.maybeRefresh(this, f, () -> h.post(() -> {
            loadWallList(); wallIndex = -1;
            android.util.Log.i("TVHomeWall", "new set ready: " + wallFiles.size() + " files, switching now");
            if (!isFinishing()) nextWallpaper();
        }));
    }

    @Override protected void onNewIntent(Intent i) {
        super.onNewIntent(i);
        setIntent(i);
        // Android 10+ delivers onNewIntent to an already-resumed singleTask activity WITHOUT
        // onPause/onResume, so a force flag only read in onResume was never acted on.
        if (i != null && i.getBooleanExtra("refreshWallpapers", false)) { forceWall = true; i.removeExtra("refreshWallpapers"); triggerWallRefresh("onNewIntent"); }
        if (handleIntent(i)) rebuild();
        else if (scroller != null) { scroller.smoothScrollTo(0, 0); focusDock(); }
    }

    boolean handleIntent(Intent i) {
        if (i == null) return false;
        if (i.getBooleanExtra("refreshWallpapers", false)) { forceWall = true; i.removeExtra("refreshWallpapers"); }
        String d = i.getStringExtra("dock");
        if (d == null) return false;
        prefs.edit().putString("dock", d.replace(" ", "")).apply();
        return true;
    }

    @Override protected void onResume() {
        super.onResume();
        IntentFilter f = new IntentFilter();
        f.addAction(Intent.ACTION_PACKAGE_ADDED); f.addAction(Intent.ACTION_PACKAGE_REMOVED);
        f.addAction(Intent.ACTION_PACKAGE_CHANGED); f.addAction(Intent.ACTION_PACKAGE_REPLACED);
        f.addDataScheme("package");
        registerReceiver(pkgReceiver, f); receiverOn = true;
        rebuild();
        triggerWallRefresh("onResume");
        h.removeCallbacks(wallTick); h.postDelayed(wallTick, WALL_INTERVAL);
        android.util.Log.i("TVHomeRotate", "timer armed, next crossfade in " + WALL_INTERVAL / 1000 + "s");
    }

    @Override protected void onPause() {
        super.onPause();
        if (receiverOn) { unregisterReceiver(pkgReceiver); receiverOn = false; }
        h.removeCallbacks(wallTick);
    }

    @Override public void onBackPressed() { /* home: do nothing */ }

    // ---------- UI ----------
    int px(float v) { return Math.round(v * dp); }

    void buildUi() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        wallBack = wallView(); wallFront = wallView();
        root.addView(wallBack); root.addView(wallFront);

        View grad = new View(this);
        grad.setBackground(new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{0x00000000, 0x66000000, 0xE6000000}));
        FrameLayout.LayoutParams glp = new FrameLayout.LayoutParams(-1, px(330), Gravity.BOTTOM);
        root.addView(grad, glp);

        LinearLayout clock = new LinearLayout(this);
        clock.setOrientation(LinearLayout.VERTICAL); clock.setGravity(Gravity.END);
        TextClock time = new TextClock(this);
        time.setFormat12Hour("h:mm"); time.setFormat24Hour("HH:mm");
        style(time, 44, true);
        TextClock date = new TextClock(this);
        date.setFormat12Hour("EEEE, MMMM d"); date.setFormat24Hour("EEEE, MMMM d");
        style(date, 18, false);
        clock.addView(time); clock.addView(date);
        FrameLayout.LayoutParams clp = new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.END);
        clp.setMargins(0, px(28), px(48), 0);
        root.addView(clock, clp);

        android.util.DisplayMetrics dm = new android.util.DisplayMetrics();
        getWindowManager().getDefaultDisplay().getRealMetrics(dm);
        scrW = Math.max(dm.widthPixels, dm.heightPixels); scrH = Math.min(dm.widthPixels, dm.heightPixels);
        safeX = Math.round(scrW * 0.05f); safeY = Math.round(scrH * 0.05f);
        gridGap = px(20);
        gridTileW = (scrW - 2 * safeX - GRID_COLS * gridGap) / GRID_COLS;
        gridTileH = gridTileW * 9 / 16;
        scroller = new ScrollView(this) {
            // we do our own row-aware scrolling on focus
            @Override protected int computeScrollDeltaToGetChildRectOnScreen(Rect r) { return 0; }
        };
        scroller.setVerticalScrollBarEnabled(false);
        scroller.setFillViewport(true);
        scroller.setClipChildren(false);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setClipChildren(false); col.setClipToPadding(false);
        int screenH = scrH;
        View spacer = new View(this);
        col.addView(spacer, new LinearLayout.LayoutParams(-1, screenH - px(200)));

        HorizontalScrollView hs = new HorizontalScrollView(this);
        hs.setHorizontalScrollBarEnabled(false); hs.setClipChildren(false); hs.setClipToPadding(false);
        hs.setFillViewport(true);
        dockRow = new LinearLayout(this);
        dockRow.setGravity(Gravity.CENTER_HORIZONTAL);
        dockRow.setClipChildren(false); dockRow.setClipToPadding(false);
        dockRow.setPadding(safeX, px(14), safeX, 0);
        hs.addView(dockRow, new FrameLayout.LayoutParams(-1, -2));
        col.addView(hs, new LinearLayout.LayoutParams(-1, px(170)));

        TextView allTitle = new TextView(this);
        allTitle.setText("All apps"); style(allTitle, 20, true);
        allTitle.setPadding(safeX, px(24), 0, px(8));
        col.addView(allTitle);

        grid = new GridLayout(this);
        grid.setColumnCount(GRID_COLS);
        grid.setClipChildren(false); grid.setClipToPadding(false);
        grid.setPadding(safeX - gridGap / 2, px(8), safeX - gridGap / 2, safeY);
        LinearLayout.LayoutParams gp = new LinearLayout.LayoutParams(-1, -2);
        col.addView(grid, gp);
        // keep the grid backed by a dim layer for legibility
        grid.setBackground(new ColorDrawable(0x00000000));

        scroller.addView(col);
        caption = new TextView(this);
        caption.setTextColor(0x99FFFFFF);
        caption.setTextSize(11);
        caption.setSingleLine(true); caption.setEllipsize(TextUtils.TruncateAt.END);
        caption.setShadowLayer(4, 0, 1, 0xAA000000);
        caption.setMaxWidth(scrW / 2);
        FrameLayout.LayoutParams cap = new FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM | Gravity.START);
        cap.setMargins(safeX, 0, 0, safeY);
        root.addView(caption, cap);
        root.addView(scroller, new FrameLayout.LayoutParams(-1, -1));
        // fade attribution out while browsing the grid so it never sits on top of tiles
        scroller.setOnScrollChangeListener((v, x, y, ox, oy) -> caption.setAlpha(y > px(8) ? 0f : 1f));
        setContentView(root);
    }

    ImageView wallView() {
        ImageView v = new ImageView(this);
        v.setScaleType(ImageView.ScaleType.CENTER_CROP);
        v.setLayoutParams(new FrameLayout.LayoutParams(-1, -1));
        return v;
    }

    void style(TextView t, int sp, boolean bold) {
        t.setTextColor(Color.WHITE);
        t.setTextSize(sp);
        t.setTypeface(Typeface.create("sans-serif", bold ? Typeface.BOLD : Typeface.NORMAL));
        t.setShadowLayer(8, 0, 2, 0x99000000);
    }

    // ---------- Apps ----------
    void loadApps() {
        apps.clear();
        String self = getPackageName();
        for (String cat : new String[]{Intent.CATEGORY_LEANBACK_LAUNCHER, Intent.CATEGORY_LAUNCHER}) {
            Intent q = new Intent(Intent.ACTION_MAIN).addCategory(cat);
            for (ResolveInfo ri : pm.queryIntentActivities(q, 0)) {
                String p = ri.activityInfo.packageName;
                if (p.equals(self) || apps.containsKey(p)) continue;
                App a = new App();
                a.pkg = p;
                a.label = String.valueOf(ri.loadLabel(pm));
                a.launch = new Intent(Intent.ACTION_MAIN).addCategory(cat)
                        .setClassName(p, ri.activityInfo.name)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
                apps.put(p, a);
            }
        }
    }

    List<String> dockList() {
        List<String> l = new ArrayList<>();
        for (String s : prefs.getString("dock", DEFAULT_DOCK).split(",")) { s = s.trim(); if (!s.isEmpty() && !l.contains(s)) l.add(s); }
        return l;
    }

    void saveDock(List<String> l) { prefs.edit().putString("dock", TextUtils.join(",", l)).apply(); }

    void rebuild() {
        View f = getCurrentFocus();
        String focusTag = f != null && f.getTag() instanceof String ? (String) f.getTag() : null;
        loadApps();
        dockRow.removeAllViews();
        for (String p : dockList()) {
            App a = apps.get(p);
            if (a != null) dockRow.addView(tile(a, true));
        }
        dockRow.addView(settingsTile());

        grid.removeAllViews();
        List<App> sorted = new ArrayList<>(apps.values());
        Collections.sort(sorted, (x, y) -> x.label.compareToIgnoreCase(y.label));
        for (App a : sorted) grid.addView(tile(a, false));

        View target = focusTag != null ? findTagged(focusTag) : null;
        if (target == null) target = dockRow.getChildAt(0).findViewWithTag(tagOf(dockRow.getChildAt(0)));
        final View t = target;
        if (t != null) t.post(t::requestFocus);
    }

    String tagOf(View container) { View c = ((ViewGroup) container).getChildAt(0); return (String) c.getTag(); }

    View findTagged(String tag) { return getWindow().getDecorView().findViewWithTag(tag); }

    void focusDock() { if (dockRow.getChildCount() > 0) ((ViewGroup) dockRow.getChildAt(0)).getChildAt(0).requestFocus(); }

    View settingsTile() {
        App s = new App();
        s.pkg = SETTINGS_KEY; s.label = "Settings";
        s.launch = new Intent(android.provider.Settings.ACTION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return tile(s, true);
    }

    Drawable gearIcon() {
        try { return pm.getActivityIcon(new Intent(android.provider.Settings.ACTION_SETTINGS)); }
        catch (Exception e) { return getDrawable(android.R.drawable.ic_menu_preferences); }
    }

    View tile(final App a, final boolean inDock) {
        final boolean isSettings = SETTINGS_KEY.equals(a.pkg);
        int wPx = inDock ? px(isSettings ? 90 : 160) : gridTileW, hPx = inDock ? px(90) : gridTileH;
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER_HORIZONTAL);
        box.setClipChildren(false); box.setClipToPadding(false);

        final FrameLayout card = new FrameLayout(this);
        card.setTag((inDock ? "d:" : "g:") + a.pkg);
        card.setFocusable(true); card.setFocusableInTouchMode(false); card.setClickable(true);
        final float radius = px(14);
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(radius);
        bg.setColor(0xCC2A2D33);
        card.setBackground(bg);
        card.setOutlineProvider(ViewOutlineProvider.BACKGROUND);
        card.setClipToOutline(true);
        card.setElevation(px(2));

        ImageView iv = new ImageView(this);
        Drawable banner = null;
        if (!isSettings) {
            try { banner = pm.getApplicationBanner(a.pkg); } catch (Exception ignored) {}
            if (banner == null) { try { banner = pm.getActivityBanner(a.launch); } catch (Exception ignored) {} }
        }
        if (banner != null) {
            iv.setScaleType(ImageView.ScaleType.CENTER_CROP);
            iv.setImageDrawable(banner);
            card.addView(iv, new FrameLayout.LayoutParams(-1, -1));
        } else {
            Drawable icon;
            if (isSettings) icon = gearIcon();
            else { try { icon = pm.getApplicationIcon(a.pkg); } catch (Exception e) { icon = getDrawable(android.R.drawable.sym_def_app_icon); } }
            iv.setScaleType(ImageView.ScaleType.FIT_CENTER);
            iv.setImageDrawable(icon);
            int s = Math.min(hPx - px(30), px(72));
            card.addView(iv, new FrameLayout.LayoutParams(s, s, Gravity.CENTER));
            if (!isSettings) {
                // derive a pleasant background tint from the icon
                bg.setColor(0xE6000000 | (tint(icon) & 0x00FFFFFF));
            }
        }

        final TextView label = new TextView(this);
        label.setText(a.label);
        style(label, 15, false);
        label.setSingleLine(true); label.setEllipsize(TextUtils.TruncateAt.END);
        label.setGravity(Gravity.CENTER);
        label.setMaxWidth(wPx);
        label.setVisibility(View.INVISIBLE);

        LinearLayout.LayoutParams cp = new LinearLayout.LayoutParams(wPx, hPx);
        box.addView(card, cp);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-2, -2);
        lp.topMargin = px(14);
        box.addView(label, lp);

        if (inDock) {
            LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(-2, -2);
            bp.setMargins(px(12), 0, px(12), 0);
            box.setLayoutParams(bp);
        } else {
            GridLayout.LayoutParams gp = new GridLayout.LayoutParams();
            gp.setMargins(gridGap / 2, px(14), gridGap / 2, px(4));
            gp.width = gridTileW;
            box.setLayoutParams(gp);
        }

        card.setOnFocusChangeListener((v, has) -> {
            v.animate().scaleX(has ? 1.1f : 1f).scaleY(has ? 1.1f : 1f).translationZ(has ? px(16) : 0).setDuration(150).start();
            label.setVisibility(has ? View.VISIBLE : View.INVISIBLE);
            ((View) v.getParent()).setZ(has ? 1 : 0);
            if (has) {
                if (inDock) scroller.smoothScrollTo(0, 0);
                else scrollIntoView((View) v.getParent());
            }
        });
        card.setOnClickListener(v -> launch(a));
        card.setOnLongClickListener(v -> { toggleDock(a, inDock); return true; });
        card.setOnKeyListener((v, code, ev) -> {
            if (code == KeyEvent.KEYCODE_MENU && ev.getAction() == KeyEvent.ACTION_UP) { toggleDock(a, inDock); return true; }
            return code == KeyEvent.KEYCODE_MENU;
        });
        return box;
    }

    void scrollIntoView(View box) {
        int extra = Math.round(box.getHeight() * 0.06f) + px(8); // room for 1.1x scale + shadow
        int top = grid.getTop() + box.getTop() - extra;
        int bottom = grid.getTop() + box.getBottom() + extra;
        int y = scroller.getScrollY(), vh = scroller.getHeight();
        int topSafe = px(120); // stay below the clock
        int target = y;
        if (bottom > y + vh - safeY) target = bottom - (vh - safeY);
        if (top < target + topSafe) target = top - topSafe;
        target = Math.max(0, target);
        if (target != y) scroller.smoothScrollTo(0, target);
    }

    int tint(Drawable d) {
        try {
            Bitmap b = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888);
            Canvas c = new Canvas(b);
            d.setBounds(0, 0, 8, 8); d.draw(c);
            long r = 0, g = 0, bl = 0, n = 0;
            for (int x = 0; x < 8; x++) for (int y = 0; y < 8; y++) {
                int p = b.getPixel(x, y);
                if (Color.alpha(p) < 128) continue;
                r += Color.red(p); g += Color.green(p); bl += Color.blue(p); n++;
            }
            b.recycle();
            if (n == 0) return 0x2A2D33;
            return Color.rgb((int) (r / n * 0.55), (int) (g / n * 0.55), (int) (bl / n * 0.55));
        } catch (Throwable t) { return 0x2A2D33; }
    }

    void launch(App a) {
        try { startActivity(a.launch); }
        catch (Exception e) { Toast.makeText(this, "Can't open " + a.label, Toast.LENGTH_SHORT).show(); }
    }

    void toggleDock(App a, boolean inDock) {
        if (SETTINGS_KEY.equals(a.pkg)) return;
        List<String> l = dockList();
        if (inDock) { l.remove(a.pkg); Toast.makeText(this, "Removed " + a.label + " from dock", Toast.LENGTH_SHORT).show(); }
        else if (!l.contains(a.pkg)) { l.add(a.pkg); Toast.makeText(this, "Added " + a.label + " to dock", Toast.LENGTH_SHORT).show(); }
        else { Toast.makeText(this, a.label + " is already in the dock", Toast.LENGTH_SHORT).show(); return; }
        saveDock(l);
        rebuild();
    }

    // ---------- Wallpaper ----------
    void loadWallList() {
        wallFiles = WallpaperFetcher.cached(this);
        wallCaps = WallpaperFetcher.captions(this);
    }

    int wallCount() { return wallFiles.isEmpty() ? WALLS.length : wallFiles.size(); }

    void showCaption(int idx) {
        String c = wallFiles.isEmpty() || idx >= wallFiles.size() ? null : wallCaps.get(wallFiles.get(idx).getName());
        caption.setText(c == null ? "" : c);
    }

    /** Decode wallpaper idx downsampled to screen size, RGB_565. Falls back to bundled set. */
    Bitmap decodeWall(int idx) {
        BitmapFactory.Options o = new BitmapFactory.Options();
        o.inPreferredConfig = Bitmap.Config.RGB_565;
        o.inScaled = false;
        try {
            if (!wallFiles.isEmpty() && idx < wallFiles.size()) {
                String path = wallFiles.get(idx).getPath();
                o.inJustDecodeBounds = true;
                BitmapFactory.decodeFile(path, o);
                o.inJustDecodeBounds = false;
                int ss = 1;
                while (o.outWidth / (ss * 2) >= scrW && o.outHeight / (ss * 2) >= scrH) ss *= 2;
                o.inSampleSize = ss;
                Bitmap b = BitmapFactory.decodeFile(path, o);
                if (b != null) return b;
            }
        } catch (OutOfMemoryError ignored) {}
        return decode(WALLS[idx % WALLS.length]);
    }

    Bitmap decode(int res) {
        BitmapFactory.Options o = new BitmapFactory.Options();
        o.inPreferredConfig = Bitmap.Config.RGB_565;
        o.inScaled = false;
        int sw = getResources().getDisplayMetrics().widthPixels;
        if (sw > 0 && sw <= 1280) o.inSampleSize = 2;
        try { return BitmapFactory.decodeResource(getResources(), res, o); } catch (OutOfMemoryError e) { return null; }
    }

    void nextWallpaper() {
        if (wallCount() == 0) return;
        if (wallIndex >= wallCount()) wallIndex = -1;
        final int next = (wallIndex + 1) % wallCount();
        new Thread(() -> {
            final Bitmap nb = decodeWall(next);
            h.post(() -> {
                if (nb == null || isFinishing()) {
                    android.util.Log.e("TVHomeRotate", "decode failed for #" + next + (isFinishing() ? " (finishing)" : ""));
                    if (nb != null) nb.recycle();
                    if (!isFinishing()) { h.removeCallbacks(wallTick); h.postDelayed(wallTick, WALL_INTERVAL); }
                    return;
                }
                android.util.Log.i("TVHomeRotate", "crossfade to #" + next + "/" + wallCount() + (wallFiles.isEmpty() ? " (bundled)" : " (cached " + wallFiles.get(next).getName() + ")"));
                wallIndex = next;
                showCaption(next);
                prefs.edit().putInt("wall", next).apply();
                // back view shows the new image, front fades out, then swap
                wallBack.setImageBitmap(nb);
                wallBack.setAlpha(1f);
                wallFront.animate().alpha(0f).setDuration(FADE_MS).withEndAction(() -> {
                    Bitmap old = bmpFront;
                    wallFront.setImageBitmap(nb);
                    wallFront.setAlpha(1f);
                    wallBack.setImageDrawable(null);
                    bmpFront = nb;
                    if (old != null && old != nb) old.recycle();
                }).start();
                h.removeCallbacks(wallTick);
                h.postDelayed(wallTick, WALL_INTERVAL);
            });
        }, "wall").start();
    }

    @Override protected void onDestroy() {
        super.onDestroy();
        h.removeCallbacksAndMessages(null);
    }

    @Override public void onTrimMemory(int level) {
        super.onTrimMemory(level);
    }
}
