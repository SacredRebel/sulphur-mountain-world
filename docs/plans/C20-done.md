# C20 done — buildable ≠ gathering, then fire and water

**Date:** 2026-09-22  
**Branch:** `eco/c20`  
**Generators:** `scripts/surfaces.py`, `scripts/defensible-space.py`, `scripts/water-harvest.py`  
**Checks:** `scripts/check-rasters.py`, `scripts/check-surfaces.py`, `scripts/check-defensible.py`, `scripts/check-water.py` (+ prior suite)

C19's single `gathers` map answered "where could a foundation stand?" and accidentally
treated oak canopy as a disqualification for gathering. C20 splits that question in two,
reports bands instead of a top-three cut, then adds defensible-space rings and a
storm-sized water harvest.

Also fixed: `check-rasters` now probes **non-zero** cells across the value range
(the previous three fixed probes could all decode to 0 and pass for the wrong reason).

---

## Headline

Of the **9.46 acres** inside the survey, roughly **1.74 acres** is open ground once
oaks (crown + 3 m), the creek buffer, the easement, animal corridors and existing
footprints are respected. That is the honest buildable envelope. Gathering is a
different map: shade under oaks is welcome, so far more of the parcel scores.

---

## C20.1 — two surfaces, bands not a top three

### `buildable` weights (sum = 1.0) — canopy excluded

| factor | weight | direction |
|---|---:|---|
| sun hours annual | 0.18 | more sun better |
| sun hours December | 0.12 | winter sun better |
| cold air (inverted) | 0.12 | frost pooling loses |
| thermal belt | 0.08 | belt gains |
| TWI (inverted) | 0.10 | dry underfoot better |
| stormwater (inverted) | 0.08 | dry underfoot better |
| Santa Ana (inverted) | 0.10 | exposure loses |
| sea breeze | 0.04 | light breeze gains |
| slope | 0.12 | gentle preferred |
| landform | 0.06 | flats / benches / spurs gain |

Hard exclusions: creek + 15 m, stormwater flood cells, 16 ft easement, 5 m inside
boundary, **tree crowns + 3 m**, top-decile animal corridors, model footprints,
slope > 20°. Same exclusion set as C19 `gathers`.

### `gathering` weights (sum = 1.0) — canopy earns shade

| factor | weight | direction |
|---|---:|---|
| sun hours annual | 0.12 | more sun better |
| sun hours December | 0.10 | winter sun better |
| cold air (inverted) | 0.10 | frost pooling loses |
| thermal belt | 0.06 | belt gains |
| TWI (inverted) | 0.08 | dry underfoot better |
| stormwater (inverted) | 0.06 | dry underfoot better |
| Santa Ana (inverted) | 0.08 | exposure loses |
| sea breeze | 0.04 | light breeze gains |
| slope | 0.10 | gentle preferred |
| landform | 0.06 | flats / benches / spurs gain |
| **shade** | **0.20** | under crown, boosted where Dec sun still reaches |

Hard exclusions for gathering: creek, easement, boundary setback, corridors,
footprints, **trunks only (1.5 m radius)** — not the whole crown. Canopy is scored,
not zeroed.

Each surface is rescaled across its own surviving population so the full 0–1 range
is used. Contiguous polygons carry `rank`, `band`, `score`, `area_m2`, `reasons`.
Bands on the rescaled score: **best ≥ 0.67**, **good ≥ 0.33**, **workable ≥ 0.05**.

`gathers` remains an **alias of `buildable`** for one phase (`alias_of: buildable`
in the sidecar and `pack.json`).

### Band areas (1 m cells ≈ m²)

| surface | band | m² | acres | score range (rescaled cells) |
|---|---|---:|---:|---|
| buildable | best | 6,532 | 1.61 | 0.67 – 1.00 |
| buildable | good | 490 | 0.12 | 0.33 – 0.67 |
| buildable | workable | 28 | 0.01 | 0.08 – 0.33 |
| buildable | **total above workable** | **7,050** | **1.74** | |
| gathering | best | 3,223 | 0.80 | 0.67 – 1.00 |
| gathering | good | 11,393 | 2.82 | 0.33 – 0.67 |
| gathering | workable | 172 | 0.04 | 0.13 – 0.33 |
| gathering | **total above workable** | **14,788** | **3.65** | |

### Oak proof cell (the whole point of the split)

Pack EN ≈ **(260.8, 267.8)** — under a large oak crown, away from any trunk:

| surface | score |
|---|---:|
| `buildable` | **0.000** |
| `gathering` | **1.000** |

A cell ~1 m from a trunk (EN ≈ 283.8, 150.8) is **0 on both**.

---

## C20.2 — defensible space (modelled, not an inspection)

