"""
C21.3 — validate pack-layers.json, display PNGs, and sidecar alignment.

    python scripts/check-pack-layers.py
    python scripts/check-pack-layers.py --self-test
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'pack-layers.json'
SCORE_LAYERS = frozenset({'buildable', 'gathering', 'gathers'})
DISPLAY_ONLY_IMAGES = frozenset({'terrain', 'terrain_hillshade'})


def decode_pixel(pixel: int, meta: dict) -> float | None:
    if int(pixel) == int(meta['nodata']):
        return None
    vmin, vmax = float(meta['value_min']), float(meta['value_max'])
    return vmin + (float(pixel) / 65534.0) * (vmax - vmin)


def load_grid_meta(layer: dict) -> dict:
    return json.loads((ROOT / layer['meta']).read_text(encoding='utf-8'))


def bounds_roundtrip(layer_id: str, bounds_lnglat, meta: dict, tol_m: float = 0.1) -> list[str]:
    errs = []
    west, south, east, north = bounds_lnglat
    mx = float(meta['metres_per_deg_lng'])
    my = float(meta['metres_per_deg_lat'])
    ol = float(meta['frame_origin_lng'])
    oa = float(meta['frame_origin_lat'])
    e_w = (west - ol) * mx
    e_e = (east - ol) * mx
    n_s = (south - oa) * my
    n_n = (north - oa) * my
    be = meta['bounds_en_m']
    deltas = []
    for label, a, b in (
        ('west', e_w, be[0]), ('south', n_s, be[1]),
        ('east', e_e, be[2]), ('north', n_n, be[3]),
    ):
        d = abs(a - b)
        deltas.append(f'{label}={d:.4f}m')
        if d > tol_m:
            errs.append(f'{layer_id}: bounds {label} off by {d:.3f} m > {tol_m}')
    print(f'  bounds {layer_id}: ' + ', '.join(deltas))
    return errs


def sample_display_alpha(layer_id: str, entry: dict, meta: dict, rng: random.Random) -> list[str]:
    errs = []
    data_path = ROOT / entry['data_raster']
    disp_path = ROOT / entry['path']
    data_png = np.array(Image.open(data_path))
    disp = np.array(Image.open(disp_path))
    if disp.ndim != 3 or disp.shape[2] != 4:
        errs.append(f'{layer_id}: display not RGBA')
        return errs
    nrows, ncols = int(meta['nrows']), int(meta['ncols'])
    if data_png.shape != (nrows, ncols):
        errs.append(f'{layer_id}: data png shape mismatch')
        return errs

    nodata = int(meta['nodata'])
    candidates = []
    for _ in range(500):
        r = rng.randrange(nrows)
        c = rng.randrange(ncols)
        pix = int(data_png[r, c])
        val = decode_pixel(pix, meta)
        is_nodata = pix == nodata or val is None
        is_zero_score = (
            layer_id in SCORE_LAYERS and val is not None and abs(val) < 1e-12
        )
        has_value = val is not None and not is_zero_score
        candidates.append((r, c, is_nodata or is_zero_score, has_value))
    rng.shuffle(candidates)
    picked = []
    need_mask = need_val = 0
    for item in candidates:
        if item[2] and need_mask < 5:
            picked.append(item)
            need_mask += 1
        elif item[3] and need_val < 5:
            picked.append(item)
            need_val += 1
        if len(picked) >= 10:
            break
    for item in candidates:
        if len(picked) >= 10:
            break
        if item not in picked:
            picked.append(item)

    for r, c, expect_transparent, expect_opaque in picked:
        alpha = int(disp[r, c, 3])
        if expect_transparent and alpha != 0:
            errs.append(f'{layer_id}[{r},{c}]: expected alpha=0, got {alpha}')
        if expect_opaque and alpha <= 0:
            errs.append(f'{layer_id}[{r},{c}]: expected alpha>0, got {alpha}')
    print(f'  alpha samples {layer_id}: {len(picked)} cells checked')
    return errs


def check_tree_crown_count(manifest: dict) -> list[str]:
    errs = []
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as fh:
        csv_rows = sum(1 for _ in fh) - 1
    crown_path = ROOT / 'trees-crowns.geojson'
    if not crown_path.exists():
        errs.append('missing trees-crowns.geojson')
        return errs
    gj = json.loads(crown_path.read_text(encoding='utf-8'))
    crown_n = len(gj.get('features') or [])
    print(f'  tree crowns: csv={csv_rows} geojson={crown_n}')
    if crown_n != csv_rows:
        errs.append(f'trees_crowns: feature count {crown_n} != trees.csv rows {csv_rows}')
    return errs


def check_hillshade_range() -> list[str]:
    errs = []
    path = ROOT / 'analysis/display/terrain.png'
    if not path.exists():
        errs.append('missing analysis/display/terrain.png')
        return errs
    disp = np.array(Image.open(path))
    if disp.ndim != 3 or disp.shape[2] != 4:
        errs.append('terrain hillshade: display not RGBA')
        return errs
    mask = disp[..., 3] > 0
    if not mask.any():
        errs.append('terrain hillshade: no opaque pixels')
        return errs
    rgb = disp[..., :3][mask].astype(np.float64) / 255.0
    span = float(rgb.max() - rgb.min())
    print(f'  hillshade RGB span: {span:.3f}')
    if span <= 0.5:
        errs.append(f'terrain hillshade: range {span:.3f} <= 0.5')
    return errs


def pack_layer_covered(pack_key: str, manifest: dict) -> bool:
    mids = {L['id'] for L in manifest.get('layers') or []}
    if pack_key in mids:
        return True
    aliases = manifest.get('pack_aliases') or {}
    alias = aliases.get(pack_key)
    if alias is None:
        return False
    if isinstance(alias, str):
        return alias in mids
    return all(a in mids for a in alias)


def check_pack_coverage(manifest: dict) -> list[str]:
    """Every pack.json layer is in the manifest or an explicit not_drawable reason."""
    errs = []
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    not_drawable = manifest.get('not_drawable') or {}
    if not isinstance(not_drawable, dict) or not not_drawable:
        errs.append('manifest missing not_drawable map with reasons')
        return errs
    for key, reason in not_drawable.items():
        if not str(reason).strip():
            errs.append(f'not_drawable.{key}: empty reason')
        if key not in pack.get('layers', {}):
            errs.append(f'not_drawable.{key}: not a pack.json layer')
    missing = []
    for pack_key in pack.get('layers', {}):
        if pack_key in not_drawable:
            continue
        if pack_layer_covered(pack_key, manifest):
            continue
        missing.append(pack_key)
    if missing:
        errs.append(
            'pack layers neither in manifest nor not_drawable: ' + ', '.join(sorted(missing))
        )
    print(
        f'  pack coverage: {len(pack["layers"])} pack keys; '
        f'{len(manifest.get("layers") or [])} drawable; '
        f'{len(not_drawable)} not_drawable'
    )
    return errs


def validate_manifest(manifest: dict) -> list[str]:
    errs = []
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    grid_by_id = {
        k: v for k, v in pack['layers'].items() if v.get('kind') == 'grid'
    }

    for entry in manifest.get('layers') or []:
        lid = entry['id']
        kind = entry['kind']
        path = ROOT / entry['path']
        if not path.exists():
            errs.append(f'{lid}: missing path {entry["path"]}')
            continue
        if kind == 'image':
            try:
                Image.open(path).verify()
            except Exception as exc:
                errs.append(f'{lid}: PNG open failed: {exc}')
            if lid in DISPLAY_ONLY_IMAGES:
                meta_path = ROOT / 'analysis/grids/terrain.json'
                if not meta_path.exists():
                    errs.append(f'{lid}: missing analysis/grids/terrain.json')
                    continue
                meta = json.loads(meta_path.read_text(encoding='utf-8'))
                errs.extend(bounds_roundtrip(lid, entry['bounds_lnglat'], meta))
                legend = entry.get('legend') or {}
                stops = legend.get('stops') or []
                if len(stops) < 2:
                    errs.append(f'{lid}: ramp needs >=2 stops')
                continue
            grid_layer = grid_by_id.get(lid)
            if not grid_layer:
                errs.append(f'{lid}: no pack grid layer')
                continue
            meta = load_grid_meta(grid_layer)
            errs.extend(bounds_roundtrip(lid, entry['bounds_lnglat'], meta))
            errs.extend(sample_display_alpha(lid, entry, meta, random.Random(42)))
            legend = entry.get('legend') or {}
            stops = legend.get('stops') or []
            if len(stops) < 2:
                errs.append(f'{lid}: ramp needs >=2 stops')
        elif kind == 'geojson':
            try:
                gj = json.loads(path.read_text(encoding='utf-8'))
            except Exception as exc:
                errs.append(f'{lid}: geojson open failed: {exc}')
                continue
            style_by = entry.get('style_by')
            if not style_by:
                errs.append(f'{lid}: missing style_by')
                continue
            for i, feat in enumerate(gj.get('features') or []):
                p = feat.get('properties') or {}
                if style_by not in p:
                    errs.append(f'{lid}: feature {i} missing {style_by}')
            cats = (entry.get('legend') or {}).get('categories') or []
            stops = (entry.get('legend') or {}).get('stops') or []
            if len(cats) < 2 and len(stops) < 2:
                errs.append(f'{lid}: legend needs >=2 categories or stops')
        else:
            errs.append(f'{lid}: unknown kind {kind}')

    return errs


def self_test():
    if not MANIFEST.exists():
        print('FAIL negative: run pack-layers.py first')
        raise SystemExit(1)
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    bad_path = copy.deepcopy(manifest)
    bad_path['layers'][0]['path'] = 'analysis/display/__missing__.png'
    if not validate_manifest(bad_path):
        print('FAIL negative: bad path should fail')
        raise SystemExit(1)

    bad_bounds = copy.deepcopy(manifest)
    for entry in bad_bounds['layers']:
        if entry['kind'] == 'image':
            entry['bounds_lnglat'] = [0, 0, 0, 0]
            break
    else:
        print('FAIL negative: no image layer')
        raise SystemExit(1)
    if not validate_manifest(bad_bounds):
        print('FAIL negative: bad bounds should fail')
        raise SystemExit(1)

    bad_cov = copy.deepcopy(manifest)
    bad_cov['not_drawable'] = dict(manifest.get('not_drawable') or {})
    # drop a known not_drawable entry so coverage fails if survey is still required
    # forge: remove trees_crowns from layers and clear aliases so trees is uncovered
    bad_cov['layers'] = [L for L in bad_cov['layers'] if L['id'] != 'trees_crowns']
    aliases = dict(bad_cov.get('pack_aliases') or {})
    aliases.pop('trees', None)
    bad_cov['pack_aliases'] = aliases
    nd = dict(bad_cov.get('not_drawable') or {})
    nd.pop('trees', None)
    bad_cov['not_drawable'] = nd
    if not check_pack_coverage(bad_cov):
        print('FAIL negative: missing pack coverage should fail')
        raise SystemExit(1)

    print('OK negative check-pack-layers')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return

    if not MANIFEST.exists():
        raise SystemExit('missing pack-layers.json — run scripts/pack-layers.py')
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    errs = validate_manifest(manifest)
    errs.extend(check_pack_coverage(manifest))
    errs.extend(check_tree_crown_count(manifest))
    errs.extend(check_hillshade_range())
    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    n_img = sum(1 for L in manifest['layers'] if L['kind'] == 'image')
    n_geo = sum(1 for L in manifest['layers'] if L['kind'] == 'geojson')
    by_group: dict[str, int] = {}
    for L in manifest['layers']:
        by_group[L['group']] = by_group.get(L['group'], 0) + 1
    groups = ', '.join(f'{g}={by_group[g]}' for g in sorted(by_group))
    print(f'OK check-pack-layers: {n_img} image, {n_geo} geojson ({groups})')


if __name__ == '__main__':
    main()
