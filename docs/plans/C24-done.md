# C24 done — the ground you can walk

**Date:** 2026-09-23  
**Branch:** `eco/c24`  
**Generators:** `scripts/walkable.py`  
**Checks:** `check-walkable` (+ pack-layers coverage, licences after add)

---

## Walkable ground

`walkable.geojson` — connected polygons with holes:

| rule | |
|---|---|
| slope threshold | **30°** — usual limit before walking becomes scrambling on unimproved ground (not an accessibility standard) |
| excluded | building footprints, trunk radius 0.45 m, creek channel, slope > 30° |
| **not** excluded | tree canopy (same correction as C20 gathering) |

Each feature carries `area_m2`, `mean_slope_deg`, `component_id`.

| quantity | value |
|---|---:|
| walkable cells (1 m) | 27,941 |
| polygons published | 14 |
| total area | **28,374 m²** |

Proof points in `check-walkable`: under oak crowns at EN (260.8, 267.8) is walkable; a footprint cell is not; a 35° cell is not; component areas sum to the graph total; union matches the sum within 5%.

---

## Walk graph

`walk-graph.json` lists which components touch and the narrowest gap between those that do not (top 50 gaps) — where a path would join two pieces of the property.

---

## Collision mesh

`models/collision.glb` + `collision.json`:

| | |
|---|---|
| triangles | **8,404** (< 50k) |
| DEM step | 3 m |
| max deviation vs 1 m DEM (200 samples) | **0.75 m** (bound 2.5 m) |
| frame | pack spawn origin; x east, y up, z south |
| contents | downsampled ground + 2.5 m building shells |

---

## Pack registry

`walkable`, `walk_graph`, `collision` registered in `pack.json`. Atlas `not_drawable` notes them until a later drawable pass (walkable is the contract file; collision is physics).
