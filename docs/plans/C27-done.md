# C27 done — snap guides, grid, symbolic construction

**Date:** 2026-09-23  
**Branch:** `eco/c27`  
**Generators:** `scripts/build-guides.py`  
**Checks:** `check-guides` (+ `--self-test`)

---

## Published

| file | what |
|---|---|
| `guides.geojson` | **368** snap features — survey calls/monuments (pri 100), easement edges (90), building edges +5 m (70), keylines (60), true-north + solar 10 m grids (50/45), 2 m contours on buildable (40) |
| `grid.json` | pack-frame grid: origin at parcel centroid, 10 m spacing, rotation 0 (true north) + solar rotation note; worked example index `(3,-2)` ↔ lng/lat |
| `construction-grid.geojson` | **50** lines — 30 ft module, solar-aligned to June flat sunrise az; **`authority: symbolic`**, `evidence: design-intent` |

Survey guides lie within **0.1 ft** of source. Contours follow DEM within **1.5 m** (worst 0.19 m). Grid round-trip exact. No guide outside pack AOI. Surfaces / water / defensible scripts do not reference the construction grid.
