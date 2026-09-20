# C6 done — human stairs (C6.0) + gathering places

**Date:** 2026-09-20  
**Architect override:** board C6 (manifest-only) expanded — C6.0 re-cut every step to human proportion, then three gathering halls; manifest also gains `name` and oak-leaf.

---

## C6.0 — stairs and ramps

Stairs were previously tuned to the engine's 0.55 m snap. That is not a stair. Re-cut to building numbers; `check-paths.py` now asserts **0.18 m** as the binding riser limit, with **0.55 m** as a backstop that should never fire on walk surfaces.

### Choice: ramp vs stair

| path | mode | why |
|---|---|---|
| path to barn, dome, glamping, ag, court link | **ramp ≤ 8%** | Short/gentle; no steps needed |
| path to retreat (~13.8 m climb) | **switchback ramp ≤ 8%** | 81 human risers would be absurd; a hillside ramp is what belongs here |
| path to oak (court → house) | **stair, 170 mm** | Short climb; the most-walked route — real stairs |

### Stair numbers (oak flight)

| metric | value |
|---|---|
| Total risers | **19** |
| Riser range | **0.170 – 0.170 m** |
| Tread | **0.29 m** |
| Blondel (2R+T) | **0.63 m** |
| Longest run without landing | **14** (landing every 14, landing 1.2 m) |

### Site-grounds after re-cut

| model | bytes | triangles | floors | solids | validate | check-paths |
|---|---|---|---|---|---|---|
| `site-grounds.glb` | **412,028** | **5,952** | 321 | 51 | pass | pass |

| metric | value |
|---|---|
| Path length | **773.8 m** |
| Steepest ramp | **0.077** (≤ 0.08) |
| Steepest drive | **0.191** (≤ 0.20) |
| Largest building riser (walk) | **0.17 m** |
| Engine backstop | unused on walk (0.55 still asserted) |

---

## Gathering places

Rooms for thirty people — not cabins scaled up. Crowd doors are wide gaps. Floor rings meet walls (no shortfall).

| model | bytes | tris | floors | solids | capacity | clear floor | door | validate |
|---|---|---|---|---|---|---|---|---|
| `community-hub.glb` | **14,336** | **156** | 3 | 5 | **30 standing** | **96 m²** (12×8) | **3.0 m** | pass |
| `events-gatherings-hub.glb` | **14,332** | **156** | 3 | 5 | **30 standing** | **140 m²** (14×10) | **3.6 m** | pass |
| `wellness-facilities.glb` | **14,312** | **156** | 3 | 5 | **30 standing** | **70 m²** (10×7) | **2.8 m** | pass |

| hall | m² / standing person | seated (from area) |
|---|---|---|
| Community Hub | 3.2 | ~27 |
| Events & Gatherings | 4.7 | ~40 |
| Wellness | 2.3 | ~20 |

Shared builder: `scripts/gathering.py`. Origins at vision points.

---

## Manifest

- Every model now has a display **`name`**
- **`oak-leaf-massing`** added (was the only pack model missing from the manifest)
- Three gathering halls registered

Scripts: `check-paths.py` (building riser + engine backstop), `site-grounds.py`, `gathering.py`, `community-hub.py`, `events-hub.py`, `wellness.py`.
