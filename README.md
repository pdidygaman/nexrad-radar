# NEXRAD Radar — Desktop App

A live NEXRAD weather-radar viewer for every WSR-88D site in the U.S. — Level II & Level III
data, every product, RadarScope-style UI. Runs as a **native Windows desktop app**.

## Install (Windows 10 & 11)

Run **`installer\NEXRAD-Radar-Setup.exe`**. It installs per-user (no admin prompt) and adds a
**Desktop icon** and a **Start-menu** entry, plus an uninstaller.

Then just **double-click the NEXRAD Radar icon** — it opens like any normal app. There is no
server to start and nothing to run in a terminal: the app starts everything it needs inside
itself (on its own private port) and shows a loading splash while it gets ready. Python and all
libraries are bundled in, so it works on a machine with no Python installed.

You can **right-click the icon → Pin to taskbar / Pin to Start** to keep it handy.

> Needs the Microsoft **WebView2** runtime, which ships with Windows 11 and with Edge on
> Windows 10 (already present on virtually all machines). If the window is blank, install it
> from https://developer.microsoft.com/microsoft-edge/webview2/ (Evergreen Runtime).

### Won't conflict with your other apps
- The installed app bundles its **own private Python + libraries** — it cannot clash with
  packages used by any other Python project on your machine.
- It **auto-picks a free network port** at startup (tries 8753, 8761, … then any free port),
  so it never collides with something already using port 8000.

## Run from source (for development)

```
pip install -r requirements.txt      # first time only
python main.py                        # opens the desktop window
```

`python app.py` runs the server only (browser at http://localhost:8000).

## Rebuild the installer

```
build_all.bat        # icon → PyInstaller exe → Inno Setup installer
```

Outputs `dist\NEXRAD Radar\` (standalone app) and `installer\NEXRAD-Radar-Setup.exe`.
Requires `pyinstaller` (pip) and Inno Setup 6 (https://jrsoftware.org/isdl.php).

## Top bar
- **☰ Menu** — base map, radar opacity, and all data overlays
- **🔍 Search** — jump to a site by ICAO or city
- **📡 Radar sites** — pop-up of every U.S. radar, grouped by state; click to switch
- **Center** — current VCP mode (Clear-Air / Precip) and selected site
- **NN ALERTS** — active NWS alert count; click to toggle the warnings layer

## Bottom dock (left → right)
| Tool | What it does |
|---|---|
| ▶ Play | Animate the last *N* frames |
| 📍 GPS | Jump to your location (GPS, or IP fallback) |
| ◎ Probe | Toggle the center crosshair that reads the pixel value under it |
| ▭ / ▭▭ / ⊞ | Single / Dual / Quad screen — all panels stay synced |
| ⏱ Estimator | Click storm → target, set speed (mph), get ETA |
| 📏 Measure | Click points; distance in yards until 1 mile, then miles |
| ✏ Draw | Freezes the map and lets you draw freehand |
| 🔊 Sound | Toggle the "new data" ping |

**Bottom-left** = frame count (7–50) + current frame time.
**Bottom-right** (single screen) = product → click for **Level II / Level III** picker.
In **dual/quad**, each panel has its own product button in its header.

## Controls
- **Scroll wheel** = zoom · **left-click drag** = pan · **Space** = play/pause · **← →** = step frames

## Data
- **Level III** (live, ~2–4 min): reflectivity, velocity, spectrum width, dual-pol (ZDR/CC/KDP/HC),
  precipitation, VIL, echo tops — all tilts.
- **Level II**: raw Archive-II moments (REF/VEL/SW/ZDR/PHI/RHO) with download links.
- **Overlays**: NWS warnings (by category — severe, winter, fire, marine, tropical, hydro),
  SPC Day-1 outlooks (categorical/tornado/hail/wind), Local Storm Reports, METARs,
  Blitzortung lightning, Spotter Network, special statements, range rings, county lines,
  and NEXRAD history (date-based replay).

## Sources
- `unidata-nexrad-level3` (AWS Open Data) — live Level III
- `noaa-nexrad-level2` — Level II archive (listing needs an AWS account)
- weather.gov, SPC, Iowa Environmental Mesonet, Aviation Weather Center, Blitzortung
