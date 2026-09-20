# C4 done — Oak Leaf rebuilt parametric + sparse

**Date:** 2026-09-20  
**Budget:** under 500 KB and ~20,000 triangles **uncompressed**. Meshopt unused.  
**Design:** unchanged — same footprint, massing, roof line, siting, rotation. Only mesh density and open rings changed.

## Numbers

| model | bytes | triangles | floors | solids | validate | extensionsRequired |
|---|---|---|---|---|---|---|
| `oak-leaf-massing.glb` (before) | 2,154,680 | 51,348 | 67 | 87 | pass | [] |
| `oak-leaf-massing.glb` (after) | **280,972** | **4,830** | 49 | 59 | pass | [] |

Closed walk rings (`first==last`): **5 → 0**. Floors drop mostly from garden stones (26 → 8 pads); solids from fewer wall/seat segments — not from redesigning the house.

## Before / after triangles per element

| mesh (material) | before | after | Δ |
|---|---|---|---|
| timber (soffit + eaves) | 17,652 | 732 | −16,920 |
| timber rib | 14,512 | 900 | −13,612 |
| living roof | 13,216 | 376 | −12,840 |
| stone | 3,104 | 1,020 | −2,084 |
| bronze | 1,384 | 860 | −524 |
| river stone | 420 | 400 | −20 |
| dark stone | 368 | 240 | −128 |
| timber deck | 252 | 64 | −188 |
| pool floor | 192 | 84 | −108 |
| glass | 136 | 78 | −58 |
| water | 64 | 28 | −36 |
| concrete | 48 | 48 | 0 |
| **total** | **51,348** | **4,830** | **−46,518** |

Where the 51k went: dense leaf shells (`shell_nt=56`, `shell_nv=25`) and dense rib sweeps. Sparse sampling of the **same** Leaf math (`shell_nt=10`, `shell_nv=5`, fixed `rib_cross=3`) cuts roof + ribs by ~43k tris. No decimation; no design change; no meshopt.

## PARAMS (next change to this house = a change to these numbers)

Script: `scripts/oak-leaf.py`. Written into GLB `extras.params` on every build.

### `PARAMS['design']` — owner decisions (do not casually edit)

```
levels_m:        court -3.5, lower -3.3, main 0.0, loft 3.7, ridge 9.8
central:         tip (0,-15), base (0,11), width 13, widest 0.62
                 ridge [(0,5.8),(0.3,7.6),(0.62,9.8),(0.85,8.4),(1.0,5.6)]
kitchen_wing:    tip (16.5,10.5), base (4.0,2.0), width 9.0, widest 0.62
master_wing:     tip (-14.5,9.5), base (-4.0,2.0), width 9.0, widest 0.62
lounge_wing:     tip (15.5,-10.0), base (4.0,-2.0), width 8.6, widest 0.62
suites_wing:     tip (-15.0,-10.5), base (-4.0,-2.0), width 8.6, widest 0.62
lower:           LX0 -14, LX1 2, LN0 -12, LN1 -3
pool_deck:       DX0 -25, DX1 -7, DN0 13, DN1 24
pool_centre:     (-16.0, 18.5)  rx 5.2  ry 3.1
fire:            (3.5, 20.0, 0.0)
oak_lounge:      (13.0, -19.5, -1.3)
garden_x:        26.0
```

### `PARAMS['mesh']` — C4 density (edit these to regenerate denser/sparser)

| key | value | was (approx) |
|---|---|---|
| `shell_nt` | **10** | 56 |
| `shell_nv` | **5** | 25 |
| `outline_n` | **12** | denser |
| `wall_step_m` | **3.2** | 1.8 |
| `rib_cross` | **3** | ~L/2.4 sweeps |
| `rib_path_n` | **5** | ~30 |
| `pool_n` | **16** | 40 |
| `circle_n` | **12** | 24–36 |
| `garden_stones` | **8** | 26 |
| `garden_circle_n` | **8** | — |
| `fire_seats` | **6** | 8 |
| `loft_outline_n` | **8** | 16 |
| `suite_bays` | **6** | 12 |
| `balustrade_posts` | **4** | — |
| `shell_thick` | **0.32** | — |

Rebuild: `python scripts/oak-leaf.py models/oak-leaf-massing.glb`

## Walk rings

`open_ring()` drops a coincident closing tip on teardrop leaf floors and the loft. Five rings that previously shipped `first==last` now ship open. Consumer closes them.

## Not done (by design)

- No redesign of footprint / massing / roof / siting / rotation
- No meshopt
- Gathering places (board C4/C5) deferred — architect overrode C4 to Oak Leaf
