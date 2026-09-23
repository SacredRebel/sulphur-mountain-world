"""
C19.1 — check drawable grid rasters.

    python scripts/check-rasters.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GRID = ROOT / 'analysis' / 'grids'


def load_pack_grids():
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    out = {}
    for name, layer in pack['layers'].items():
        if layer.get('kind') == 'grid':
            out[name] = layer
    return out


def decode(pixel, meta):
    nodata = int(meta['nodata'])
    if int(pixel) == nodata:
        return None
    vmin, vmax = float(meta['value_min']), float(meta['value_max'])
    return vmin + (float(pixel) / 65534.0) * (vmax - vmin)


def main():
    layers = load_pack_grids()
    if not layers:
        raise SystemExit('no kind=grid layers in pack.json')
    errs = []
    for name, layer in layers.items():
        meta_path = ROOT / layer['meta']
        png_path = ROOT / layer['raster']
        npz_path = ROOT / layer['file']
        for key in ('kind', 'authority', 'evidence', 'units'):
            if key not in layer:
                errs.append(f'{name}: pack layer missing {key}')
        if not meta_path.exists():
            errs.append(f'{name}: missing meta {meta_path}')
            continue
        if not png_path.exists():
            errs.append(f'{name}: missing raster {png_path}')
            continue
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        for key in ('encoding', 'value_min', 'value_max', 'nodata', 'row_order', 'bounds_lnglat'):
            if key not in meta:
                errs.append(f'{name}: sidecar missing {key}')
        im = Image.open(png_path)
        w, h = im.size
        ncols, nrows = int(meta['ncols']), int(meta['nrows'])
        if w != ncols or h != nrows:
            errs.append(f'{name}: png {w}x{h} != ncols x nrows {ncols}x{nrows}')
        if meta.get('row_order') != 'north_to_south':
            errs.append(f'{name}: row_order must be north_to_south')

        data = np.asarray(np.load(npz_path)['data'], dtype=np.float64)
        # PNG is north_to_south; npz is south→north (north ascending)
        png = np.array(im)
        if png.ndim != 2:
            errs.append(f'{name}: png not greyscale')
            continue
        # three sample cells in npz index space
        samples = [
            (nrows // 4, ncols // 4),
            (nrows // 2, ncols // 2),
            (3 * nrows // 4, 3 * ncols // 4),
        ]
        span = float(meta['value_max']) - float(meta['value_min']) or 1.0
        print(f'--- {name} ---')
        for i, j in samples:
            # png row for north_to_south
            pr = nrows - 1 - i
            pix = int(png[pr, j])
            got = decode(pix, meta)
            want = float(data[i, j]) if np.isfinite(data[i, j]) else None
            if want is None:
                if got is not None and pix != int(meta['nodata']):
                    errs.append(f'{name}[{i},{j}]: expected nodata')
                print(f'  cell ({i},{j}): npz=nan png={pix} decoded={got}')
                continue
            if got is None:
                errs.append(f'{name}[{i},{j}]: unexpected nodata')
                continue
            err = abs(got - want) / span
            print(f'  cell ({i},{j}): npz={want:.6g} decoded={got:.6g} rel={err*100:.4f}%')
            if err > 0.001:
                errs.append(f'{name}[{i},{j}]: decode error {err*100:.3f}% > 0.1%')

        # bounds round-trip
        west, south, east, north = meta['bounds_lnglat']
        mx = float(meta['metres_per_deg_lng'])
        my = float(meta['metres_per_deg_lat'])
        ol = float(meta['frame_origin_lng'])
        oa = float(meta['frame_origin_lat'])
        e_w = (west - ol) * mx
        e_e = (east - ol) * mx
        n_s = (south - oa) * my
        n_n = (north - oa) * my
        be = meta['bounds_en_m']
        for label, a, b in (
            ('west', e_w, be[0]), ('south', n_s, be[1]),
            ('east', e_e, be[2]), ('north', n_n, be[3]),
        ):
            if abs(a - b) > 0.05:
                errs.append(f'{name}: bounds {label} off by {abs(a-b):.3f} m')

    # every pack layer needs kind/authority/evidence/units
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    skip = {'imagery', 'terrain', 'models', 'materials'}  # structural
    for name, layer in pack['layers'].items():
        if not isinstance(layer, dict):
            continue
        if name in skip or layer.get('kind') in ('xyz', 'terrarium'):
            continue
        for key in ('kind', 'authority', 'evidence', 'units'):
            if key not in layer:
                # evidence/units optional for older survey/county until we add them
                if key in ('kind', 'authority') or layer.get('kind') in ('grid', 'vector', 'table'):
                    if key not in layer:
                        errs.append(f'pack.layers.{name}: missing {key}')

    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print(f'OK check-rasters: {len(layers)} grid layers')


if __name__ == '__main__':
    main()
