# C11 done — Infrastructure massing

**Date:** 2026-09-20  
**Architect override:** infrastructure + ceremonial-infrastructure programme massing.

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
| yard gravel | walkable floor between plant |
| equipment shed | the one enterable room (tools), open south bay |
| kiva floor | outdoor walkable floor — **no enterable interior** |
| sacred fire | solid |

---

## Placeholder sizes (say so)

| item | stated size | note |
|---|---|---|
| water tank | **10,000 gal** → Ø **3.7 m** × **3.5 m** | programme cistern massing — **placeholder** |
| solar array | **48 m²** (12×4 m) → roughly **8–10 kW** DC | rule-of-thumb 5–6 m²/kW — **placeholder, not a string design** |
| leach field | **96 m²** (8×12 m) | programme pad with berm sketch — **placeholder, not a septic design** |
| greywater beds | 2 × (3×2 m) | massing only |
| equipment shed | 8×6 m | from C0 |
| kiva | 13 m diameter | mid of C0 12–14 m |

Where a serious reader would need engineering, the number is labelled placeholder.

---

## Built table

| model | bytes | tris | floors | solids | validate |
|---|---|---|---|---|---|
| `infrastructure.glb` | **42,568** | **568** | 2 | 22 | pass |
| `ceremonial-infrastructure.glb` | **42,172** | **620** | 1 | 27 | pass |

No meshopt. Scripts: `infrastructure.py`, `ceremonial.py`.
