"""
C19.1 — export each land-reading .npz as a plain georeferenced 16-bit PNG.

  Pixel array is exactly ncols x nrows (width x height). No axes or margins.
  Row 0 of the PNG is the northmost row (row_order: north_to_south).
  Encoding: 16-bit greyscale; nodata pixel = 65535.
    value = value_min + (pixel / 65534) * (value_max - value_min)   # for pixel < 65535

    python scripts/export-grid-rasters.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GRID = ROOT / 'analysis' / 'grids'
NODATA = 65535

# name -> (units, short what)
GRIDS = {
    'twi': ('dimensionless', 'topographic wetness index'),
    'stormwater_depth': ('m', '1-in-10 1-hr storm sheet depth proxy'),
    'sun_hours_annual': ('hours/year', 'clear-sky direct sun hours (12 x 21st)'),
    'sun_hours_dec': ('hours/day', 'clear-sky direct sun hours on 21 Dec'),
    'sun_hours_jun': ('hours/day', 'clear-sky direct sun hours on 21 Jun'),
    'cold_air': ('dimensionless', 'cold-air drain / frost-pool index'),
    'wind_santa_ana': ('0-1', 'exposure to Santa Ana wind from NE'),
    'wind_sea_breeze': ('0-1', 'exposure to afternoon sea breeze from W'),
    'corridors': ('dimensionless', 'animal-corridor current'),
    'landforms': ('class 1-6', 'TPI landform class'),
    'flow_accum': ('m2', 'D8 flow accumulation'),
}


def en_to_lnglat(e, n, meta):
    return (
        meta['frame_origin_lng'] + e / meta['metres_per_deg_lng'],
        meta['frame_origin_lat'] + n / meta['metres_per_deg_lat'],
    )


def export_one(name: str, units: str, what: str):
    npz = np.load(GRID / f'{name}.npz')
    data = np.asarray(npz['data'], dtype=np.float64)
    es = np.asarray(npz['es'])
    ns = np.asarray(npz['ns'])
    meta_path = GRID / f'{name}.json'
    meta = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.exists() else {}
    # keep frame fields from npz meta if present
    if 'meta' in npz.files:
        try:
            embedded = json.loads(str(npz['meta']))
            meta = {**embedded, **meta}
        except Exception:
            pass

    nrows, ncols = data.shape
    cell = float(meta.get('cell_m') or (es[1] - es[0]))
    # edges of the grid (cell centres at es/ns)
    e_w = float(es[0] - cell / 2)
    e_e = float(es[-1] + cell / 2)
    n_s = float(ns[0] - cell / 2)
    n_n = float(ns[-1] + cell / 2)
    # fill frame origin from pack if missing
    if 'frame_origin_lng' not in meta:
        pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
        fr = pack['frame']
        meta['frame_origin_lng'] = fr['origin_lng']
        meta['frame_origin_lat'] = fr['origin_lat']
        meta['metres_per_deg_lng'] = fr['metres_per_deg_lng']
        meta['metres_per_deg_lat'] = fr['metres_per_deg_lat']

    wlng, slat = en_to_lnglat(e_w, n_s, meta)
    elng, nlat = en_to_lnglat(e_e, n_n, meta)

    finite = np.isfinite(data)
    if not finite.any():
        raise SystemExit(f'{name}: no finite values')
    vmin = float(np.nanmin(data))
    vmax = float(np.nanmax(data))
    if vmax <= vmin:
        vmax = vmin + 1e-9

    # Encode to 0..65534; flip so PNG row 0 = north
    scaled = np.full(data.shape, NODATA, dtype=np.uint16)
    scaled[finite] = np.clip(
        np.round((data[finite] - vmin) / (vmax - vmin) * 65534.0),
        0, 65534,
    ).astype(np.uint16)
    png_arr = np.flipud(scaled)  # north_to_south

    out_png = GRID / f'{name}.png'
    Image.fromarray(png_arr, mode='I;16').save(out_png)

    meta.update({
        'origin_east_m': float(es[0]),
        'origin_north_m': float(ns[0]),
        'cell_m': cell,
        'ncols': int(ncols),
        'nrows': int(nrows),
        'units': units,
        'what': what,
        'evidence': meta.get('evidence', 'modelled'),
        'encoding': 'uint16_greyscale',
        'value_min': vmin,
        'value_max': vmax,
        'nodata': NODATA,
        'decode': (
            f'if pixel == {NODATA}: nodata; else '
            f'value = value_min + (pixel / 65534) * (value_max - value_min)'
        ),
        'row_order': 'north_to_south',
        'col_order': 'west_to_east',
        'axes_npz': 'row = north ascending (south at index 0), col = east ascending',
        'bounds_lnglat': [
            round(wlng, 7), round(slat, 7), round(elng, 7), round(nlat, 7),
        ],
        'bounds_en_m': [e_w, n_s, e_e, n_n],
        'raster': f'analysis/grids/{name}.png',
    })
    meta_path.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    print(f'{name}: {ncols}x{nrows} vmin={vmin:.4g} vmax={vmax:.4g} -> {out_png.name}')


def main():
    for name, (units, what) in GRIDS.items():
        if not (GRID / f'{name}.npz').exists():
            raise SystemExit(f'missing {name}.npz')
        export_one(name, units, what)
    print('OK export-grid-rasters')


if __name__ == '__main__':
    main()
