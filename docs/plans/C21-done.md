# C21 done — re-site water, prove the checks, publish the pack

**Date:** 2026-09-22  
**Branch:** `eco/c21`  
**Generators:** `scripts/water-harvest.py`, `scripts/pack-layers.py`  
**Checks:** `check-water`, `check-surfaces`, `check-pack-layers`, `check-rasters` (+ prior suite); each with `--self-test`

C20's oak split holds. C21 corrects the water brief, stops checks from trusting their own generators, and publishes drawable atlas layers.

---

## C21.1 — water on low ground

### What changed

Ponds are ranked by **flow accumulation × TWI**, not by `buildable`. Exclusions are only:
creek *channel* (model footprint), easement, oak crowns, footprints + Zone 0.
`buildable_score` is reported as information. Every pond carries `on_channel: true|false`.

Swales adopt their own `needed_section_m2` (stated as width × depth). Where needed
section exceeds the practical max 2.0 × 0.6 m = 1.2 m², the run is split into parallel
segments. Every swale in this pack **holds its event**.

### Honest capture (25 mm event)

| quantity | value |
|---|---|
| parcel runoff | 344.8 m³ |
| **held** | **117.2 m³ ≈ 31,000 US gallons** |
| **fraction held** | **34.0%** |
| season through system (400 mm proxy) | 1,172 m³ ≈ 310,000 gallons |

C20's 16.8% / 58 m³ was a siting artefact (ponds forced onto dry open ground). Moving
them onto wet low ground roughly doubles the useful hold. All three ponds are
`on_channel: true` — in California that typically needs a state wildlife agency answer
before they are real. Flagged for the owner; not concluded here.

### Swales (sized, not assumed 0.15 m²)

| id | section m² | width × depth m | holds_event |
|---|---:|---|---|
| swale-1b | 1.195 | 1.99 × 0.6 | true |
| swale-2 | 1.179 | 1.97 × 0.6 | true |
| swale-5 | 0.944 | 1.57 × 0.6 | true |

### Ponds

| id | catch m² | event m³ | buildable_score | on_channel |
|---|---:|---:|---:|---|
| pond-1 | 3,825 | 34.4 | 0.000 | true |
| pond-2 | 1,545 | 13.9 | 0.000 | true |
| pond-3 | 1,087 | 9.8 | 0.577 | true |

### Routed / unrouted (D8 walk from every parcel cell)

| | m² |
|---|---:|
| routed to a swale or pond footprint | 3,752 |
| unrouted | 34,529 |
| **sum** | **38,281** (= parcel cells) |

Of the unrouted ground: **~8,145 m²** drains into the defined creek channel; classified
boundary exits include north ~1,584 m² and west ~768 m². Those boundary fractions leave
the property and cannot be harvested without works outside the survey line. Channel-bound
flow is the creek itself — on-channel storage, not off-channel harvest.

Named assumptions (unchanged C): runoff C = 0.45, infil 5 mm, pond depth 1.2 m,
season 400 mm proxy — all in `water-harvest.json`.

---

## C21.2 — checks that prove things

### Summary-readers audited

| check | was reading | now |
|---|---|---|
| `check-surfaces` | `surfaces-summary.json` proof_oak_cell | recomputes cell (148,141) from `.npz` + `trees.csv` (2 crowns, trunk 3.24 m) |
| `check-water` | buildable gate on summary ponds | buildable is info only; verifies crowns/easement/channel/`on_channel` from geometry + grids |
| `check-rasters` | already npz↔png | unchanged probes; gained `--self-test` |
| `check-defensible` | geojson + trees.csv | already independent; gained `--self-test` |
| `check-gathers` | npz + hand EN | already independent |
| `check-pack-layers` | new | files, bounds, alpha, style_by, legend |

### Negative tests (`--self-test`)

Each of `check-water`, `check-surfaces`, `check-rasters`, `check-pack-layers`,
`check-defensible` has a deliberate wrong input that **must** fail. Running
`python scripts/<check>.py --self-test` prints `OK negative …` only when that failure
is observed.

### Row-order sentence

In `docs/layers.md`: `.npz` row 0 = south (`north ascending`); PNG row 0 = north
(`north_to_south`); worked example EN (260.82, 267.76) → `(i,j)=(148,141)` →
`png_row = nrows − 1 − 148`.

---

## C21.3 — pack a client can draw

`pack-layers.json` — **29 layers** drawable from the manifest alone:

| group | count |
|---|---:|
| terrain | 3 |
| water | 6 |
| habitat | 4 |
| sun | 3 |
| surfaces | 7 |
| defensible | 1 |
| proposed | 5 |

- Data PNGs unchanged (16-bit greyscale).
- Display PNGs at `analysis/display/<id>.png` — RGBA, ramp in sidecar, **transparent
  where excluded / nodata**.
- Vectors carry `style_by` in the manifest; legends have ≥2 stops or categories.
- `bounds_lnglat` round-trips to grid corners within 0.1 m (checked).

---

## What this pack says now

Buildable and gathering stay as C20 left them. Water finally sits where water goes, and
the capture figure (about a third of a 25 mm runoff, ~31k gallons) is about the land,
not about a wrong gate. The atlas can paint every published layer without bespoke decode
code. Real phone captures still wait on the owner.