Distances from each `models.json` footprint: Zone 0 = 0–1.5 m, Zone 1 = 1.5–9.1 m,
Zone 2 = 9.1–30.5 m. On slopes > 20%, Zone 2 outer radius extends **1.5× downhill**
(isotropic larger buffer). This is a geometric reading of published zone distances —
**not a fire-agency inspection**, and **no tree removal is implied**.

| structure | slope % | Z2 outer m | Z0 crowns | Z1 canopy % | Z2 crosses boundary |
|---|---:|---:|---:|---:|---|
| oak-leaf-massing | 0.0 | 30.5 | 15 | 22.5 | yes |
| retreat-village | 64.3 | 45.75 | 23 | 70.0 | yes |
| glamping-creek | 14.0 | 30.5 | 21 | 69.0 | no |
| the-barn | 12.5 | 30.5 | 5 | 37.5 | yes |
| agricultural-hub | 6.2 | 30.5 | 6 | 50.8 | yes |
| tropical-dome | 31.2 | 45.75 | 5 | 63.5 | yes |
| creek | 8.8 | 30.5 | 39 | 58.8 | yes |
| community-hub | 0.0 | 30.5 | 9 | 42.5 | yes |
| events-gatherings-hub | 6.2 | 30.5 | 0 | 2.0 | yes |
| wellness-facilities | 6.2 | 30.5 | 7 | 31.8 | yes |
| livestock-dairy | 0.0 | 30.5 | 4 | 30.8 | no |
| mushroom-cultivation | 22.5 | 45.75 | 3 | 54.5 | yes |
| beekeeping-program | 14.0 | 30.5 | 2 | 53.0 | yes |
| farmstead-produce-stand | 31.2 | 45.75 | 3 | 44.0 | yes |
| infrastructure | 19.8 | 30.5 | 15 | 46.0 | no |
| ceremonial-infrastructure | 12.5 | 30.5 | 5 | 36.5 | no |

Outputs: `defensible-space.geojson`, `defensible.json`, `analysis/defensible-space.png`.

---

## C20.3 — water harvest sized to a 25 mm event

### Assumptions (every one named)

| assumption | value | note |
|---|---|---|
| runoff coefficient C | **0.45** | Assumed for a 1-hour 25 mm event on mixed oak/grass/compacted hillside — **not measured on site**. |
| infiltration during event | **5 mm** | Sandy-loam order of magnitude — **not a field measurement**. |
| swale cross-section | **0.15 m²** | Assumed 0.6 m wide × 0.3 m deep trapezoid. |
| pond depth | **1.2 m** | Assumed useful depth for tank/pond sizing. |
| season proxy | **400 mm** | Season volume = event catch × (400/25) — named proxy, not a climate series. |
| useful hold | min(capacity, event volume) | Capacity alone would overstate what one storm delivers. |

### Parcel numbers

| quantity | value |
|---|---|
| parcel | 38,310 m² ≈ 9.47 acres |
| rain on parcel (25 mm) | 958 m³ |
| runoff (C=0.45, after 5 mm infil) | **345 m³** |
| swale capacity (8 × 25 m × 0.15) | 30 m³ |
| pond capacity (3 sites) | 724 m³ (geometry) |
| **held from one event** | **58 m³ (16.8% of runoff)** |
| catchment sum (swales + ponds) | 21,655 m² ≤ parcel + upslope 39,951 m² |

### Ponds (on `buildable` ground)

| id | catchment m² | event m³ | season m³ | buildable score |
|---|---:|---:|---:|---:|
| pond-1 | 1,452 | 13.1 | 131 | 0.654 |
| pond-2 | 1,087 | 9.8 | 98 | 0.577 |
| pond-3 | 575 | 5.2 | 52 | 0.745 |

Outputs: `water-harvest.geojson`, `water-harvest.json`, `analysis/water-harvest.png`.

---

## What the three maps say together

**Buildable** is the thin open ground — about 1.74 acres — where a structure could
stand without sitting under a recorded oak, in the creek, or on a corridor. **Gathering**
is the larger map that keeps those oaks: shade is a score, not a ban, so people-places
can sit under canopy while foundations cannot. **Defensible space** then tells, for every
proposed footprint, how many crowns sit in the ember and lean-and-green rings and whether
Zone 2 crosses the neighbour's line. **Water harvest** sizes the existing keyline swales
and three pond sites to one 25 mm storm and shows they would hold roughly a sixth of the
parcel runoff under the named assumptions — useful order of magnitude, not a drainage
design.

Figures: `analysis/buildable-figure.png`, `analysis/gathering-figure.png`,
`analysis/defensible-space.png`, `analysis/water-harvest.png`.
