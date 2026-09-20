# C5 done — the ground between the buildings

**Date:** 2026-09-20  
**Budget:** under 500 KB / ~20k tris uncompressed. Meshopt unused.  
**Architect override:** board C5 (remaining zones) deferred — this phase is drive, parking, paths, steps/retaining.

## Numbers

| model | bytes | triangles | floors | solids | validate | check-paths |
|---|---|---|---|---|---|---|
| `site-grounds.glb` | **331,596** | **4,784** | 254 | 45 | pass | pass |

## Path contract report

| metric | value |
|---|---|
| Total path length (drive + walk centreline) | **675.7 m** |
| Steepest walking segment (rise/run) | **0.386** (≪ 1.2) |
| Steepest drive segment (rise/run) | **0.191** (under 0.20 abs) |
| Largest floor-to-floor step | **0.549 m** (≤ 0.55) |
| Segments that failed the check **before** fix | **28** |

The 28 were straight-line samples between anchors (and the raw easement→court drive) that exceeded either walk step-at-sample-spacing or drive absolute grade. Fixed with easement-aligned arcs, profile clamping, stairs, and a flat court apron — not by relaxing the numbers.

## Drive specification (vehicle, not walker)

| limit | value | why |
|---|---|---|
| Preferred max grade | **15%** (0.15) | Drivable without drama |
| Absolute max grade (short pitch) | **20%** (0.20) | Hard stop — steeper is undrivable |
| Minimum outside turning radius | **7.5 m** | Passenger car; arcs built at **8.0 m** |
| Width | **3.6 m** | Single lane inside the surveyed 16 ft easement |

A 30° / slope-1.2 drive would validate as walkable and still be wrong. `check-paths.py` asserts drive grade and radius separately from the walker limits.

## What was built

- **Drive** — road entry along the survey 16 ft access easement → gate parking → spur to the Oak Leaf court (flatten elev 422.4 m from `edits.geojson`)
- **Parking** — gate apron south of the barn door; oak court pad matching the court edit
- **Paths** — gravel links from pack spawn to barn, dome, glamping, retreat, ag hub, oak (north edge of court), plus spawn→court
- **Steps / retaining** — stairs where Δz > 0.55 m; river-stone retaining solids where the ribbon sits > 0.55 m above natural grade

Origin: **pack spawn** (−119.156345, 34.432675). Frame: pack EN relative to spawn; y = DEM − spawn elev (terrarium z17).

## Scripts

| script | role |
|---|---|
| `scripts/terrain.py` | Terrarium DEM sampler |
| `scripts/site-grounds.py` | Generator (PARAMS + seed 5) |
| `scripts/check-paths.py` | Walk slope ≤ 1.2, step ≤ 0.55 m, drive grade/radius |

Registered in `build-models.mjs` (runs `check-paths` after validate), `pack.json`, `models.json`.

## Floor-area note (C4 carry-over)

The −2.8% ring-area drop was **not** double-counting: 18 of the lost rings were garden-stone pads dropped by mesh density (26→8), and the rest is chordal shrinkage from coarser curved outlines — worst inset ≈ **0.18 m** on the 5.2 m fire/lounge circles (n=12). Nobody stands on air.
