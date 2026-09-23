"""
C22 — check water-harvest (independent of generator summary claims).

    python scripts/check-water.py
    python scripts/check-water.py --self-test
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from shapely import contains_xy
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR  # noqa: E402
from land_layers import D8, d8_accum  # noqa: E402
from terrain import lnglat_to_en  # noqa: E402

HARVEST_BUFFER_M = 2.0
CATCHMENT_METHOD = 'exclusive_first_hit_d8'


def dem_on_flow_grid(es, ns):
    pack = np.load(GRID_DIR / 'dem_1m.npz')
    des, dns, zd = np.asarray(pack['es']), np.asarray(pack['ns']), np.asarray(pack['Z'], dtype=np.float64)
    jj = np.clip(np.round(es - des[0]).astype(int), 0, zd.shape[1] - 1)
    ii = np.clip(np.round(ns - dns[0]).astype(int), 0, zd.shape[0] - 1)
    jj_grid, ii_grid = np.meshgrid(jj, ii)
    z = zd[ii_grid, jj_grid].copy()
    ee, nn = np.meshgrid(es, ns)
    valid = (ee >= des[0]) & (ee <= des[-1]) & (nn >= dns[0]) & (nn <= dns[-1])
    z[~valid] = np.nan
    return z


def load_crowns():
    trees = []
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            trees.append(Point(
                float(row['x_east_dm']) / 10.0,
                float(row['y_north_dm']) / 10.0,
            ).buffer(float(row.get('crown_radius_dm') or 30) / 10.0))
    return unary_union(trees)


def easement_en(survey):
    parts = []
    for f in survey['features']:
        name = str((f.get('properties') or {}).get('name') or '').lower()
        if 'easement' not in name:
            continue
        g = shape(f['geometry'])
        if g.geom_type == 'Polygon':
            parts.append(Polygon([lnglat_to_en(x, y) for x, y in g.exterior.coords]).buffer(2.5))
    return unary_union(parts) if parts else None


def creek_channel():
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    creek = next(m for m in man['models'] if m['id'] == 'creek')
    return Polygon([lnglat_to_en(a, b) for a, b in creek['footprint']])


def drainage_en():
    d = json.loads((ROOT / 'drainage.geojson').read_text(encoding='utf-8'))
    lines = []
    for f in d['features']:
        g = shape(f['geometry'])
        if g.geom_type == 'LineString':
            lines.append(LineString([lnglat_to_en(x, y) for x, y in g.coords]))
    return unary_union(lines) if lines else None


def feature_en(f):
    g = shape(f['geometry'])
    if g.geom_type == 'LineString':
        return LineString([lnglat_to_en(x, y) for x, y in g.coords])
    if g.geom_type == 'Polygon':
        return Polygon([lnglat_to_en(x, y) for x, y in g.exterior.coords])
    return g


def harvest_works_from_geo(geo):
    works = []
    geoms = []
    for f in geo['features']:
        p = f.get('properties') or {}
        kind = p.get('kind')
        if kind not in ('swale', 'pond'):
            continue
        g = feature_en(f)
        if kind == 'swale':
            geoms.append(g.buffer(HARVEST_BUFFER_M))
        else:
            geoms.append(g)
        works.append(p['id'])
    return works, geoms


def build_owner(geoms, es, ns, rows, cols):
    owner = np.full((rows, cols), -1, dtype=np.int32)
    EE, NN = np.meshgrid(es, ns)
    for wi, geom in enumerate(geoms):
        mask = contains_xy(geom, EE, NN)
        claim = mask & (owner < 0)
        owner[claim] = wi
    return owner


def classify_exit(i, j, es, ns, cols, b_en):
    e_out = float(es[min(max(j, 0), cols - 1)])
    n_out = float(ns[min(max(i, 0), len(ns) - 1)])
    c = b_en.centroid
    de, dn = e_out - c.x, n_out - c.y
    if abs(de) > abs(dn):
        return 'east' if de > 0 else 'west'
    return 'north' if dn > 0 else 'south'


def recompute_routed_m2(in_p, fdir, owner, es, ns, b_en):
    rows, cols = in_p.shape
    memo = {}
    routed = 0

    def walk(i0, j0):
        if (i0, j0) in memo:
            return memo[(i0, j0)]
        path = []
        i, j = i0, j0
        seen = set()
        edge = None
        while True:
            if (i, j) in memo:
                result = memo[(i, j)]
                for pi, pj in path:
                    memo[(pi, pj)] = result
                memo[(i0, j0)] = result
                return result
            if (i, j) in seen:
                result = ('leave', edge)
                for pi, pj in path:
                    memo[(pi, pj)] = result
                memo[(i0, j0)] = result
                return result
            seen.add((i, j))
            path.append((i, j))
            if int(owner[i, j]) >= 0:
                result = ('routed', None)
                for pi, pj in path:
                    memo[(pi, pj)] = result
                return result
            k = int(fdir[i, j]) if 0 <= i < rows and 0 <= j < cols else -1
            if k < 0:
                result = ('leave', edge)
                for pi, pj in path:
                    memo[(pi, pj)] = result
                memo[(i0, j0)] = result
                return result
            ni, nj = i + D8[k][0], j + D8[k][1]
            if not (0 <= ni < rows and 0 <= nj < cols) or not in_p[ni, nj]:
                edge = classify_exit(i, j, es, ns, cols, b_en)
                result = ('leave', edge)
                for pi, pj in path:
                    memo[(pi, pj)] = result
                memo[(i0, j0)] = result
                return result
            i, j = ni, nj

    for i in range(rows):
        for j in range(cols):
            if not in_p[i, j]:
                continue
            res, _ = walk(i, j)
            if res == 'routed':
                routed += 1
    return routed


def run_checks(summary, geo) -> list[str]:
    errs = []
    a = summary['assumptions']
    storm = summary['storm_mm']
    c = a['runoff_coefficient']
    infil = a['infiltration_mm_during_event']
    parcel = summary['parcel_m2']

    want = parcel * (max(0.0, storm - infil) / 1000.0) * c
    got = summary['parcel_runoff_m3_25mm']
    if abs(want - got) / max(want, 1) > 0.01:
        errs.append(f'parcel runoff {got} != recomputed {want:.1f}')
    print(f'parcel runoff: {got} m3 (recomputed {want:.1f})')

    routed = summary['routed_m2']
    catch_sum = summary['catchment_sum_m2']
    rel = abs(routed - catch_sum) / max(routed, 1)
    print(f'routed_m2={routed} catchment_sum_m2={catch_sum} rel_diff={rel:.4f}')
    if rel >= 0.02:
        errs.append(f'routed_m2 {routed} vs catchment_sum_m2 {catch_sum} differ by {100 * rel:.1f}%')

    union_m2 = summary.get('catchment_union_m2', catch_sum)
    rel_u = abs(union_m2 - catch_sum) / max(catch_sum, 1)
    print(f'catchment_union_m2={union_m2} vs catchment_sum_m2={catch_sum} rel_diff={rel_u:.4f}')
    if rel_u >= 0.02:
        errs.append(f'catchment_union_m2 {union_m2} vs catchment_sum_m2 {catch_sum}')

    catch_feats = [f for f in geo['features'] if (f.get('properties') or {}).get('kind') == 'catchment']
    if not catch_feats:
        errs.append('no catchment features in geojson')
    for f in catch_feats:
        p = f['properties']
        for key in ('work_id', 'area_m2', 'method'):
            if key not in p:
                errs.append(f"catchment feature missing {key}")
        if p.get('method') != CATCHMENT_METHOD:
            errs.append(f"catchment method {p.get('method')} != {CATCHMENT_METHOD}")

    for vname in ('all_works', 'off_channel'):
        if vname not in summary.get('variants', {}):
            errs.append(f'variants.{vname} missing')
        else:
            v = summary['variants'][vname]
            for key in ('held_m3', 'held_gallons', 'fraction', 'routed_m2', 'catchment_sum_m2', 'note'):
                if key not in v:
                    errs.append(f'variants.{vname} missing {key}')

    es = np.asarray(np.load(GRID_DIR / 'buildable.npz')['es'])
    ns = np.asarray(np.load(GRID_DIR / 'buildable.npz')['ns'])
    dem = dem_on_flow_grid(es, ns)
    fdir, _, _ = d8_accum(dem)
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    b_en = Polygon([lnglat_to_en(x, y) for x, y in shape(survey['features'][0]['geometry']).exterior.coords])
    EE, NN = np.meshgrid(es, ns)
    in_p = contains_xy(b_en, EE, NN)
    work_ids, geoms = harvest_works_from_geo(geo)
    if work_ids:
        owner = build_owner(geoms, es, ns, in_p.shape[0], in_p.shape[1])
        routed_re = recompute_routed_m2(in_p, fdir, owner, es, ns, b_en)
        rel_r = abs(routed_re - routed) / max(routed, 1)
        print(f'independent routed recompute={routed_re} published={routed} rel_diff={rel_r:.4f}')
        if rel_r >= 0.02:
            errs.append(f'independent routed {routed_re} vs published {routed}')

    unrouted = summary['unrouted_m2']
    cells = summary['parcel_cells_m2']
    print(f'routed {routed} + unrouted {unrouted} = {routed + unrouted}; parcel cells {cells}')
    if routed + unrouted != cells:
        errs.append(f'routed+unrouted {routed + unrouted} != parcel cells {cells}')

    crowns = load_crowns()
    ease = easement_en(survey)
    channel = creek_channel()
    drains = drainage_en()
    by_id = {f['properties']['id']: f for f in geo['features'] if 'id' in f.get('properties', {})}

    build = np.asarray(np.load(GRID_DIR / 'buildable.npz')['data'])
    flow = np.asarray(np.load(GRID_DIR / 'flow_accum.npz')['data'])

    for s in summary['swales']:
        vol = s['catchment_m2'] * (max(0.0, storm - infil) / 1000.0) * c
        if abs(vol - s['event_volume_m3']) / max(vol, 0.01) > 0.05:
            errs.append(f"{s['id']}: volume {s['event_volume_m3']} != {vol:.2f}")
        cap = s['length_m'] * s['section_m2']
        if abs(cap - s['capacity_m3']) / max(cap, 0.01) > 0.02:
            errs.append(f"{s['id']}: capacity {s['capacity_m3']} != length×section {cap:.2f}")
        feat = by_id.get(s['id'])
        if feat:
            line = LineString([lnglat_to_en(x, y) for x, y in shape(feat['geometry']).coords])
            if line.buffer(0.25).intersection(crowns).area > 0.25:
                errs.append(f"{s['id']}: intersects recorded crown")
            if ease is not None and line.buffer(0.25).intersection(ease).area > 0.25:
                errs.append(f"{s['id']}: intersects easement")

    for p in summary['ponds']:
        e, n = p['east_m'], p['north_m']
        j = int(round(e - es[0]))
        i = int(round(n - ns[0]))
        if not (0 <= i < build.shape[0] and 0 <= j < build.shape[1]):
            errs.append(f"{p['id']}: outside grid")
            continue
        sc = float(build[i, j]) if np.isfinite(build[i, j]) else float('nan')
        print(f"{p['id']} buildable={sc:.3f} catch={p['catchment_m2']} on_channel={p['on_channel']}")
        if 'buildable_score' not in p:
            errs.append(f"{p['id']}: missing buildable_score info field")

        feat = by_id.get(p['id'])
        if not feat:
            errs.append(f"{p['id']}: missing geometry")
            continue
        poly = Polygon([lnglat_to_en(x, y) for x, y in shape(feat['geometry']).exterior.coords])
        if crowns.intersection(poly).area > 0.5:
            errs.append(f"{p['id']}: intersects recorded crown")
        if ease is not None and ease.intersection(poly).area > 0.5:
            errs.append(f"{p['id']}: intersects easement")
        if channel.intersection(poly).area > 0.5:
            errs.append(f"{p['id']}: intersects creek channel polygon")

        near_drain = drains is not None and poly.distance(drains) < 8.0
        high_flow = float(flow[i, j]) >= 500.0 if np.isfinite(flow[i, j]) else False
        expect = bool(near_drain or high_flow)
        if bool(p['on_channel']) != expect:
            if high_flow and not p['on_channel']:
                errs.append(f"{p['id']}: on_channel false but flow_accum>={500}")
            if p['on_channel'] and not near_drain and not high_flow:
                errs.append(f"{p['id']}: on_channel true but not near channel/high accum")

    if 'c21_headline_was' not in a:
        errs.append('assumptions.c21_headline_was missing')

    return errs


def self_test():
    summary = json.loads((ROOT / 'water-harvest.json').read_text(encoding='utf-8'))
    geo = json.loads((ROOT / 'water-harvest.geojson').read_text(encoding='utf-8'))
    bad = copy.deepcopy(summary)
    bad['routed_m2'] = bad['catchment_sum_m2'] + max(500, int(bad['catchment_sum_m2'] * 0.1))
    errs = run_checks(bad, geo)
    if not any('routed_m2' in e or 'catchment_sum' in e for e in errs):
        print('FAIL negative: expected routed vs catchment mismatch to be caught')
        raise SystemExit(1)
    print(f'OK negative check-water ({len(errs)} errs as expected)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return

    summary = json.loads((ROOT / 'water-harvest.json').read_text(encoding='utf-8'))
    geo = json.loads((ROOT / 'water-harvest.geojson').read_text(encoding='utf-8'))
    errs = run_checks(summary, geo)
    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print('OK check-water')


if __name__ == '__main__':
    main()
