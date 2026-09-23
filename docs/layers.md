# Layers — consumer contract

Every `pack.json` layer carries `kind`, `authority`, `evidence`, and `units`.
Grid rasters are plain `ncols × nrows` 16-bit greyscale PNGs (`row_order: north_to_south`,
`nodata: 65535`). Decode with the sidecar formula:
`value = value_min + (pixel / 65534) * (value_max - value_min)`.

| layer | what | units | evidence | how to read |
|---|---|---|---|---|
| `twi` | topographic wetness index | dimensionless | modelled | grid raster + `.npz` |
| `stormwater_depth` | 1-in-10 1-hr storm sheet-depth proxy | m | modelled | grid raster + `.npz` |
| `sun_hours_annual` | clear-sky direct sun (12 × 21st) | hours/year | modelled | grid raster + `.npz` |
| `sun_hours_dec` | clear-sky direct sun on 21 Dec | hours/day | modelled | grid raster + `.npz` |
| `sun_hours_jun` | clear-sky direct sun on 21 Jun | hours/day | modelled | grid raster + `.npz` |
| `cold_air` | cold-air drain / frost-pool index | dimensionless | modelled | grid raster + `.npz` |
| `wind_santa_ana` | exposure to Santa Ana wind from NE | 0–1 | modelled | grid raster + `.npz` |
| `wind_sea_breeze` | exposure to afternoon sea breeze from W | 0–1 | modelled | grid raster + `.npz` |
| `corridors` | animal-corridor current | dimensionless | modelled | grid raster + `.npz` |
| `landforms` | TPI landform class | class 1–6 | modelled | grid raster + `.npz` |
| `flow_accum` | D8 flow accumulation | m² | modelled | grid raster + `.npz` |
| `gathers` | where the land gathers (weighted overlay) | score 0–1 | modelled | grid raster + `.npz` + `gathers.geojson` |
| `capture_plan` | phone-scan walk order (~20 m zones) | geometry | modelled | GeoJSON + plan PNG |
| `scans` | Gaussian-splat placement rows | lng/lat, turn, scale, lift | measured | `scans.json` only — binaries stay private |
| `keylines` | keyline / swale candidates | geometry | modelled | GeoJSON |
| `drainage` | D8 flow channels | m² accum / slope / Strahler | modelled | GeoJSON |
| `thermal-belt` | mid-slope thermal belt | geometry | modelled | GeoJSON (`thermal_belt`) |
| `oak-leaf-knoll` | Oak Leaf knoll site analysis | geometry | modelled | GeoJSON (`oak_leaf_knoll`) |
| `sky_events` | sun/moon vs horizon; cross-quarters traditional | azimuth / local time | measured / traditional | JSON — stays its own layer |

Sidecar JSON for every grid also records `bounds_lnglat` `[west, south, east, north]`,
`encoding`, `value_min`, `value_max`, `nodata`, and `decode`.
