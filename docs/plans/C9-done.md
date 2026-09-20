# C9 done — cultivated ground as data

**Date:** 2026-09-20  
**Architect override:** board C9 (LiteReality interiors) deferred — this phase is orchard rows, garden beds, and cultivated-ground footprints. Interiors stay later.

---

## Passing fix — Oak Leaf footprint

The manifest shipped a 4-point AABB of **2,767 m²**. That proposed clearing the oak lounge and garden stones with the house. Replaced with a **57-point built-ground outline of 772 m²** (raster union of built floors ≈ 867 m²), excluding `oak lounge` and `garden stone` so recorded oaks there survive. Generator: `scripts/oak-footprint.py`.

---

## Contract

**No tree meshes.** Positions only — same local frame as `trees.csv` (integer decimetres), plus a `species` column. The engine instances them. Cultivated-ground polygons keep the **wild** vegetation rule out of orchard and beds.

---

## Spacing (chosen)

| crop | spacing | why |
|---|---|---|
| **olive** | **6.0 m** in-row and between rows | Mediterranean hillside orchard — the primary block |
| **citrus** | **5.0 m** | Smaller block by the beds |

Rows follow a contour-ish grid on the slope south-east of the agricultural hub (along-row mostly east; downhill south).

---

## What was authored

| piece | file | bytes | content |
|---|---|---|---|
| plant positions | `cultivated.csv` | **3,114** | 108 rows + header |
| wild-rule footprints | `cultivated-ground.geojson` | **5,620** | 6 beds + 2 orchard polygons |

### Counts

| species | positions | spacing | height | crown |
|---|---|---|---|---|
| olive | **84** (7 × 12) | 6.0 m | 4.5 m | 3.0 m |
| citrus | **24** (4 × 6) | 5.0 m | 3.2 m | 2.4 m |
| **total** | **108** | — | — | — |

### Garden beds (aerial signature)

Six rectangles south of the ag-hub shed: **8.0 × 1.2 m** each, 0.8 m paths between, long axis east–west. Footprints only (cultivated ground) — no plant meshes.

---

## Pack registration

`pack.json` layers:

- `cultivated` → `cultivated.csv` (extends the tree-layer frame with `species`)
- `cultivated_ground` → `cultivated-ground.geojson` (`suppresses: wild_vegetation`)

Scripts: `scripts/cultivated.py`, `scripts/oak-footprint.py`.
