# C16 done — read the land

**Date:** 2026-09-22  
**Evidence labels:** each layer carries `authority: derived` and `evidence: measured | modelled | traditional` in pack.json / file properties.

Shared grid: pack-frame 1 m (`analysis/grids/`), same origin/cell as terrain. NOTICE lists MIT sources; GRASS not installed here (GPL run-only — check noted as unavailable).

---

## C16.1 — horizon and sky events

| | |
|---|---|
| viewpoints | parcel centroid, Oak Leaf origin, ceremonial |
| eye | **1.6 m** |
| near | pack 1 m DEM to **1.5 km** |
| far | USGS NED 10 m (OpenTopoData) on **1 km** grid to **30 km** |
| az step | **0.5°** |
| refraction | standard, R_eff = 7/6 R_earth |

**Flat synthetic check:** astronomy-engine June 2026 sunrise az **60.515°**; flat model matches within **0.0°** (limit 0.1°). OK.

**Ridge delay of sunrise (2026), minutes after flat AE rise:**

| viewpoint | June solstice | December solstice |
|---|---|---|
| parcel_centroid | **30** | **65** |
| oak_leaf | **30** | **35** |
| ceremonial | **29** | **75** |

Outputs: `horizon.json`, `sky-events.json`. Cross-quarters listed with `evidence: traditional` only.

---

## C16.2 — water

| product | result |
|---|---|
| TWI | `analysis/grids/twi.npz` — breached DEM + D8, ln(a/tan β) |
| keylines | `keylines.geojson` + `analysis/keylines.png` — keypoints, keylines, swales 0.5–1%; topo_drain core vendored (MIT) |
| keypoint → ford | **26.69 m** |
| keyline → ford | **24.98 m** |
| stormwater | `analysis/stormwater.png` + grid — **25 mm** 1-in-10 1-hr proxy (Landlab OverlandFlow missing depth field on this grid; kinematic sheet used) |

---

## C16.3 — sun, cold, wind, landforms

| product | files |
|---|---|
| sun hours | Dec / Jun / annual grids + PNGs — clear-sky, 12×21st, 30 min; horizon + self-shade |
| GRASS r.sun | **not installed** on this machine — GPL external check skipped; noted |
| cold air / frost | `analysis/frost.png` + grid |
| thermal belt | `thermal-belt.geojson` |
| wind exposure | sea breeze **from 270° (W)**; Santa Ana **from 45° (NE)** |
| wind source | Ojai REC climatology appendix (DocumentCenter/View/1464) daytime westerly onshore; NWS SoCal Santa Ana NE offshore |
| landforms | TPI 20 m classes + 100 m scale; `analysis/landforms.png` |

---

## C16.4 — animal corridors

Circuitscape-style current (scipy sparse) creek → upslope woodland. `analysis/corridors.png` + grid.

**Synthetic wall+gap check:** gap current **0.086** vs wall **0.0086** (gap ≫ wall). OK.

---

## Generators

`scripts/horizon.py`, `sky_events.py`, `land_layers.py`, `land_grid.py`; `vendor/topo_drain/topo_drain_core.py`; `NOTICE`.
