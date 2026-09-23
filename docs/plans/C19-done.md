# C19 done — drawable land layers + where the land gathers

**Date:** 2026-09-22  
**Branch:** `eco/c19`  
**Generators:** `scripts/export-grid-rasters.py`, `scripts/gathers.py`  
**Checks:** `scripts/check-rasters.py`, `scripts/check-gathers.py`

---

## C19.1 — layer contract (drawable grids)

Every C16 land-reading `.npz` now has a matching plain georeferenced PNG at
`analysis/grids/<name>.png` — exactly `ncols × nrows` pixels, no axes, no title,
no colourbar. Encoding is **16-bit greyscale** (`uint16_greyscale`); nodata pixel
= **65535**. Row 0 of the PNG is the northmost row (`row_order: "north_to_south"`).

Decode formula (also in every sidecar):

```
if pixel == 65535: nodata
else value = value_min + (pixel / 65534) * (value_max - value_min)
```

| layer | units | evidence | raster | sidecar extras |
|---|---|---|---|---|
| `twi` | dimensionless | modelled | `analysis/grids/twi.png` | encoding, value_min/max, nodata, bounds_lnglat |
| `stormwater_depth` | m | modelled | `…/stormwater_depth.png` | same |
| `sun_hours_annual` | hours/year | modelled | `…/sun_hours_annual.png` | same |
| `sun_hours_dec` | hours/day | modelled | `…/sun_hours_dec.png` | same |
| `sun_hours_jun` | hours/day | modelled | `…/sun_hours_jun.png` | same |
| `cold_air` | dimensionless | modelled | `…/cold_air.png` | same |
| `wind_santa_ana` | 0–1 | modelled | `…/wind_santa_ana.png` | same |
| `wind_sea_breeze` | 0–1 | modelled | `…/wind_sea_breeze.png` | same |
| `corridors` | dimensionless | modelled | `…/corridors.png` | same |
| `landforms` | class 1–6 | modelled | `…/landforms.png` | same |
| `flow_accum` | m² | modelled | `…/flow_accum.png` | same |
| `gathers` | score 0–1 | modelled | `…/gathers.png` | + weights, exclusions |

`.npz` archives are unchanged. Contract page: `docs/layers.md`.

---

## C19.2 — weights (sum = 1.0)

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
| slope | 0.12 | full under 8°, zero above 20° |
| landform | 0.06 | flats / benches / spurs gain |

Hard exclusions (score forced to 0): creek + 15 m, stormwater flood cells,
16 ft easement, 5 m inside boundary, tree crowns + 3 m, top-decile animal corridors,
existing model footprints, slope > 20°.

Ranked polygons: contiguous cells above the **85th percentile** of usable scores
(after a 3×3 closing clipped to usable cells), each ≥ **100 m²**. Three areas ranked.

Figure: `analysis/gathers-figure.png`. Vectors: `gathers.geojson`.

---

## Proof cells

### Good — pack EN (418, 324) — sunny dry thermal-belt bench

| layer | value |
|---|---|
| sun_hours_annual | 135.0 h/yr |
| sun_hours_dec | 7.5 h/day |
| cold_air | 0.10 |
| twi | 2.43 |
| stormwater_depth | 0.001 m |
| wind_santa_ana | 0.10 |
| wind_sea_breeze | 1.0 |
| slope | 1.8° |
| landform | 4 (bench/flat) |
| thermal belt | yes |
| **gathers score** | **0.970** (top quintile; q80 ≈ 0.946) |

### Bad — pack EN (275, 234) — creek ford

| layer | value |
|---|---|
| gathers score | **0.0** (hard exclusion — creek + 15 m buffer) |
| twi | 12.35 (wet) |
| landform | 6 (channel) |

---

## What the map says

The land gathers on the mid-slope benches that sit in the thermal belt: sunny year-round
and still lit in December, dry underfoot, out of the frost pools and the Santa Ana
blast, gentle enough to stand on, and clear of the oaks, the creek, the easement, and
the animals' main paths. Three ranked patches — the largest about 1,370 m² on the
eastern / central benches — are where those conditions stack. The creek corridor, tree
crowns, and corridor spines stay empty on purpose.
