# C10 done — Oak Leaf footprint fix + productive cluster

**Date:** 2026-09-20  
**Architect override:** productive cluster (livestock, mushroom, beekeeping, produce stand) plus the Oak Leaf footprint re-pass. Board C10 row may follow.

---

## Oak Leaf footprint — exception list (a decision)

Regenerated **from solids**, not floors. The footprint encloses every built solid **except** these three, which stand deliberately in uncleared ground so the recorded oaks survive:

| exception | why outside |
|---|---|
| `oak lounge fire` | outdoor lounge among oaks |
| `oak lounge seat` | outdoor lounge among oaks |
| `standing stone` | sacred garden stones among oaks |

Fire terrace, pool rim, wing walls, suite fronts, and every other solid are **inside**.

| metric | value |
|---|---|
| points | **56** |
| area | **1,132 m²** (registry reference was 1,064 m²) |
| included solids outside | **0** |
| excluded solids min distance | **5.8 m** outside |

Generator: `scripts/oak-footprint.py`.

---

## Four working buildings — work first, then plan

| building | WORK (one sentence) | what the plan does | enterable interior? |
|---|---|---|---|
| **Livestock & Dairy** | Milk animals and hose the floor clean afterward. | 3.0 m cow door, open south bay, sealed wash-down concrete with drain channel, enclosed milk room east | yes |
| **Mushroom Cultivation** | Grow mushrooms in controlled dark climate. | Small opaque sealed box, person door only, no windows, low eaves, internal racks | yes |
| **Beekeeping & Honey** | Store hive tools and extract honey next to the yards. | 4×3.5 m tool shed + work bench; hive yard outside footprint | yes |
| **Farmstead Produce Stand** | Sell produce at the road edge; customers stay outside. | Counter under canopy, open to the road, screens behind — **no enclosed room** | **no** |

The produce stand is the one with **no enterable interior**: you stand on the serving apron outdoors and buy across the counter. There is nowhere indoors to stand.

---

## Built table

| model | bytes | tris | floors | solids | validate |
|---|---|---|---|---|---|
| `livestock-dairy.glb` | **22,064** | **276** | 3 | 13 | pass |
| `mushroom-cultivation.glb` | **14,884** | **178** | 2 | 8 | pass |
| `beekeeping-program.glb` | **12,900** | **146** | 2 | 6 | pass |
| `farmstead-produce-stand.glb` | **15,364** | **178** | 2 | 9 | pass |

No meshopt. Display names in `models.json`. Scripts: `livestock-dairy.py`, `mushroom.py`, `beekeeping.py`, `produce-stand.py`.
