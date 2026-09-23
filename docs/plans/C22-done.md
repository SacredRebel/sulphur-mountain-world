# C22 done — settle the water number, draw the rest of the land

**Date:** 2026-09-23  
**Branch:** `eco/c22`  
**Generators:** `scripts/water-harvest.py`, `scripts/export-drawable-extras.py`, `scripts/pack-layers.py`  
**Checks:** full suite; `check-water` and `check-pack-layers` hardened to the standing rule

C21's water headline rested on two numbers that could not both be true. C22 names the
bug, publishes one routed area, shows on-channel and off-channel variants side by side,
and draws the four pack layers that belonged in the atlas.

---

## C22.1 — the routing bug, in plain words

C21 published `routed_m2` = **3,752** from a D8 walk and `catchment_sum_m2` = **13,026**
from per-work catchments, then derived held volume from the second (117 m³ / 34%). From
the first it would have been 33.8 m³ / **9.8%**. They differed 3.5×.

**What was wrong**

1. The walk treated the creek `channel_mask` as a flow sink. Paths that hit the channel
   left the harvest set before reaching a work, so `routed_m2` undercounted — and landed
   almost on pond-1's catchment alone (~3,825), which is the smell that led here.
2. Per-work catchments were taken from nested `flow_accum` at each work cell. Upstream
   cells shared by several works were counted once per work, so the sum double-counted.
   The sum was not a union.

**Neither figure was the exclusive drainage area.** Averaging them, or forcing one to
match the other, would have been dishonest.

**Fix:** exclusive first-hit D8 — every parcel cell walks downhill until it first hits a
harvest work (or leaves the parcel). No channel sink. Each cell belongs to at most one
work. `routed_m2`, `catchment_sum_m2` and `catchment_union_m2` are the same quantity.

| quantity | C21 (wrong) | C22 |
|---|---:|---:|
| routed_m2 | 3,752 | **11,647** |
| catchment_sum_m2 | 13,026 | **11,647** |
| held m³ (25 mm event) | 117.2 | **88.0** |
| % of parcel runoff | 34.0% | **25.5%** |
| held gallons | ~31,000 | **23,247** |

Parcel runoff is unchanged at 344.8 m³. The 9.8% figure was the honest reading of the
undercounted walk; it is not the truth once the sink is removed. The honest exclusive
number is **25.5%**.

Independent check: `check-water` recomputes exclusive routed area from DEM + geojson
work footprints (EN-buffered) and asserts it agrees with the published figure within 2%.
Union equals sum within 2% because the method is exclusive by construction.

---

## C22.2 — catchments visible, two variants

Seven catchment polygons are in `water-harvest.geojson` (kind=`catchment`), each with
`work_id`, `area_m2` and `method: exclusive_first_hit_d8`.

All three primary ponds remain `on_channel: true`. The off-channel variant drops those
in-channel ponds and places three off-channel ponds by the same method so the comparison
is same-method, not empty.

| variant | works | held m³ | gallons | % of 25 mm runoff |
|---|---:|---:|---:|---:|
| **all_works** (published headline) | 4 swales + 3 on-channel ponds | 88.0 | 23,258 | **25.5%** |
| **off_channel** | 4 swales + 3 off-channel ponds | 56.0 | 14,796 | **16.2%** |

The **all_works** figure needs a permitting answer before it is real — every pond sits
on/near a defined watercourse (`on_channel: true`). The off-channel variant does not
carry that flag on its ponds; it is a different regulatory question. Neither is
recommended here. The owner chooses.

---

## C22.3 — draw the rest of the land

Added to `pack-layers.json` (C21 contract: bounds, legend, `style_by`, authority/evidence):

| layer | kind | notes |
|---|---|---|
| `trees_crowns` | geojson | 3,663 crown circles, `style_by: height_m` (= `trees.csv` row count) |
| `trees_trunks` | geojson | trunk points |
| `cultivated_ground` | geojson | styled by class |
| `horizon` | geojson | ridgeline line; units stated in manifest |
| `terrain` | image | hillshade display PNG; RGB span 1.0 (> 0.5) |

### `not_drawable` (every remaining `pack.json` layer, one-line reason)

| pack key | reason |
|---|---|
| models | GLB inventory and meshes — engine loads, not a map overlay |
| scans | placement table; splat binaries stay private / gitignored |
| positions | placement CSV for the engine, not an atlas drawable |
| materials | material table, not geometry |
| imagery | streamed XYZ tiles, never committed |
| county | assessor ring kept for drift checks, not for siting or drawing |
| trees | tabular crowns; drawn as trees_crowns + trees_trunks |
| cultivated | tabular plantings; drawn as cultivated_ground |
| sky_events | event table awaiting C26 alignments drawable |
| terrain | terrarium tile pyramid; hillshade display is layer terrain |

`terrain_hillshade` aliases to manifest `terrain`. Coverage is asserted by
`check-pack-layers` (forges a missing layer in `--self-test`).

### Manifest count by group

33 layers total — **15 image**, **18 geojson**:
defensible=1, habitat=7, proposed=4, sun=4, surfaces=7, terrain=4, water=6.

---

## Check audit against the standing rule

A check earns its keep only by making two separately derived quantities agree.

| check | two paths? | changed in C22? |
|---|---|---|
| `check-water` | published routed vs independent exclusive D8 recompute; union vs sum | **yes** — primary asserts; partition kept secondary; `--self-test` forges routed mismatch |
| `check-pack-layers` | crown count vs `trees.csv`; hillshade span; pack key ∈ manifest ∨ not_drawable | **yes** — coverage + trees + hillshade |
| `check-surfaces` | oak cell from npz+trees.csv vs bands | already (C21) |
| `check-rasters` | npz cell vs PNG decode | already (C20/C21) |
| `check-defensible` | geojson rings vs trees.csv distances | already |
| `check-gathers` | npz vs hand EN probe | already |
| `check-frame` | frame constants vs survey/EN round-trip | already independent |
| `check-lods` | declared LOD files vs on-disk sizes/presence | already |
| `check-materials` | materials.json vs expected keys/files | already |
| `check-positions` | positions.csv vs models/survey geometry | already |
| `check-paths` / `check-edits` / `check-scans` / `check-overlaps` | file/geometry consistency | already; not reworked |

---

## Named assumptions (unchanged C)

runoff C = 0.45, infil 5 mm during event, pond depth 1.2 m, season 400 mm proxy —
all in `water-harvest.json`. `assumptions.c21_headline_was` records the retired 34% claim.
