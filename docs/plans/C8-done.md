# C8 done — water

**Date:** 2026-09-20  
**Architect override:** board C8 (authoring-a-world blueprint) deferred — this phase is the creek and the Oak Leaf pool / fire terrace. Blueprint stays later.

---

## Water contract (chosen and applied everywhere)

**Water is not a floor.** Nobody walks on it.

| piece | role |
|---|---|
| water surface | **visual only** (`cap` mesh) — never in `extras.walk.floors` |
| bed | **walkable floor** — you wade / stand on the bottom |
| banks / rim | **solids** that shape the channel — they do not fill the water column |

The other defensible choice (edge solid stops you at the bank) was rejected so a person can enter the creek and the pool. Both buildings use the same rule.

**Bed below terrain — verified, not assumed.** Creek: per-station assert that bed ≤ local grade − 0.75 m. Oak Leaf pool: assert bed_y < min(deck-corner DEM deltas) − 0.2 m at build.

---

## Season (honest)

A Ventura County creek is **dry for much of the year**. The pack shows **late-winter / early-spring flow** — the wet season — so the water is readable. It is not a summer perennial. Stated in `extras.season` on the creek model.

---

## Creek

| metric | value |
|---|---|
| model | `creek.glb` |
| bytes / tris | **137,016** / **2,088** |
| floors / solids | 43 / 78 |
| length | **82.5 m** along DEM thalweg |
| bed cut | **0.75 m** below local grade |
| water depth | **0.28 m** |
| bed clearance (min) | **0.75 m** (verified per station) |
| crossing | ford + timber plank at origin (path to glamping already crosses here) |
| origin | ford (−119.156485, 34.432554) |
| validate | pass |

Thalweg from pack easting ~232→308 through the glamping draw. Banks are river-stone solids left/right of the bed.

---

## Oak Leaf pool and fire terrace

Geometry was already in the massing, but the pool sat near main-floor height while the north bank DEM is ~1.7 m lower — water as a sheet on the hillside. C8 re-sits both on terrain and applies the water contract.

| metric | value |
|---|---|
| pool deck_y (model) | **−1.607** (≈ local DEM) |
| water_y | **−1.958** (visual) |
| bed_y | **−3.407** (walkable) |
| bed below terrain | **1.22 m** (verified) |
| fire terrace_y | **−1.012** (north-bank DEM) |
| oak-leaf bytes / tris | **331,744** / **5,610** |
| validate | pass |

Hot tub uses the same contract. Stairs link the north terrace down to the deck and fire terrace; pool entry steps reach the bed.

---

## Built table

| model | bytes | tris | floors | solids | validate | note |
|---|---|---|---|---|---|---|
| `creek.glb` | **137,016** | **2,088** | 43 | 78 | pass | wet-season creek + ford |
| `oak-leaf-massing.glb` | **331,744** | **5,610** | 76 | 79 | pass | pool/fire on DEM; water contract |

No meshopt. Same pack surfaces. Registered in `pack.json`, `models.json`, `build-models.mjs`.

---

## C7 correction carried here (egress load ≠ design capacity)

Occupant-load factors compute **egress load** (exit safety ceiling). **Design capacity** is programme intent. C7 had reported the first as the second.

| building | egress load (area × factor) | design capacity (programme) | doors (from egress) |
|---|---|---|---|
| Community Hub | **102** (foyer 0.5 + rooms 1.4) | **48** — foyer ~20 standing + two rooms ×14 seated | 1.8+1.8 = min floor (calc 1.43 each) — **over-provision** |
| Events hall | **125** (176 / 1.4 seated) | **125** — same number; seated assembly is the programme | 1.8+1.8 from 125×28 mm = 3.5 m — **sized** |
| Wellness | **96** (corridor 0.5 + rooms 1.4) | **14** — four rooms ×2 + corridor ~6 | 1.8+1.8 = min floor (calc 1.34 each) — **over-provision** |

Events was the case where the two nearly coincide; the other two were a crush if read as design capacity. Manifest now carries both fields. Door geometry unchanged this phase (over-provision is safe); the record no longer pretends all three were equally “sized.”
