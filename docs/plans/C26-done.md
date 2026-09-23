# C26 done — sky against the real horizon

**Date:** 2026-09-23  
**Branch:** `eco/c26`  
**Generators:** `scripts/sky_events.py`  
**Checks:** `check-sky` (+ `--self-test`)

---

## What published

| | |
|---|---|
| `sky-events.json` | **17** observers × **8** events (4 seasons + 4 cross-quarters) × rise/set |
| observers | gathering `best`/`good` centroids + 15 structures (not site-grounds/creek) |
| horizon | nearest C16 viewpoint profile in `horizon.json` |
| `alignments.geojson` | **272** sight-lines to 8 km (same radius as `horizon.geojson`) |
| ephemeris | astronomy-engine (MIT) + mourner/suncalc (BSD) cross-check |
| timezone | `America/Los_Angeles` (DST flagged on every time) |
| authority / evidence | `derived` / `modelled` |

SunCalc worst deviation: **2.40 min** time, **0.42°** azimuth (tol 2.5 min / 0.5°) — AE `SearchRiseSet` and SunCalc civil sunrise (−0.833°) differ systematically by about one to two minutes; azimuths still agree.

June sunrise ridge delay **29.2–30.2 min**; December **35.6–74.6 min** — inside the C16/C17 range.

---

## What the ridge does to the light

On this property the mountains to the east keep morning light back: about half an hour after a flat-horizon sunrise in June, and from a little over half an hour to an hour and a quarter in December depending where you stand. Evening light is cut short the same way as the sun drops behind the western skyline. The alignments show which way that first and last light actually come from at each gathering band and structure — not the textbook flat compass bearing, but the bearing where the real ridge finally lets the sun through.
