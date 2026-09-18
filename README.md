# Sulphur Mountain — the world data pack

11962 Sulphur Mountain Rd, Ojai · APN 037-0-012-125 · 9.465 surveyed acres

This repository is one property's ground truth for the walkable world
([spatial-map](https://github.com/SacredRebel/spatial-map)): the surveyed
boundary, what stands on the land, what grows on it, and what is proposed
for it. The engine loads `pack.json` by URL and renders the rest. There is
one engine and one pack per property; nothing here is code.

## What is in it

| file | authority | date | what |
|---|---|---|---|
| `pack.json` | — | 2026-09-18 | the manifest: frame, layers, sources, and the reconciliation list |
| `survey.geojson` | **survey** | 2024-11-14 | the boundary from the eleven surveyed corners, every call with bearing and distance, the 16 ft access easement, the four found monuments |
| `county.geojson` | county | read 2026-09-18 | the assessor's parcel ring (kept to show the drift), the three county building footprints with their measured 2018 roof heights, the road centrelines |
| `roofs.geojson` | derived | 2018 | roof planes recovered from the lidar under the tree canopy: the house, a shed, and a 157 m² building the county does not map |
| `trees.csv` | derived | 2018 | 3,663 tree tops with height, crown radius and ground elevation; 367 inside the line, 96 per hectare |
| `vision.geojson` | proposal | — | the 18 proposed project zones, 14 with drawn territories — placeholders until each has a model |
| `edits.geojson` | **owner** | 2026-09-18 | what the owner has said differs from the record, applied by the world on top of the layers: the trees within 12 m of the house are gone |

Imagery (the county's 2025 aerial, ~12 cm/px) and terrain (USGS 3DEP 1 m,
baked by the atlas) are streamed from their publishers by URL and are not
copied here.

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
attributed feature and the world applies it on top: an `op` of `remove`
on a `layer`, over a Point with `radius_m` or a Polygon with `buffer_m`.
`trees.csv` still holds all 3,663 tops the lidar saw in 2018; the edit is
what takes fourteen of them down.

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
gate. The new house arrives as a model in the engine, sited from
`survey.geojson`, never from the county ring.

## Sources

- Henry Land Surveying Inc., Jeremy Henry PLS 8135 — topographic survey,
  2024-11-14; record map 14-PM-15, Ventura County Recorder
- USGS 3DEP lidar, CA_SoCal_Wildfires_B3_2018, tile w2091n1519 (public domain)
- Ventura County GIS, maps.ventura.org — parcels, footprints, road
  centrelines, 2025 Urban Aerial
- The atlas, eco-village-map.vercel.app — survey transcription, Vision zones,
  baked terrain

No owner names, no residents, no purchased data. This repository is public.
