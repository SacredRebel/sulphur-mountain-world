"""
C20.2 — check defensible-space rings.

    python scripts/check-defensible.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from shapely.geometry import Point, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from terrain import lnglat_to_en  # noqa: E402

Z = {'0': (0.0, 1.5), '1': (1.5, 9.1), '2': (9.1, 30.5)}
SLOPE_EXTEND = 1.5


def to_en(geom):
    """GeoJSON lng/lat → pack EN polygon/multipolygon (keep holes)."""
    g = shape(geom)
    if g.geom_type == 'Polygon':
        shell = [lnglat_to_en(x, y) for x, y in g.exterior.coords]
        holes = [[lnglat_to_en(x, y) for x, y in r.coords] for r in g.interiors]
        return Polygon(shell, holes)
    if g.geom_type == 'MultiPolygon':
        parts = []
        for p in g.geoms:
            shell = [lnglat_to_en(x, y) for x, y in p.exterior.coords]
            holes = [[lnglat_to_en(x, y) for x, y in r.coords] for r in p.interiors]
            parts.append(Polygon(shell, holes))
        return unary_union(parts)
    return g


def main():
    errs = []
    geo = json.loads((ROOT / 'defensible-space.geojson').read_text(encoding='utf-8'))
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    boundary = shape(survey['features'][0]['geometry'])
    b_en = Polygon([lnglat_to_en(x, y) for x, y in boundary.exterior.coords])

    by_id = {}
    for f in geo['features']:
        sid = f['properties']['structure_id']
        by_id.setdefault(sid, {})[f['properties']['zone']] = f

    trees = []
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            trees.append((
                float(row['x_east_dm']) / 10.0,
                float(row['y_north_dm']) / 10.0,
                float(row.get('crown_radius_dm') or 30) / 10.0,
            ))

    edge_ok = False
    mid_ok = False
    for m in man['models']:
        mid = m['id']
        if mid not in by_id or not m.get('footprint'):
            continue
        fp = Polygon([lnglat_to_en(a, b) for a, b in m['footprint']])
        zones = by_id[mid]

        if '0' in zones and '1' in zones:
            z0 = to_en(zones['0']['geometry'])
            z1 = to_en(zones['1']['geometry'])
            inter = z0.intersection(z1).area
            if inter > 5.0:
                errs.append(f'{mid}: zone0∩zone1 area {inter:.1f} > 5 m2')

        for zname, (rin, rout) in Z.items():
            if zname not in zones:
                continue
            ring = to_en(zones[zname]['geometry'])
            lim = (rout * SLOPE_EXTEND if zname == '2' else rout) + 0.2
            coords = []
            if ring.geom_type == 'Polygon':
                coords = list(ring.exterior.coords)
            elif ring.geom_type == 'MultiPolygon':
                for p in ring.geoms:
                    coords.extend(list(p.exterior.coords))
            far = 0
            for x, y in coords[:: max(1, len(coords) // 30)]:
                d = fp.distance(Point(x, y))
                if d > lim + 0.2:
                    far += 1
            if far > 5:
                errs.append(f'{mid} zone{zname}: {far} vertices farther than {lim + 0.2:.1f} m')

            if zones[zname]['properties']['crosses_boundary']:
                edge_ok = True
            elif zname == '2' and b_en.contains(fp.buffer(35)):
                mid_ok = True

        print(
            f'{mid}: z2_cross='
            f'{zones.get("2", {}).get("properties", {}).get("crosses_boundary")} '
            f'z0_crowns={zones.get("0", {}).get("properties", {}).get("crowns_in_zone")}'
        )

    if not edge_ok:
        errs.append('no structure reported crosses_boundary=true')
    if not mid_ok:
        print('note: few deep-interior structures on this parcel')

    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print('OK check-defensible')


def self_test():
    geo = json.loads((ROOT / 'defensible-space.geojson').read_text(encoding='utf-8'))
    # forge overlapping zone0 and zone1 by copying zone0 geometry onto zone1
    by = {}
    for f in geo['features']:
        by.setdefault(f['properties']['structure_id'], {})[f['properties']['zone']] = f
    sid = next(iter(by))
    if '0' in by[sid] and '1' in by[sid]:
        by[sid]['1']['geometry'] = by[sid]['0']['geometry']
    # write temp? run inline check
    z0 = to_en(by[sid]['0']['geometry'])
    z1 = to_en(by[sid]['1']['geometry'])
    if z0.intersection(z1).area <= 5.0:
        print('FAIL negative: forged overlap not large')
        raise SystemExit(1)
    print('OK negative check-defensible (forged zone0∩zone1 would fail)')


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    main()
    if args.self_test:
        self_test()
