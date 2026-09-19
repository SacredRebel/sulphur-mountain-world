# C0 — pack survey

**Agent C — the land** · `SacredRebel/sulphur-mountain-world`  
**Date:** 2026-09-19  
**Authority of this document:** written survey only. No models built. Footprints and storey counts below for the 17 zones without geometry are **proposed**, not surveyed.

Notion (`Agent Phases`, Agent = C — the land) is the control surface. Where this chat brief and Notion disagree, **Notion wins**. Notably: Notion’s **C7 is interiors via LiteReality-Agent**, not stations/events; phases stop at C7 on the board (no C8/C9 rows yet).

---

## 1. What each file is, and how `pack.json` ties them

The engine loads **`pack.json` by URL** and renders the rest. Nothing in this repository is application code.

| Path | Role | Authority |
|---|---|---|
| `pack.json` | Manifest: id, situs, frame, spawn, layer index, sources, reconciliation, rules. `schema: 1`. | — |
| `survey.geojson` | Boundary (11 corners), 11 bearing/distance calls, 16 ft access easement (2 parts), 4 found monuments. | **survey** (2024-11-14) |
| `county.geojson` | Assessor parcel ring (drift only), 3 footprints with 2018 lidar height notes, road centrelines. | county |
| `roofs.geojson` | Lidar-derived roof planes: house, shed, McQueen’s Garage (157 m² warehouse county omits). | derived (2018) |
| `trees.csv` | 3,663 tree tops in local metric frame (dm integers). 367 in parcel. | derived (2018) |
| `vision.geojson` | 18 proposed zone **points** (placeholders until each has a model). | proposal |
| `edits.geojson` | Owner overlays applied on top of the record (never rewriting layers). | **owner** |
| `materials.json` + `textures/` | Close-up albedo/normal tiles (CC0 ambientCG, recoloured to site photos). | derived |
| `terrain/` + `terrain/index.json` | 13 USGS 3DEP terrarium PNGs (z13–17) so ground loads with the pack. | USGS / baked |

**How they rank:** survey beats county beats derived. County ring is never used for siting. The record is never rewritten — differences go in `edits.geojson` (`op` + `layer`).

**What `pack.json` also carries:**

- **`frame`** — origin lng/lat and metres-per-degree for converting `trees.csv` (see §4).
- **`aoi.bbox`** — surveyed parcel padded ~150 m; lidar layers cover this box.
- **`spawn`** — first arrival: lng/lat/heading (today: near the knoll, heading 200°).
- **`layers.*.file` / `kind`** — which file or XYZ/terrarium template to load.
- **`reconciliation[]`** — dated notes where lidar/county/owner disagree (trees by house, pad vs building, McQueen’s, county drift, etc.).
- **`rules[]`** — authority order; no personal names in the pack.

**Imagery** is streamed (Ventura 2025 Urban Aerial XYZ) and not committed. **Oak Leaf massing** is not in this pack: it lives in `spatial-map` as `scripts/massing/oak-leaf.py` → `.glb`, placed by the atlas registry (`sulphur-oak-house`). This pack only holds land edits that belong to that proposal (`edits.geojson` features with `"proposal": "sulphur-oak-house"`).

**Agent C must never write the registry.** Publish `models.json` (C6); the architect places rows.

---

## 2. Exact structure of `vision.geojson`

```text
FeatureCollection
  features[]: Feature
    geometry: Point  [lng, lat]     // EPSG:4326 — never a Polygon today
    properties:
      id          string   kebab-case, stable (zone key for models.json)
      name        string   display title
      type        string   agriculture | residential | community | hospitality |
                           infrastructure | creative | ceremonial | wellness |
                           beekeeping | events | landscape | …
      mode        string   today | vision | both
      emoji       string   atlas icon (not geometry)
      summary     string   programme text (may be truncated)
      placeholder true     always true until a model exists
      lidar_2018  string?  optional note when structure exists in 2018 lidar
```

**Eighteen features, all Points.** There is no zone polygon in this file. Territories were dropped (see `pack.json` reconciliation `zone-territories`): atlas grid cells did not contain their icons. Real territories come later from drawing on the aerial, or from each model’s `footprint` in `models.json`.

