# C23 done — outline audit and licence provenance

**Date:** 2026-09-23  
**Branch:** `eco/c23`  
**Generators:** `scripts/fix-site-grounds-outline.py`, `scripts/build-positions.py`, `scripts/build-licence-manifest.py`  
**Checks:** `check-outlines`, `check-licences` (+ positions/materials); each new check has `--self-test`

---

## C23.1 — site-grounds was a padded AABB, not a site outline

`site-grounds` carried a **4-corner axis-aligned box**: the walk-floor AABB plus a 3 m
pad (~**35,332 m²**). That matched `check-positions`' old "vegetation envelope" special
case exactly — so the table and the GLB agreed, and nobody noticed the outline was
wrong for placement.

It was not a double buffer, not a units slip, and not a stale WGS84 ring. It was a
**convex AABB standing in for a concave path network**, and about **10,124 m²** of that
box sat outside the survey.

### Fix

Replaced the footprint with **walk-floors ∪ buffered 3 m** (same construction
`check-positions` now compares against). Every model also got a recorded `area_m2`
stamped from its own geometry.

| | m² |
|---|---:|
| old AABB+3 m envelope | 35,332.4 |
| new floors∪+3 m outline | **6,972.8** |
| **delta removed** | **−28,359.6** |
| still outside survey (flagged `crosses_survey`) | 708.7 |

The brief's "about 3,504 m² too big" is smaller than the full AABB excess. Measured pad
growth alone (unpadded floor AABB → +3 m) is **2,273 m²**; outside-survey excess of the
old box was **10,124 m²**. Neither single figure is 3,504 — the honest correction is the
whole AABB → floors∪+3 m change above. Remaining delta against that definition: **0**
(registry area matches recomputed geometry within 1%).

`creek` also crosses the survey (~65 m²) and is flagged. All other outlines lie inside.

### Outline table (all 17 models)

| id | claimed m² | recomputed m² | delta | verdict |
|---|---:|---:|---:|---|
| oak-leaf-massing | 1137.0 | 1136.9 | 0.0 | OK |
| retreat-village | 1029.5 | 1029.4 | 0.0 | OK |
| glamping-creek | 581.2 | 581.2 | 0.0 | OK |
| the-barn | 228.4 | 228.4 | 0.0 | OK |
| agricultural-hub | 199.9 | 199.9 | 0.0 | OK |
| tropical-dome | 130.0 | 130.0 | 0.0 | OK |
| site-grounds | 6972.8 | 6972.8 | 0.0 | OK (crosses_survey) |
| creek | 2241.0 | 2241.0 | 0.0 | OK (crosses_survey) |
| community-hub | 141.9 | 141.9 | 0.0 | OK |
| events-gatherings-hub | 241.4 | 241.4 | 0.0 | OK |
| wellness-facilities | 158.3 | 158.3 | 0.0 | OK |
| livestock-dairy | 227.3 | 227.3 | 0.0 | OK |
| mushroom-cultivation | 62.8 | 62.8 | 0.0 | OK |
| beekeeping-program | 20.7 | 20.7 | 0.0 | OK |
| farmstead-produce-stand | 32.2 | 32.2 | 0.0 | OK |
| infrastructure | 571.5 | 571.5 | 0.0 | OK |
| ceremonial-infrastructure | 169.0 | 169.0 | 0.0 | OK |

---

## C23.2 — provenance on every asset

- `licence` + `source` on every `models.json` model (and LOD row): `own-work`.
- `materials.json` top-level and each material: `CC0-1.0` with ambientCG source URL.
- `licence-manifest.json`: **146** tracked binaries with licence, source, sha256.
- `docs/licensing.md`: one-paragraph rule — nothing enters unless redistribution from a
  public repository and use in a publicly served application are allowed.

### Count by licence

| licence | assets |
|---|---:|
| own-work | 115 |
| CC0-1.0 | 31 |

`check-licences` asserts every git-tracked binary is in the manifest, every licence is
on the allowed list (no redistribution-forbidden entries), and every sha256 matches
disk. `--self-test` forges `Commercial-NoRedistrib` and proves rejection.
