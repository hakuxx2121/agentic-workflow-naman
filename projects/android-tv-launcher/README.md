# Android TV home launcher

A leanback-friendly Android TV **home screen**: a full-bleed rotating landscape wallpaper, a dock of streaming apps, and a six-column all-apps grid. It registers as a HOME / LEANBACK_LAUNCHER activity (`com.naman.tvhome`, version 1.2).

Built with the **TV Bot** Grok Bot agent under Naman's direction.

A preview of the dock on a Wikimedia landscape is in `preview.png`. Wallpaper files under `app/src/main/res/drawable-nodpi/` are public-domain or CC0 images from Wikimedia Commons; credits are in `WALLPAPER_CREDITS.txt`.

## What it does

The behavior below is what `MainActivity.java` and `WallpaperFetcher.java` implement:

- Immersive landscape home. A dock of common TV apps (YouTube, Netflix, Prime Video, Disney+, Hulu, and others in a default package list) sits over the wallpaper; an "All apps" grid lists everything the system reports as a launcher or leanback activity.
- Wallpapers rotate on a timer (60 seconds, 1.5-second fade) through eight bundled stills. You can also load extra images from storage; `WallpaperFetcher` is a helper for that path.
- Settings and dock membership are stored in app preferences (`home`). The activity is `singleTask`, hidden from recents, and handles package-install broadcasts by rebuilding the app list.
- `minSdk 26`, `targetSdk 30`, `compileSdk 34`. Internet permission is declared for wallpaper fetch. Backup is disabled.

This is a launcher only. It does not include any account credentials for the streaming apps.

## Tech stack

- Java (Android API, no extra libraries in `build.gradle`)
- Android Gradle Plugin 8.5.2, Gradle wrapper
- Leanback / HOME intent filters in `AndroidManifest.xml`

## How to build

```bash
# Android SDK 34 and a JDK 17+ (AGP 8.5) on your PATH
./gradlew assembleDebug
```

The debug and release build types in this copy are signed with the **local Android debug keystore** (`signingConfigs.debug`), which the Android toolchain creates under `~/.android/debug.keystore` if it is missing. Install the debug APK on a TV or emulator and, if you want it as the home app, choose it when Android asks for a default launcher.

## What was removed and how to run it yourself

**Removed (security — do not commit these):**
- `debug.keystore` and any other `*.keystore` / `*.jks` signing keys.
- The built `tvhome.apk`.
- `local.properties` (a machine-specific Android SDK path).
- `build/` and `.gradle/` outputs.

The Gradle file no longer points at a keystore in the project tree. You do not have to invent a password: the standard debug signing config is enough to install a debug build.

If you prefer a keystore next to the project (still gitignored), create one and point a local signing config at it. Example with `keytool` (this creates a **new** empty keystore; it is not the file that was removed):

```bash
keytool -genkeypair -v -keystore debug.keystore -alias androiddebugkey   -keyalg RSA -keysize 2048 -validity 10000   -storepass android -keypass android   -dname "CN=Android Debug,O=Android,C=US"
```

Do not commit `debug.keystore`, `local.properties`, or APKs. The root `.gitignore` already lists them.

Create `local.properties` on your machine only, for example:

```
sdk.dir=/path/to/Android/sdk
```