| id | name | type | mode | lng, lat (approx) |
|---|---|---|---|---|
| `agricultural-hub` | Agricultural Hub | agriculture | vision | −119.155982, 34.433478 |
| `main-residence` | Main Residence Compound | residential | both | −119.155333, 34.433118 |
| `community-hub` | Community Hub | community | vision | −119.155387, 34.432771 |
| `retreat-village` | Retreat Village | hospitality | vision | −119.155628, 34.432173 |
| `infrastructure` | Infrastructure & Utilities | infrastructure | vision | −119.155966, 34.432386 |
| `mcqueens-garage` | McQueen's Garage | creative | both | −119.155279, 34.432549 |
| `ceremonial-infrastructure` | Ceremonial Infrastructure | ceremonial | vision | −119.155582, 34.432501 |
| `wellness-facilities` | Storage Structures | wellness | both | −119.155062, 34.43293 |
| `mushroom-cultivation` | Mushroom Cultivation | agriculture | vision | −119.156218, 34.433474 |
| `beekeeping-program` | Beekeeping & Honey Production | beekeeping | vision | −119.15582, 34.433477 |
| `events-gatherings-hub` | Events & Gatherings Hub | events | vision | −119.155065, 34.433394 |
| `livestock-dairy` | Livestock & Dairy Program | agriculture | vision | −119.156143, 34.432797 |
| `creative-workshop-center` | Creative Workshop & Art Creation Center | creative | vision | −119.156486, 34.43347 |
| `glamping-creek-village` | Creek-Side Glamping & Lodging Village | hospitality | vision | −119.15654, 34.432479 |
| `gatelodge-operations-hub` | The Barn | infrastructure | both | −119.156728, 34.433082 |
| `tropical-dome-greenhouse` | Tropical Dome Greenhouse | agriculture | vision | −119.156763, 34.432888 |
| `sulphur-mountain-sanctuary` | Sulphur Mountain Sanctuary | landscape | vision | −119.155827, 34.433038 |
| `farmstead-produce-stand` | Farmstead Produce Stand & Online Hub | agriculture | vision | −119.156935, 34.432483 |

**One zone already has a walkable massing (outside this repo):** `main-residence` → Oak Leaf (`sulphur-oak-house`). Notion: leave it alone; it is the reference. The other **17** are labels over bare ground until C2–C5.

---

## 3. How `oak-leaf.py` emits `extras.walk`, and what is reusable

Read from `SacredRebel/spatial-map` (reference only — **never commit there**):

- `scripts/massing/glb.py` — shared writer
- `scripts/massing/oak-leaf.py` — the model *is* the script

### Contract (from `glb.Model`)

```ts
extras.walk = {
  floors[]: { name, ring: [x, z][], top }   // standable surfaces
  solids[]: { name, ring: [x, z][], base, top }  // collision volumes
}
```

- Metres, model-local.
- Rings are **open** (first point not repeated); consumer closes them.
- `Model.floor()` / `Model.solid()` append to `self.walk`.
- `Model.write(path, extras=…)` puts `{ walk, **extras }` on the **root node** and on the scene.

### Frame helper in oak-leaf

```python
def P(e, n, y=0.0):
    """plan (east, north) → model (x east, y up, z south)"""
    return (float(e), float(y), float(-n))

def ring_xz(pts):
    return [(float(e), float(-n)) for e, n in pts]
```

**Z-negation happens here:** plan coordinates are (east, north); model `z = -north`. Walls and floors always call `ring_xz` / `P` so walk rings and mesh vertices share one frame.

### Origin

Named landmark: the **existing river-stone chimney** at `(0,0)` in plan metres — not the centroid. Registry places the GLB so that origin sits on the real chimney.

### Doors

A door is a **gap** in the solid run (`doors=[(t0,t1), …]` skipped in `leaf_walls`), never a `door: true` flag.

### Materials (today in oak-leaf — **anti-pattern for Agent C**)

Hardcoded `Material('timber', (0.55, 0.38, 0.22), …)` RGB tuples. C1b requires every script to read **this pack’s** `materials.json` instead. Glass already uses `alphaMode: BLEND` when `alpha < 1` in `glb.Material.gltf()`.

### Reusable for this repo’s toolkit (C1)

