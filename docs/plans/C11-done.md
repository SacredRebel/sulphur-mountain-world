# C11 done — Infrastructure massing

**Date:** 2026-09-20  
**Architect override:** infrastructure + ceremonial-infrastructure programme massing.  
**Review fix:** disposal setbacks, solar row pitch, kiva wall height (same day).

**This is massing, not engineering.**

---

## Zone programme → what was built

| zone | summary says | built |
|---|---|---|
| **Infrastructure & Utilities** | water system upgrades; electric reactivation with solar; utilities foundation | water tank, well head, solar array, greywater beds, leach field, equipment shed |
| **Ceremonial Infrastructure** | natural stone and earthen kiva with sacred fire circle in front of McQueen's | 13 m Ø kiva floor, low ring wall, centre fire |

C0 sketch matches: utility yard with tank pads / solar rack / shed ~8×6 m; ceremonial stone circle ~12–14 m Ø.

---

## Walk contract (not buildings)

| element | walk |
|---|---|
| solar panel rows | **solids** — a roof you cannot walk on; **no floor** under the rack |
| water tank | **solid** cylinder — you cannot enter |
| well head | solid |
| yard / disposal path | walkable floors between plant |
| equipment shed | the one enterable room (tools), open south bay |
| kiva floor | outdoor walkable floor — **no enterable interior** |
| sacred fire | solid |
| kiva ring wall | **0.45 m** (steppable — not the engine's 0.55 m knife edge) |

**Owner decision (2026-09-21): open-air.** The kiva is complete as built — no enclosure. Further kiva work closed.

---

## Placeholder sizes (say so)

| item | stated size | note |
|---|---|---|
| water tank | **10,000 gal** → Ø **3.7 m** × **3.5 m** | programme cistern massing — **placeholder** |
| solar array | yard **12 × 5.9 m**; three **0.80 m** rows at **2.40 m** pitch; panel plan ≈ **67 m²** → roughly **11–13 kW** DC | pitch clears winter-solstice self-shade at 34.433° — **placeholder, not a string design** |
| leach field | **96 m²** (12×8 m) | programme pad with berm sketch — **placeholder, not a septic design** |
| greywater beds | 2 × (3×2 m) | massing only |
| equipment shed | 8×6 m | from C0 |
| kiva | 13 m diameter | mid of C0 12–14 m |

---

## Setbacks (a decision)

California requires **100 ft (30.5 m)** from a well (and we hold the same off the creek) to sewage disposal. The disposal group (greywater + leach) sits **east** of the utility core — the creek runs west.

| clearance | min distance |
|---|---|
| disposal → well head | **≥ 31.1 m** |
| disposal → creek bed | **≥ 36.4 m** |

---

## Built table

| model | bytes | tris | floors | solids | validate |
|---|---|---|---|---|---|
| `infrastructure.glb` | **46,064** | **616** | 5 | 22 | pass |
| `ceremonial-infrastructure.glb` | **42,176** | **620** | 1 | 27 | pass |

No meshopt. Scripts: `infrastructure.py`, `ceremonial.py`.
