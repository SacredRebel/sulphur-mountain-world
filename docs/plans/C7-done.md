# C7 done — three distinct gathering buildings

**Date:** 2026-09-20  
**Architect override:** board C7 (stations schema) deferred — redesign community / events / wellness so they are not one parametric box.

---

## Occupancy factors (stated)

| use | factor |
|---|---|
| standing / reception | **0.5 m² / person** |
| assembly, no tables | **0.65 m² / person** |
| seated at tables | **1.4 m² / person** |

Design occupancy = Σ floor(area ÷ factor) per use zone. Capacity is derived, not asserted.

Egress: **28 mm clear width per person of design occupancy, total across all exits**, minimum **1.8 m** per opening; second exit when design occupancy **> 49**.

---

## Arithmetic

### Community Hub — everyday, divisible

Plan: foyer + west lounge + east meeting. Crossed shed roofs.

| zone | area | factor | occupancy |
|---|---|---|---|
| foyer | 30.0 m² | standing 0.5 | floor(30.0 / 0.5) = **60** |
| west lounge | 30.0 m² | seated 1.4 | floor(30.0 / 1.4) = **21** |
| east meeting | 30.0 m² | seated 1.4 | floor(30.0 / 1.4) = **21** |
| **design** | **90.0 m²** | mixed | **60 + 21 + 21 = 102** |

Doors: 102 × 28 mm = 2.856 m total ÷ 2 exits → 1.43 m → **1.8 m** each (min). Second exit on east meeting wall.

### Events & Gatherings Hub — one clear volume

Plan: 16 × 11 m clear span, timber ribs overhead, standing-seam gable. Nothing in the middle.

| zone | area | factor | occupancy |
|---|---|---|---|
| hall | 176.0 m² | seated 1.4 | floor(176.0 / 1.4) = **125** |

Doors: 125 × 28 mm = 3.50 m total ÷ 2 exits → 1.75 m → **1.8 m** each (south + north). Total clear **3.6 m** — the width that previously appeared as one 3.6 m opening, now explicit and split.

### Wellness Facilities — small quiet rooms

Plan: corridor + three east rooms + one west room. Low shed roof.

| zone | area | factor | occupancy |
|---|---|---|---|
| corridor | 26.4 m² | standing 0.5 | floor(26.4 / 0.5) = **52** |
| room south | 14.0 m² | seated 1.4 | floor(14.0 / 1.4) = **10** |
| room mid | 14.0 m² | seated 1.4 | **10** |
| room north | 14.0 m² | seated 1.4 | **10** |
| room west | 20.0 m² | seated 1.4 | floor(20.0 / 1.4) = **14** |
| **design** | **88.4 m²** | mixed | **52 + 10 + 10 + 10 + 14 = 96** |

Doors: 96 × 28 mm = 2.688 m total ÷ 2 exits → 1.34 m → **1.8 m** each (south entry + north garden).

---

## Built table

| model | bytes | tris | floors | solids | clear floor | factor (primary) | design occupancy | doors | validate |
|---|---|---|---|---|---|---|---|---|---|
| `community-hub.glb` | **28,516** | **362** | 5 | 16 | **90.0 m²** | standing 0.5 + seated 1.4 | **102** | 1.8 + 1.8 | pass |
| `events-gatherings-hub.glb` | **27,032** | **352** | 3 | 6 | **176.0 m²** | seated 1.4 | **125** | 1.8 + 1.8 | pass |
| `wellness-facilities.glb` | **36,084** | **474** | 7 | 21 | **88.4 m²** | seated 1.4 + standing 0.5 | **96** | 1.8 + 1.8 | pass |

Solid names are no longer shared across buildings (different plans). No meshopt; same pack surfaces and `extras.walk` method.

Scripts: `gathering.py` (factors + egress helpers only — not a hall builder), `community-hub.py`, `events-hub.py`, `wellness.py`. Manifest updated.
