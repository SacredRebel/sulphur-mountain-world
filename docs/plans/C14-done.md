# C14 done — phone-scan capture plan + placement tooling

**Date:** 2026-09-22  
**Branch:** `eco/c14`  
**Generators:** `scripts/capture-plan.py`, `scripts/scan.py`  
**Check:** `scripts/check-scans.py`

Privacy: `scans/` is git-ignored. No scan binaries or site photographs are committed.
`scans.json` holds placement rows only (`url: null` until private storage is filled in).

---

## C14.1 — capture plan

- `capture-plan.geojson` — **160** zones of **20 m** with **3 m** overlap over the survey
  parcel, each with `id`, `walk_order`, and a one-line tip.
- `analysis/capture-plan.png` — zones numbered over the hillshade and boundary.

Walk order is serpentine (west→east on even rows, east→west on odd).

---

## C14.2 — `scripts/scan.py`

Accepts PLY (or SPZ via `npx @playcanvas/splat-transform`), a zone id, and ≥3 ground-control
pairs (`sx,sy,sz,east,north`). Steps:

1. Stand upright (capture y-down → y-up).
2. Umeyama similarity to the control points (height from the 1 m DEM).
3. Light ICP vertical refine against the DEM.
4. Crop to the zone + 2 m; drop floaters (>25 m above DEM or >3 m below) and near-zero opacity.
5. Write `scans/<zone>.ply` (git-ignored) and a placement row in `scans.json`.

**Placement convention** (also in `scans.json`):

centre on mid of 2nd–98th percentile (x, z); rest base (2nd percentile of y) on the DEM;
turn clockwise by `turn_deg`; scale; add `lift_m`.

`pack.json` gains `layers.capture_plan` and `layers.scans`.

---

## C14.3 — synthetic proof

A DEM-sampled patch near EN (300, 250) was transformed with scale **1.05**, yaw **15°**, and a
known shift, written as a y-down PLY, then recovered:

| check | result |
|---|---|
| RMS | **0.0000 m** (limit 0.1 m) |
| centre offset | **0.0052 m** (limit 0.2 m) |
| recovered scale | **1.0500** |

Numbers in `analysis/scans-proof.json`.

---

## What still waits on Sacred Rebel

1. Yes/no to private scan storage (so `url` can be filled).
2. One real Scaniverse capture of zone `z001` (or any zone) with three ground-control points.

Until then the tooling and walk plan are ready; no property photographs enter the public repo.