| Take | Leave |
|---|---|
| `glb.py` pattern: one mesh per material, walk floors/solids, metre Y-up Z-south | Hardcoded colours |
| `P` / `ring_xz` plan→model | Leaf-specific PCHIP roof math (unless needed) |
| Door-as-gap, open rings, named origin | Writing into `spatial-map` or the registry |
| Size budget awareness (phone / cellular) | Interior fit-out (C7 / LiteReality later) |
| Script prints `{bytes, triangles, floors, solids}` | Assuming Oak Leaf is authored here |

---

## 4. The frame, and where z-negation happens

### Pack frame (`pack.json` → `trees.csv`)

```text
lng = origin_lng + x / metres_per_deg_lng
lat = origin_lat + y / metres_per_deg_lat
```

- Origin: (−119.1594805, 34.4304373)
- `trees.csv` columns: `x_east_dm`, `y_north_dm`, … in **integer decimetres** (east / north).
- All GeoJSON: plain **EPSG:4326**.

This frame is for **tabular tree positions**, not for GLB vertices.

### Model frame (massings)

| Axis | Meaning |
|---|---|
| +x | east |
| +y | up |
| +z | **south** (= −north in plan) |

**Z-negation** is the conversion from site plan (E,N) to glTF (x,y,z): `z = −N`. It is applied in the massing script (`P`, `ring_xz`), not in the pack’s GeoJSON. Get this wrong and the building faces the wrong way when placed on the map.

Placement (architect / registry): origin lng/lat + `rotationDeg` + `altitudeM` transform model metres onto the ellipsoid/terrain. Agent C publishes those fields in `models.json`; does not write the registry.

---

## 5. What is in `materials.json`, and what surfaces are missing

### Present (ground / bark close-ups)

Each entry: `albedo`, `albedo_512`, `normal`, `metres` (tile repeat), `source` (ambientCG), optional `matched_to` photo colour.

| Key | Use today (intended) |
|---|---|
| `straw` | mowed field |
| `dirt` | dirt drive |
| `gravel` | gravel drive |
| `litter` | leaf litter under oaks |
| `asphalt` | county road (no photo match yet) |
| `bark` | oak trunks |

**Gap:** these tiles exist (~4.8 MB under `textures/`) but the walkable world still draws untextured grey massings. Fix path: C1b — extend the palette for **buildings**, wire `glb.py` to emit real glTF PBR from this file, reuse ≤512 px textures across models. No colour hardcoded in a script.

### Missing surfaces (required by C1b / Notion)

Building massings need entries (base colour, roughness, metalness, opacity — and textures where appropriate, ≤512 px, shared):

| Surface | Why |
|---|---|
| stone | walls, standing stones, plinths |
| river stone | chimney, retaining (Oak Leaf reference) |
| timber | structure, decking, ribs |
| board-and-batten | cabin / barn cladding |
| glass | curtain walls, dome panels (`alphaMode: BLEND`) |
| stucco | workshop / hub shells |
| concrete | pads, aprons, lower floors |
| living roof | green roofs (Oak Leaf) |
| standing-seam metal | barn / shed roofs |
| canvas | glamping / tipís |

Also useful later (not in the C1b list but likely): decomposed granite paths, water — keep them proposed until authored.

---

## 6. Proposed footprint and storey count — 17 zones without geometry

**Authority: proposed.** Sized from zone summaries, 2018 lidar notes, and neighbour spacing — not from a new survey. `footprint` in `models.json` must mark **built ground only** (suppresses trees). Outdoor rooms among oaks stay outside the footprint.

`main-residence` is omitted (Oak Leaf already exists).

