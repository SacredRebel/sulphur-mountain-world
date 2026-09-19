# Sulphur Mountain — the world data pack

11962 Sulphur Mountain Rd, Ojai · APN 037-0-012-125 · 9.465 surveyed acres

This repository is one property's ground truth for the walkable world
([spatial-map](https://github.com/SacredRebel/spatial-map)): the surveyed
boundary, what stands on the land, what grows on it, and what is proposed
for it. The engine loads `pack.json` by URL and renders the rest. There is
one engine and one pack per property. No application code lives here — the only code is
`scripts/`, the generators that build this property's own derived data, kept beside what they
produce so every model has its provenance.

## What is in it

| file | authority | date | what |
|---|---|---|---|
| `pack.json` | — | 2026-09-18 | the manifest: frame, layers, sources, and the reconciliation list |
| `survey.geojson` | **survey** | 2024-11-14 | the boundary from the eleven surveyed corners, every call with bearing and distance, the 16 ft access easement, the four found monuments |
| `county.geojson` | county | read 2026-09-18 | the assessor's parcel ring (kept to show the drift), the three county building footprints with their measured 2018 roof heights, the road centrelines |
| `roofs.geojson` | derived | 2018 | roof planes recovered from the lidar under the tree canopy: the house, a shed, and a 157 m² building the county does not map |
| `trees.csv` | derived | 2018 | 3,663 tree tops with height, crown radius and ground elevation; 367 inside the line, 96 per hectare |
| `vision.geojson` | proposal | — | the 18 proposed project zones, 14 with drawn territories — placeholders until each has a model |
| `edits.geojson` | **owner** | 2026-09-18 | what the owner has said differs from the record, applied by the world on top of the layers: the trees within 12 m of the house are gone; and what the Oak Leaf proposal asks of the land — its parking court cut into the south bank, the sacred gardens, the oak lounge |
| `models/` | proposal | — | the proposed structures as walkable GLB, `extras.walk` carrying floors and solids; built by `scripts/` and committed |
| `scripts/` | — | — | the generators: a model IS its script. `node scripts/build-models.mjs` rebuilds `models/` |
| `materials.json` + `textures/` | derived | 2026-09-18 | close-up ground, road and bark tiles: CC0 materials from ambientCG, recoloured to the owner's photographs of this land |
| `terrain/` | USGS 3DEP | 2018 lidar, baked 2026-09-17 | the 1 m ground as 13 terrarium tiles with their index — the pyramid the world walks on |

Imagery (the county's 2025 aerial, ~12 cm/px) is streamed from its publisher
by URL and is not copied here. The ground (USGS 3DEP 1 m, baked to terrarium
tiles by the atlas) is kept in `terrain/` — 13 tiles, z13–17, about 700 KB —
so the world can stand on this property with nothing but this repository.

## How the layers rank

Survey beats county beats derived. The county ring disagrees with the
surveyed line by up to 29 ft on the west side; it is kept so the drift is
visible, and it is never used to site anything. The lidar is from 2018: it
knows the ground, the roofs and every tree as of that flight, and the
`reconciliation` list in `pack.json` records what has changed since — one
county "footprint" is a concrete pad, one real building has no county
footprint at all, and the trees that stood over the house are gone.

The record is never rewritten. When the owner says the land differs from
the record, the difference goes in `edits.geojson` as its own dated,
attributed feature and the world applies it on top. Each feature has an
`op` and a `layer`:

    remove · trees   a Point with radius_m, or a Polygon with buffer_m
    add    · trees   a Point with height_m (and crown_m): a tree that is there now
    move   · vision  target = a project's id, and the Point it really goes at
    remove · vision  target = a project's id that is off the table
    add    · notes   a Point with a name: a marker (the gate, the well, a photo)
    add    · lines   a LineString with a kind (fence, path, road) and a name
    add    · zones   a Polygon with a name and a kind: a territory on the ground
    add    · terrain a Polygon with terrain_op (flatten, raise, lower),
                     height_m or to_m, and edge_m: the ground shaped, with
                     a bank that eases back into the hill
    add    · build   a part of a building, by kind — a wall (a LineString
                     along its centre: height_m, thick_m, material, smooth,
                     base_m, openings[] of doors and windows, structure),
                     a floor (a Polygon: level_m, thick_m, material) or a
                     roof (a Polygon: form flat/shed/gable/hip/vault,
                     eaves_m, pitch_deg, overhang_m, ridge_deg, material)
    remove · build   target = the id of a part taken down

A later feature with the same id replaces the earlier one — that is how a
wall is changed: it is added again, taller, or moved, under its own id.

A feature may carry `proposal`: the id of a designed structure in the atlas's
registry (`sulphur-oak-house`, the Oak Leaf massing). It belongs to that
proposal — the ground shaped for it, the gardens laid out round it — and it
goes when the proposal goes or moves. The house itself is not here: it is a
`.glb` the engine builds from its own script and serves, placed by the
atlas's registry, and the world draws it over this pack, taking down what it
clears (the standing house, whose river-stone chimney is the model's origin)
and the recorded trees under its outline.

`trees.csv` still holds all 3,663 tops the lidar saw in 2018; the edit is
what takes fourteen of them down. The walkable world writes this file
through the atlas (`POST /api/pack/edits`, PIN-guarded, validated against
the grammar above): press **B** there, make the correction, save.

## The frame

`trees.csv` is in a local metric frame so it stays small: integer
decimetres east and north of `frame.origin` in `pack.json`, converted with

    lng = origin_lng + x / metres_per_deg_lng
    lat = origin_lat + y / metres_per_deg_lat

Every GeoJSON file is plain EPSG:4326.

## What is still missing

The survey sheet draws five sheds, wood fences, power poles and dirt roads
that exist here only as a registered raster in the atlas. Those come from
a walk along the fence line with a phone, one photograph at each corner and
gate. The new house is a massing so far — the Oak Leaf, three leaves round
the existing chimney, at real size on the real knoll, made by
`scripts/massing/oak-leaf.py` in the engine — and wants a settled design
before it is more than that.

## Sources

- Henry Land Surveying Inc., Jeremy Henry PLS 8135 — topographic survey,
  2024-11-14; record map 14-PM-15, Ventura County Recorder
- USGS 3DEP lidar, CA_SoCal_Wildfires_B3_2018, tile w2091n1519 (public domain)
- Ventura County GIS, maps.ventura.org — parcels, footprints, road
  centrelines, 2025 Urban Aerial
- The atlas, eco-village-map.vercel.app — survey transcription, Vision zones,
  baked terrain

No owner names, no residents, no purchased data. This repository is public.
