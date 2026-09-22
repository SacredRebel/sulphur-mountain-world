"""
Shared 1 m pack-frame DEM window for C13/C16 land-reading layers.

  Same origin, cell size and CRS as the pack terrain (equirectangular metres
  at pack.json frame.origin). Grids are written as .npz with metadata JSON.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys_path_note = str(ROOT / 'scripts')

import sys
if sys_path_note not in sys.path:
    sys.path.insert(0, sys_path_note)

from terrain import elevation_en, en_to_lnglat, lnglat_to_en  # noqa: E402

STEP_M = 1.0
GRID_DIR = ROOT / 'analysis' / 'grids'


def pack():
    return json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))


def parcel_window(pad_m: float = 30.0):
    from shapely.geometry import shape
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    poly = shape(survey['features'][0]['geometry'])
    minx, miny, maxx, maxy = poly.bounds
    e0, n0 = lnglat_to_en(minx, miny)
    e1, n1 = lnglat_to_en(maxx, maxy)
    return poly, e0 - pad_m, n0 - pad_m, e1 + pad_m, n1 + pad_m


def sample_dem(e0, n0, e1, n1, step=STEP_M, cache_name='dem_1m.npz'):
    GRID_DIR.mkdir(parents=True, exist_ok=True)
    cache = GRID_DIR / cache_name
    if cache.exists():
        z = np.load(cache)
        if (
            abs(float(z['e0']) - e0) < 1e-6 and abs(float(z['n0']) - n0) < 1e-6
            and abs(float(z['step']) - step) < 1e-9
            and abs(float(z['e1']) - e1) < 1e-6 and abs(float(z['n1']) - n1) < 1e-6
        ):
            return z['es'], z['ns'], z['Z']

    cols = int(round((e1 - e0) / step)) + 1
    rows = int(round((n1 - n0) / step)) + 1
    es = e0 + np.arange(cols) * step
    ns = n0 + np.arange(rows) * step
    Z = np.empty((rows, cols), dtype=np.float64)
    for i, n in enumerate(ns):
        for j, e in enumerate(es):
            try:
                Z[i, j] = elevation_en(float(e), float(n))
            except FileNotFoundError:
                Z[i, j] = np.nan
    np.savez_compressed(cache, es=es, ns=ns, Z=Z, e0=e0, n0=n0, e1=e1, n1=n1, step=step)
    return es, ns, Z


def grid_meta(es, ns, step=STEP_M):
    fr = pack()['frame']
    return {
        'origin_east_m': float(es[0]),
        'origin_north_m': float(ns[0]),
        'cell_m': float(step),
        'ncols': int(es.size),
        'nrows': int(ns.size),
        'crs': 'pack-frame metres (equirectangular at origin_lat)',
        'frame_origin_lng': fr['origin_lng'],
        'frame_origin_lat': fr['origin_lat'],
        'metres_per_deg_lng': fr['metres_per_deg_lng'],
        'metres_per_deg_lat': fr['metres_per_deg_lat'],
        'axes': 'row = north ascending, col = east ascending; value at cell centre',
    }


def write_grid(name: str, array: np.ndarray, es, ns, extra: dict | None = None):
    GRID_DIR.mkdir(parents=True, exist_ok=True)
    path = GRID_DIR / f'{name}.npz'
    meta = grid_meta(es, ns)
    if extra:
        meta.update(extra)
    np.savez_compressed(path, data=array.astype(np.float32), es=es, ns=ns, meta=json.dumps(meta))
    (GRID_DIR / f'{name}.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    return path


def viewpoints():
    """Three named viewpoints for horizon / sky events."""
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    oak = next(m for m in man['models'] if m['id'] == 'oak-leaf-massing')
    cer = next(m for m in man['models'] if m['id'] == 'ceremonial-infrastructure')
    from shapely.geometry import shape
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    centroid = shape(survey['features'][0]['geometry']).centroid
    return {
        'parcel_centroid': {'lng': centroid.x, 'lat': centroid.y},
        'oak_leaf': {'lng': oak['origin'][0], 'lat': oak['origin'][1]},
        'ceremonial': {'lng': cer['origin'][0], 'lat': cer['origin'][1]},
    }