| Zone id | Storeys (proposed) | Footprint sketch (proposed) | Notes |
|---|---|---|---|
| `retreat-village` | 1 (+ loft option on 2–3 units) | Cluster envelope ~45×35 m; **per-unit** built pads ~6×8 m + deck ~3×4 m; 8–10 units | Seeded parametric ADU (C2). Paths between; not a grid. Orient to view/sun. Ridge/hillside siting near (−119.15563, 34.43217). |
| `glamping-creek-village` | 1 (platforms) | 5 Phase-1 tipí/yurt pads ~5 m Ø + shared path; cluster ~60×25 m along creek corridor | Units sit **lower** than ridge (~1–1.5 m) and face the draw. Canvas + timber decks. Trees between pads: **outside** footprint. |
| `gatelodge-operations-hub` | 1–2 | Barn massing ~12×18 m (expand toward programme; lidar today ~28 m² / 2.2 m — **small**) | Confirm on fence walk. Vision: gatelodge ADU at entrance. Working barn character first. |
| `agricultural-hub` | 1 | Open shed + potting wing ~20×12 m; nursery yard **not** all in footprint | Propagation / gardens: suppress only roofed ground. |
| `tropical-dome-greenhouse` | 1 (dome) | Geodesic ~10–12 m Ø clearspan; ribs + glass | Real dome geometry (C3). Light through glass. |
| `community-hub` | 1 | Pavilion / outdoor kitchen ~15×10 m around restored fireplace; seating terraces outside footprint if among trees | Occupancy target to state at commit (~40–60 standing). |
| `events-gatherings-hub` | 1 | Covered stage/barn ~18×24 m; overflow lawn not footprint | Capacity ~150–200; state in commit. |
| `ceremonial-infrastructure` | 1 (kiva floor + low wall) | Stone/earth circle ~12–14 m Ø; fire ring centre | In front of McQueen’s. Minimal built ground. |
| `sulphur-mountain-sanctuary` | 0–1 | Paths + small overlook ~4×4 m only | Living landscape — mostly **no** vegetation-suppressing footprint; gardens/paths among oaks stay open. |
| `infrastructure` | 1 | Utility yard: tank pads, solar rack, shed ~8×6 m | Working kit, not monumental. |
| `mcqueens-garage` | 1 | Align to lidar roof ~157 m² planar + larger true warehouse; propose ~25×18 m / ~4 m eaves | County has no footprint. Creative / ceremony interior later (C7). |
| `wellness-facilities` | 1 | Storage row today: 2–3 sheds ~6×4 m each; vision wellness later same pads | Lidar: no clean roof; survey sheds nearby unresolved. |
| `mushroom-cultivation` | 1 | Climate sheds / containers ~12×8 m | Commercial grow — opaque walls, low eaves. |
| `beekeeping-program` | 0–1 | Apiary yard; one tool shed ~3×4 m | Hives themselves may be props; minimal footprint. |
| `livestock-dairy` | 1 | Open barn ~20×12 m + pen rails; pasture **outside** footprint | Rotational grazing fields must not erase trees/grass as “built”. |
| `creative-workshop-center` | 1–1.5 | Workshop hall ~16×10 m, north light | Wood / pottery / natural building. |
| `farmstead-produce-stand` | 1 | Roadside stand ~6×4 m + canopy at gate | Direct sales at entrance; small. |

### Placement discipline (for C2–C5)

1. Origin = a point someone can point at (door threshold, chimney, barn ridge end) — not centroid.
2. Cluster retreat/glamping with paths; never a perfect grid.
3. Creek units differ in altitude and orientation from ridge units.
4. Update `models.json` (C6) after every massing phase.
5. Grey boxes are not done once C1b lands.

---

## 7. Interiors later — LiteReality-Agent (Notion C7)

**Do not hand-build interior geometry** in massing scripts.

Planned route ([LiteReality-Agent](https://github.com/pascalorg/LiteReality-Agent), Apache 2.0): iPhone room scan → `Room.glb`. Its “a script IS the model” manifest pattern matches `oak-leaf.py`. Notion phase **C7** (depends on C5): note this route now so C2–C5 stay shells with correct size and walk data only.

---

## 8. Gaps this pack already records (relevant to massing)

From `pack.json` `reconciliation` and README:

- Trees within 12 m of the house: removed via `edits.geojson` (record in `trees.csv` untouched).
- County footprint #1 is a concrete pad, not a building.
- McQueen’s Garage in lidar, absent from county.
- Survey sheds / fences / poles / dirt roads still only on atlas raster — fence walk needed.
- County vs survey drift up to ~29 ft west.
- The Barn looks small in 2018 lidar — confirm on site.
- Oak Leaf parking court / sacred gardens / oak lounge are owner proposal edits, not surveyed structures.

---

## 9. C0 acceptance checklist

- [x] What each file is and how `pack.json` ties them
- [x] Exact structure of `vision.geojson`
- [x] How `oak-leaf.py` / `glb.py` emit `extras.walk` and what is reusable
- [x] Frame and where z-negation happens
- [x] `materials.json` contents and missing building surfaces
- [x] Proposed footprint + storey count for each of the 17 zones without geometry
- [x] LiteReality noted as interior route (Notion C7)
- [x] No models built
