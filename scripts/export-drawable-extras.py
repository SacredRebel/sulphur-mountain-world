"""
C22.3 — drawable tree crowns/trunks, horizon ring, terrain hillshade display.

    python scripts/export-drawable-extras.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from matplotlib.colors import LightSource
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR, grid_meta  # noqa: E402
from terrain import en_to_lnglat, lnglat_to_en  # noqa: E402

HORIZON_DRAW_M = 8000.0
CIRCLE_PTS = 16


def load_trees():
    rows = []
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as fh:
        for i, row in enumerate(csv.DictReader(fh), start=1):
            rows.append({
                'id': i,
                'e': float(row['x_east_dm']) / 10.0,
                'n': float(row['y_north_dm']) / 10.0,
                'height_m': float(row['height_dm']) / 10.0,
                'crown_radius_m': float(row.get('crown_radius_dm') or 30) / 10.0,
            })
    return rows


def crown_ring(e: float, n: float, r_m: float) -> list[list[float]]:
    ring = []
    for k in range(CIRCLE_PTS + 1):
        az = 360.0 * (k % CIRCLE_PTS) / CIRCLE_PTS
        rad = math.radians(az)
        pe = e + r_m * math.sin(rad)
        pn = n + r_m * math.cos(rad)
        ring.append(list(en_to_lnglat(pe, pn)))
    return ring


def export_trees(trees: list[dict]):
    crown_feats = []
    trunk_feats = []
    for t in trees:
        props = {
            'id': t['id'],
            'height_m': round(t['height_m'], 2),
            'crown_radius_m': round(t['crown_radius_m'], 2),
        }
        crown_feats.append({
            'type': 'Feature',
            'properties': props,
            'geometry': {
                'type': 'Polygon',
                'coordinates': [crown_ring(t['e'], t['n'], t['crown_radius_m'])],
            },
        })
        trunk_feats.append({
            'type': 'Feature',
            'properties': {'id': t['id'], 'height_m': round(t['height_m'], 2)},
            'geometry': {
                'type': 'Point',
                'coordinates': list(en_to_lnglat(t['e'], t['n'])),
            },
        })
    common = {
        'authority': 'derived',
        'evidence': 'measured',
        'generator': 'scripts/export-drawable-extras.py',
        'source': 'trees.csv',
    }
    (ROOT / 'trees-crowns.geojson').write_text(
        json.dumps({
            'type': 'FeatureCollection',
            'name': 'trees-crowns',
            'properties': common,
            'features': crown_feats,
        }, indent=2) + '\n',
        encoding='utf-8',
    )
    (ROOT / 'trees-trunks.geojson').write_text(
        json.dumps({
            'type': 'FeatureCollection',
            'name': 'trees-trunks',
            'properties': common,
            'features': trunk_feats,
        }, indent=2) + '\n',
        encoding='utf-8',
    )
    return len(trees)


def export_horizon():
    hz = json.loads((ROOT / 'horizon.json').read_text(encoding='utf-8'))
    far_m = float(hz.get('far_m') or 30000.0)
    dist_m = HORIZON_DRAW_M if HORIZON_DRAW_M < far_m else min(far_m, 8000.0)
    feats = []
    for name, vp in (hz.get('viewpoints') or {}).items():
        lng, lat = float(vp['lng']), float(vp['lat'])
        e0, n0 = lnglat_to_en(lng, lat)
        azs = vp['azimuth_deg']
        alts = vp['altitude_deg']
        coords = []
        for az in azs:
            rad = math.radians(float(az))
            pe = e0 + dist_m * math.sin(rad)
            pn = n0 + dist_m * math.cos(rad)
            coords.append(list(en_to_lnglat(pe, pn)))
        if coords and coords[0] != coords[-1]:
            coords.append(coords[0])
        feats.append({
            'type': 'Feature',
            'properties': {
                'viewpoint': name,
                'draw_radius_m': dist_m,
                'azimuth_deg': azs,
                'altitude_deg': alts,
            },
            'geometry': {'type': 'LineString', 'coordinates': coords},
        })
    (ROOT / 'horizon.geojson').write_text(
        json.dumps({
            'type': 'FeatureCollection',
            'name': 'horizon',
            'properties': {
                'authority': 'derived',
                'evidence': 'modelled',
                'generator': 'scripts/export-drawable-extras.py',
                'source': 'horizon.json',
                'units': {'altitude_deg': 'degrees', 'azimuth_deg': 'degrees'},
                'note': (
                    'LineString vertices follow azimuth_deg at draw_radius_m on the ground plane; '
                    'parallel altitude_deg[i] is horizon altitude at azimuth_deg[i] (not encoded in XY).'
                ),
            },
            'features': feats,
        }, indent=2) + '\n',
        encoding='utf-8',
    )
    return len(feats)


def bounds_from_dem(es, ns, cell: float, meta_base: dict) -> tuple[list[float], list[float]]:
    e_w = float(es[0] - cell / 2)
    e_e = float(es[-1] + cell / 2)
    n_s = float(ns[0] - cell / 2)
    n_n = float(ns[-1] + cell / 2)
    fr = meta_base
    wlng = fr['frame_origin_lng'] + e_w / fr['metres_per_deg_lng']
    slat = fr['frame_origin_lat'] + n_s / fr['metres_per_deg_lat']
    elng = fr['frame_origin_lng'] + e_e / fr['metres_per_deg_lng']
    nlat = fr['frame_origin_lat'] + n_n / fr['metres_per_deg_lat']
    return (
        [round(wlng, 7), round(slat, 7), round(elng, 7), round(nlat, 7)],
        [e_w, n_s, e_e, n_n],
    )


def export_terrain_hillshade():
    zpath = GRID_DIR / 'dem_1m.npz'
    if not zpath.exists():
        raise SystemExit('missing analysis/grids/dem_1m.npz — run land-reading layers first')
    dem = np.load(zpath)
    es = np.asarray(dem['es'], dtype=np.float64)
    ns = np.asarray(dem['ns'], dtype=np.float64)
    Z = np.asarray(dem['Z'], dtype=np.float64)
    cell = float(dem['step']) if 'step' in dem.files else 1.0

    finite = np.isfinite(Z)
    fill = float(np.nanmean(Z[finite])) if finite.any() else 0.0
    ls = LightSource(azdeg=315, altdeg=45)
    hs = ls.hillshade(np.nan_to_num(Z, nan=fill), vert_exag=2, dx=cell, dy=cell)
    hs = np.clip(hs, 0.0, 1.0)
    hs_north = np.flipud(hs)

    rgba = np.zeros((*hs_north.shape, 4), dtype=np.uint8)
    g = (hs_north * 255.0).astype(np.uint8)
    rgba[..., 0] = g
    rgba[..., 1] = g
    rgba[..., 2] = g
    valid_north = np.flipud(finite)
    rgba[..., 3] = np.where(valid_north, 255, 0).astype(np.uint8)

    display_dir = ROOT / 'analysis' / 'display'
    display_dir.mkdir(parents=True, exist_ok=True)
    display_rel = 'analysis/display/terrain.png'
    Image.fromarray(rgba, mode='RGBA').save(ROOT / display_rel)

    meta = grid_meta(es, ns, step=cell)
    bounds_ll, bounds_en = bounds_from_dem(es, ns, cell, meta)
    ramp = {
        'name': 'greyscale',
        'stops': [
            {'value': 0.0, 'rgba': [0, 0, 0, 255], 'label': '0'},
            {'value': 0.5, 'rgba': [128, 128, 128, 255], 'label': '0.5'},
            {'value': 1.0, 'rgba': [255, 255, 255, 255], 'label': '1'},
        ],
    }
    sidecar = {
        **meta,
        'what': '1 m DEM hillshade for map underlay',
        'evidence': 'measured',
        'method': 'matplotlib LightSource hillshade on dem_1m.npz',
        'units': 'normalised shade 0–1',
        'encoding': 'display_rgba',
        'value_min': 0.0,
        'value_max': 1.0,
        'row_order': 'north_to_south',
        'bounds_lnglat': bounds_ll,
        'bounds_en_m': bounds_en,
        'display_raster': display_rel,
        'ramp': ramp,
        'source_dem': 'analysis/grids/dem_1m.npz',
    }
    (GRID_DIR / 'terrain.json').write_text(json.dumps(sidecar, indent=2) + '\n', encoding='utf-8')
    return hs_north, valid_north


def main():
    n_trees = export_trees(load_trees())
    n_hz = export_horizon()
    hs, valid = export_terrain_hillshade()
    v = hs[valid]
    span = (float(v.max()) - float(v.min())) if v.size else 0.0
    print(f'OK export-drawable-extras: trees={n_trees} horizon_viewpoints={n_hz} '
          f'hillshade_span={span:.3f}')


if __name__ == '__main__':
    main()
