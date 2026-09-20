# C2 done — Retreat Village + Creek-Side Glamping

**Date:** 2026-09-20  
**Constraint:** generate under **20,000 triangles** per model (~2,000 per dwelling × 8). No lossy decimation.

## Delivered

| script | model | bytes | triangles | floors | solids | validate |
|---|---|---|---|---|---|---|
| `scripts/dwelling.py` | (library) | — | — | — | — | — |
| `scripts/retreat-village.py` | `models/retreat-village.glb` | **85,432** | **1,220** | 33 | 40 | pass |
| `scripts/glamping-creek.py` | `models/glamping-creek.glb` | **26,732** | **211** | 11 | 35 | pass |

~152 tris/cabin, ~42 tris/tipí — budgeted at generation time.

- Seeded parametric unit (`cabin` / `tipi`) — same seed → same unit
- Retreat: 8 cabins, seed 42, arc to SW view, path + approaches, not a grid
- Glamping: 5 tipís, seed 7, creek line, `altitudeM: -1.4` vs ridge
- Materials only via `surface(...)`
- Registered in `build-models.mjs` + `pack.json` `layers.models.files`
- `models.json` updated (C6 cadence)

## Authority

All siting and footprints are **proposed** (vision points + C0 survey sketches), not surveyed.
