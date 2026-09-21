# C12 done — Oak Leaf knoll site analysis

**Date:** 2026-09-21  
**Architect override:** describe the knoll for a slope-following house redesign. **Analysis only — no house proposed.**

Also closed out C11 kiva: **owner decision open-air** — complete as built.

---

## Window

| | |
|---|---|
| centre | **−119.15536, 34.4331** |
| extent | **100 × 100 m** |
| sample step | **1 m** (matches DEM source resolution) |

Measured context (given): across the current Oak Leaf footprint the pack DEM falls **5.44 m**, lowest toward the south-west (bearing **228°**). Window relief is **7.81 m** (419.19–427.00 m).

---

## Sources and resolution

| layer | pack file | source | resolution |
|---|---|---|---|
| elevation, contours, slope | `terrain/{z}/{x}/{y}.png` | USGS 3DEP 1 m (CA_SoCal_Wildfires_B3_2018), terrarium | **1 m**; pack maxzoom 17 |
| oaks + drip line | `trees.csv` | 2018 lidar CHM local maxima; `crown_radius_dm` → drip-line radius | tops &lt; 2.5 m omitted; positions integer dm |
| owner removals (flag) | `edits.geojson#trees-around-the-house` | owner 2026-09-18 | 12 m buffer around county house footprint |
| plan frame | `pack.json` frame | equirectangular metres at origin_lat | ~91.8 m/° lng, 110.5 m/° lat |

No species column in `trees.csv` — on this knoll the recorded canopy is treated as the surveyed oaks. Removals are flagged, not deleted from the record.

---

## Findings

| product | result |
|---|---|
| contours | **0.5 m** interval |
| slope &lt; 15% | **78.5%** of window |
| slope 15–25% | **10.0%** |
| slope &gt; 25% | **11.5%** |
| buildable envelope | largest contiguous &lt;15%: **5,922 m²** |
| oaks in window | **69** (55 standing / 14 removed by owner edit) |

---

## Outputs

| file | what |
|---|---|
| `analysis/oak-leaf-knoll.geojson` | metadata, slope-class polygons, buildable envelope, contours, oak points |
| `analysis/oak-leaf-knoll.png` | top-down plan, north up, scale bar, legend |

Generator: `scripts/oak-leaf-knoll.py`. Registered in `pack.json` as `layers.oak_leaf_knoll`.
