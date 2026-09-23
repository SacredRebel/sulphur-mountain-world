"""
C24 — check walkable ground, graph totals, and collision deviation.

    python scripts/check-walkable.py
    python scripts/check-walkable.py --self-test
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR  # noqa: E402
from terrain import lnglat_to_en  # noqa: E402

SLOPE_MAX_DEG = 30.0


def dem_slope():
    build = np.load(GRID_DIR / 'buildable.npz')
    es, ns = np.asarray(build['es']), np.asarray(build['ns'])
    pack = np.load(GRID_DIR / 'dem_1m.npz')
    des, dns, zd = np.asarray(pack['es']), np.asarray(pack['ns']), np.asarray(pack['Z'], dtype=np.float64)
    jj = np.clip(np.round(es - des[0]).astype(int), 0, zd.shape[1] - 1)
    ii = np.clip(np.round(ns - dns[0]).astype(int), 0, zd.shape[0] - 1)
    jj_g, ii_g = np.meshgrid(jj, ii)
    Z = zd[ii_g, jj_g]
    gy, gx = np.gradient(Z, 1.0)
    return es, ns, Z, np.degrees(np.arctan(np.hypot(gx, gy)))


def walkable_union(geo):
    polys = []
    for f in geo['features']:
        g = shape(f['geometry'])  # lng/lat with holes
        if g.geom_type == 'Polygon':
            exterior = [lnglat_to_en(x, y) for x, y in g.exterior.coords]
            holes = [[lnglat_to_en(x, y) for x, y in hole.coords] for hole in g.interiors]
            polys.append(Polygon(exterior, holes))
        elif g.geom_type == 'MultiPolygon':
            for p in g.geoms:
                exterior = [lnglat_to_en(x, y) for x, y in p.exterior.coords]
                holes = [[lnglat_to_en(x, y) for x, y in hole.coords] for hole in p.interiors]
                polys.append(Polygon(exterior, holes))
    return unary_union(polys) if polys else None


def oak_proof_point():
    """Under a large crown, clear of trunks, on gentle ground."""
    # reuse C20/C21 oak cell EN (260.8, 267.8) — under crowns, gathering=1
    return 260.8, 267.8


def footprint_point():
    """A 1 m cell centre known to lie inside a building footprint mask."""
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    parts = []
    for m in man['models']:
        if m['id'] in ('site-grounds', 'creek') or not m.get('footprint'):
            continue
        parts.append(Polygon([lnglat_to_en(a, b) for a, b in m['footprint']]))
    fp = unary_union(parts)
    build = np.load(GRID_DIR / 'buildable.npz')
    es, ns = np.asarray(build['es']), np.asarray(build['ns'])
    EE, NN = np.meshgrid(es, ns)
    from shapely import contains_xy
    mask = contains_xy(fp, EE, NN)
    ii, jj = np.where(mask)
    i, j = ii[len(ii) // 2], jj[len(jj) // 2]
    return float(es[j]), float(ns[i])


def steep_point(es, ns, slope):
    # find a parcel cell with slope > threshold
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    parcel = Polygon([lnglat_to_en(x, y) for x, y in shape(survey['features'][0]['geometry']).exterior.coords])
    EE, NN = np.meshgrid(es, ns)
    from shapely import contains_xy
    in_p = contains_xy(parcel, EE, NN)
    cand = np.argwhere(in_p & np.isfinite(slope) & (slope > SLOPE_MAX_DEG + 2))
    if len(cand) == 0:
        return None
    i, j = cand[len(cand) // 2]
    return float(es[j]), float(ns[i]), float(slope[i, j])


def run_checks() -> list[str]:
    errs = []
    geo = json.loads((ROOT / 'walkable.geojson').read_text(encoding='utf-8'))
    graph = json.loads((ROOT / 'walk-graph.json').read_text(encoding='utf-8'))
    coll = json.loads((ROOT / 'collision.json').read_text(encoding='utf-8'))
    u = walkable_union(geo)
    if u is None or u.is_empty:
        return ['walkable.geojson empty']

    sum_areas = sum(float(f['properties']['area_m2']) for f in geo['features'])
    print(f'component areas sum={sum_areas:.1f} graph total={graph["total_area_m2"]}')
    if abs(sum_areas - graph['total_area_m2']) / max(sum_areas, 1) > 0.02:
        errs.append(f'area sum {sum_areas} vs graph {graph["total_area_m2"]}')

    # independent: sum of shapely areas vs published sum
    indep = float(u.area) if u.geom_type == 'Polygon' else sum(g.area for g in u.geoms)
    print(f'independent union area={indep:.1f} published sum={sum_areas:.1f}')
    # union can be slightly less than sum if overlaps; allow 5%
    if abs(indep - sum_areas) / max(sum_areas, 1) > 0.05:
        errs.append(f'union area {indep:.1f} vs component sum {sum_areas:.1f}')

    oak = oak_proof_point()
    if not u.contains(Point(*oak)):
        errs.append(f'oak crown point {oak} should be walkable')
    else:
        print(f'oak point {oak}: walkable')

    fp = footprint_point()
    if u.contains(Point(*fp)):
        errs.append(f'footprint point {fp} should NOT be walkable')
    else:
        print(f'footprint point {fp}: not walkable')

    es, ns, Z, slope = dem_slope()
    steep = steep_point(es, ns, slope)
    if steep is None:
        errs.append('could not find steep proof point')
    else:
        e, n, s = steep
        if u.contains(Point(e, n)):
            errs.append(f'steep point ({e:.1f},{n:.1f}) slope={s:.1f} should NOT be walkable')
        else:
            print(f'steep point ({e:.1f},{n:.1f}) slope={s:.1f}: not walkable')

    # collision
    if coll['triangles'] >= 50_000:
        errs.append(f"collision tris {coll['triangles']} >= 50000")
    if coll['max_deviation_from_dem_m'] > coll['deviation_bound_m']:
        errs.append(
            f"collision max_dev {coll['max_deviation_from_dem_m']} > "
            f"bound {coll['deviation_bound_m']}"
        )
    glb = ROOT / coll['path']
    if not glb.exists():
        errs.append(f"missing {coll['path']}")
    print(
        f"collision tris={coll['triangles']} max_dev={coll['max_deviation_from_dem_m']} "
        f"bound={coll['deviation_bound_m']}"
    )

    # canopy not excluded: oak point under crowns — already checked walkable
    return errs


def self_test():
    geo = json.loads((ROOT / 'walkable.geojson').read_text(encoding='utf-8'))
    bad = copy.deepcopy(geo)
    if not bad['features']:
        print('FAIL negative: no features')
        raise SystemExit(1)
    # inflate the largest component so sum diverges from the graph total
    largest = max(bad['features'], key=lambda f: float(f['properties']['area_m2']))
    largest['properties']['area_m2'] = float(largest['properties']['area_m2']) * 2.0
    good = ROOT / 'walkable.geojson'
    backup = good.read_text(encoding='utf-8')
    # also forge graph to keep old total so the sum check trips
    good.write_text(json.dumps(bad), encoding='utf-8')
    try:
        errs = run_checks()
    finally:
        good.write_text(backup, encoding='utf-8')
    if not errs:
        print('FAIL negative: forged area should fail')
        raise SystemExit(1)
    print(f'OK negative check-walkable ({len(errs)} errs as expected)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    errs = run_checks()
    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print('OK check-walkable')


if __name__ == '__main__':
    main()
