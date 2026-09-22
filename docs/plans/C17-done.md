# C17 done — every position proven twice

**Date:** 2026-09-22  
**UTM:** EPSG:**32611** (WGS84 UTM zone 11N)

---

## C17.1 — position table

| | |
|---|---|
| rows | **37** (`positions.csv` + `positions.geojson`) |
| kinds | models, survey corners, named sites (ford, well, …) |
| frame | pack x/y via C15.3 WGS84 metres |
| elev | pack 1 m terrain |
| POB | survey point of beginning — tape/compass columns `from_POB_m`, `bearing_from_POB_deg` |

Generator: `scripts/build-positions.py`.

---

## C17.2 — second proof (`check-positions.py`)

| check | limit | result |
|---|---|---|
| model origin vs table | ≤ 0.10 m horiz | OK (17 models) |
| base elev vs table | ≤ 0.15 m vert | OK |
| footprint area vs GLB plan | ≤ 3% | OK (oak-leaf via solids hull; site-grounds envelope) |
| footprint centroid | ≤ 0.25 m | OK |
| survey calls (C15.3) | ≤ 0.1 ft | OK |
| trees lng/lat | ≤ 1 cm | OK (worst 0.08 mm) |

Counter-proof sheet: `analysis/positions-proof.png` (boundary, easements, footprints, POB, N, scale).

---

## C17.3 — Oak Leaf (not moved)

| | |
|---|---|
| origin | **−119.155333, 34.433118** |
| pack EN | **381.222, 297.371** |
| elev | **425.625 m** |
| footprint | **1136.95 m²** |
| from POB | **66.16 m** at bearing **223.3°** |
| min boundary | **24.21 m** inside |
| creek footprint | **68.25 m** |
| trees inside footprint | **6** |
| nearest trunk | **0.08 m** |

---

**check-positions.py:** OK.
