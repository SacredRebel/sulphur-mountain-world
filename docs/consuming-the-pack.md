# Consuming the pack

This pack is a dependency for software that is not this repository. Load
`pack.json` for the frame and layer index, `pack-layers.json` for drawables,
and `contract.json` for the field promises. Below: five worked examples using
**real published numbers**.

## 1. Load the manifest

```js
const pack = await fetch('pack.json').then(r => r.json());
const layers = await fetch('pack-layers.json').then(r => r.json());
// every drawable entry has id, kind, path, bounds_lnglat, legend, authority, evidence
const twi = layers.layers.find(L => L.id === 'twi');
```

## 2. Place a raster from `bounds_lnglat`

`bounds_lnglat` is `[west, south, east, north]` in EPSG:4326. Stretch the PNG
into that geographic rectangle (equirectangular is fine at this scale).

Example — `twi` sidecar / manifest:

| | |
|---|---|
| bounds | `[-119.1581823, 34.4315124, -119.1545051, 34.4338381]` |
| PNG | `analysis/grids/twi.png` (or display `analysis/display/twi.png`) |
| size | 338 × 258 |

PNG **row 0 is north**. Pack-frame metres from `pack.json` `frame` if you need EN.

## 3. Decode a value

Uint16 greyscale; `65535` is nodata:

```
value = value_min + (pixel / 65534) * (value_max - value_min)
```

Worked example from `analysis/grids/twi.json` / `twi.png`:

| | |
|---|---|
| png_row, png_col | 124, 164 |
| pixel | 8497 |
| value_min / value_max | −0.3184537… / 17.7207107… |
| decoded | **2.020466…** |
| npz row `i = nrows − 1 − png_row` = 133 | **2.020550…** (Δ < 0.001) |

## 4. Read the instance table

`trees-instances.json`: each row names an `archetype_id` whose mesh path is under
`archetypes[]`.

Worked example — first instance:

| | |
|---|---|
| tree_id | 0 |
| archetype_id | `oak-arch-10` |
| mesh | `models/trees/oak-arch-10.glb` |
| lng, lat | −119.160611, 34.4346846 |
| scale | 0.6541 |

Place the GLB at that lng/lat (pack spawn / frame as your engine requires), apply
`rotation_deg` and uniform `scale`.

## 5. Load the collision mesh

| | |
|---|---|
| mesh | `models/collision.glb` |
| meta | `collision.json` |
| triangles | **8404** |
| max DEM deviation | **0.75 m** (bound 2.5 m) |
| frame | pack spawn origin; **x east, y up, z south** |

## Frame round-trip

From `pack.json` `frame` / `contract.json`:

```
east_m = 260.82, north_m = 267.76
lng = origin_lng + east_m / metres_per_deg_lng = -119.15664291526875
lat = origin_lat + north_m / metres_per_deg_lat =  34.43285107044863
```

Invert with the same constants to recover east/north within float noise.
