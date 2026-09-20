# C3 done — Barn, Agricultural Hub, Tropical Dome

**Date:** 2026-09-20  
**Budget:** under 20,000 tris/model; dome shell must stay under ~2,000 without compression.

## Numbers

| model | bytes | triangles | floors | solids | validate |
|---|---|---|---|---|---|
| `the-barn.glb` | **14,208** | **164** | 5 | 5 | pass |
| `agricultural-hub.glb` | **20,920** | **260** | 3 | 12 | pass |
| `tropical-dome.glb` | **26,888** | **364** | 2 | 11 | pass |

## Tropical Dome — segment choice

| parameter | value | why |
|---|---|---|
| Azimuth segments (`AZ`) | **12** | Readable as a dome at massing distance; 16+ would waste tris |
| Elevation bands (`BANDS`) | **3** | Eave → mid → near-apex; apex is triangles, not a UV sphere |
| Radius | 5.5 m | ~11 m clearspan |
| Door | omitted bay 0 (south) | Gap in the solid/glass run — not a flag |
| Whole-model triangles | **364** | Includes pad, knee wall, glass, ribs, threshold |
| Dome shell alone | well under 2,000 | No stop needed; no meshopt |

Not a tessellated sphere. Script: `scripts/tropical-dome.py`.

## Scripts

- `scripts/the-barn.py` → zone `gatelodge-operations-hub`
- `scripts/agricultural-hub.py` → zone `agricultural-hub`
- `scripts/tropical-dome.py` → zone `tropical-dome-greenhouse`

Registered in `build-models.mjs` and `pack.json`. `models.json` updated. Authority: **proposed**.
