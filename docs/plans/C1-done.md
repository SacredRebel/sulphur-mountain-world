# C1 done — extend the toolkit + C1b materials

**Date:** 2026-09-20  
**Commits:** `eco(C1): …` (this phase)

## Delivered

### Toolkit (extend, do not rewrite)
- `docs/massing-template.md` — frame, walk contract, materials, register/build/validate
- `scripts/example-box.py` — worked 4×6 m shed (door = gap, pack surfaces only)
- `scripts/validate-model.py` — metre scale, Y-up, z-south rings, open rings, reachability, solid base≤top, no self-intersection
- `scripts/build-models.mjs` — `MODELS` lists oak-leaf + example-box; mkdir `models/`; validate after each build
- `scripts/glb.py` — added `surface()` / `load_surfaces()` reading `materials.json`
- `pack.json` — `layers.models.files` includes `example-box.glb`

### C1b materials
- `materials.json` — `schema: 1`, new `surfaces` with stone, river_stone, timber, board_and_batten, glass, stucco, concrete, living_roof, standing_seam_metal, canvas (+ bronze, water, pool_floor, dark_stone, timber_rib helpers)
- `scripts/oak-leaf.py` — all materials via `surface(...)`; no hardcoded RGB
- Shared ≤512 textures referenced from surfaces (`bark_512`, `straw_512`, `dirt_512`, `gravel_512`)

## Checks

| model | bytes | triangles | floors | solids | validate |
|---|---|---|---|---|---|
| `oak-leaf-massing.glb` | 2,154,680 | 51,348 | 67 | 87 | **pass** |
| `example-box.glb` | 10,432 | 114 | 1 | 5 | **pass** |

Validator first failed on Oak Leaf (teardrop tip = coincident first/last). Fixed the check — model was right.

## Notes
- Rebased C0 onto `5f4fa2c` (scripts/models landed) and pushed before C1.
- Notion board C7/C8/C9 now match the chat brief; followed board.
- `.venv-models` may be created by the build script; do not commit it.
