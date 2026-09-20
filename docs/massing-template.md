# Massing script template

Every generator in `scripts/` follows the Oak Leaf pattern: **the Python script is the model**.
Copy `scripts/example-box.py`, rename it, register it in `scripts/build-models.mjs`, add the
output to `pack.json` → `layers.models.files`, rebuild, validate, commit the GLB with the script.

## Frame

| plan | model |
|---|---|
| east | +x |
| up | +y |
| north | **−z** (z points south) |

```python
def P(e, n, y=0.0):
    return (float(e), float(y), float(-n))

def ring_xz(pts):
    return [(float(e), float(-n)) for e, n in pts]
```

Z-negation happens here — not in GeoJSON. Get this wrong and the building faces the wrong way.

## Walk contract

```ts
floors[]: { name, ring: [x, z][], top }        // standable
solids[]: { name, ring: [x, z][], base, top }  // impassable
```

- Metres, model-local.
- Rings are **open** (do not repeat the first point).
- A door is a **gap** in the solid run, not a property.
- Origin is a **named landmark** someone can point at (door threshold, chimney), never the centroid.
- One mesh per material.

Record floors/solids with `m.floor(...)` and `m.solid(...)` from `glb.py`.

## Materials

```python
from glb import surface
TIMBER = surface('timber')
GLASS = surface('glass')      # opacity < 1 → alphaMode BLEND
```

Keys live in `materials.json` → `surfaces`. **No RGB literals in a script.** Reuse `albedo_512`
paths from the pack (≤512 px) across models; do not duplicate texture files per building.

Required surface ids (C1b): `stone`, `river_stone`, `timber`, `board_and_batten`, `glass`,
`stucco`, `concrete`, `living_roof`, `standing_seam_metal`, `canvas` — plus helpers already in
the file (`bronze`, `water`, …).

## Build & validate

```bash
node scripts/build-models.mjs
python scripts/validate-model.py models/<name>.glb
```

`models/` is **committed**. When you change a script, rebuild and commit the GLB with it. The pack
is served as static files (e.g. raw.githubusercontent); there is no deploy-time build for communities.

Budget for new models: **under 500 KB** and **~20,000 triangles** after write, uncompressed.
Oak Leaf is now inside that budget (`scripts/oak-leaf.py` PARAMS['mesh'] — see `docs/plans/C4-done.md`).

## Register a new generator

In `scripts/build-models.mjs`:

```js
const MODELS = [
  { script: 'scripts/oak-leaf.py', out: 'models/oak-leaf-massing.glb' },
  { script: 'scripts/example-box.py', out: 'models/example-box.glb' },
  { script: 'scripts/your-zone.py', out: 'models/your-zone.glb' },
];
```

And list the file under `pack.json` → `layers.models.files`.

## Worked example

`scripts/example-box.py` builds a 4×6 m board-and-batten shed:

- origin = door threshold centre on the south wall
- south wall split around a 1 m door gap
- stone pad floor, metal shed roof, one glass bay
- materials only via `surface(...)`

Read that file before writing a zone massing. Read `scripts/oak-leaf.py` for a large composition
(leaves, stairs, outdoor rooms) — take the pattern, do not copy its size.
