"""
Report footprint overlaps and trees inside footprints.

  Fails if any pair (except site-grounds and creek) overlaps by more than 0.5 m².
  Creek is landscape channel (like site-grounds) — reported, not failed.
  Tree trunks inside footprints are reported for all models. Fail only when a
  model listed in --strict-trees (default: the C15 moved set) covers a trunk
  without a clear/cleared note.

    python scripts/check-overlaps.py
    python scripts/check-overlaps.py --strict-trees farmstead-produce-stand,beekeeping-program,infrastructure
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from shapely.geometry import Point, Polygon

ROOT = Path(__file__).resolve().parents[1]
MAX_OVERLAP_M2 = 0.5
EXEMPT = {'site-grounds', 'creek'}
DEFAULT_STRICT = {
    'farmstead-produce-stand',
    'beekeeping-program',
    'infrastructure',
}


def load():
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    return pack, man


def fr_consts(pack):
    fr = pack['frame']
    return (
        float(fr['origin_lng']),
        float(fr['origin_lat']),
        float(fr['metres_per_deg_lng']),
        float(fr['metres_per_deg_lat']),
    )


def footprint_poly(m, ol, oa, mx, my) -> Polygon | None:
    fp = m.get('footprint')
    if not fp or len(fp) < 3:
        return None
    ring = [((p[0] - ol) * mx, (p[1] - oa) * my) for p in fp]
    if ring[0] != ring[-1]:
        ring = ring + [ring[0]]
    poly = Polygon(ring)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


def intentional_clear(note: str) -> bool:
    n = (note or '').lower()
    return bool(re.search(r'clear|cleared|remov|cut.?out|suppress', n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--strict-trees', default=','.join(sorted(DEFAULT_STRICT)))
    args = ap.parse_args()
    strict = {s for s in args.strict_trees.split(',') if s}

    pack, man = load()
    ol, oa, mx, my = fr_consts(pack)
    models = [m for m in man['models'] if m.get('footprint')]
    polys = {}
    for m in models:
        if m['id'] in EXEMPT:
            continue
        p = footprint_poly(m, ol, oa, mx, my)
        if p is None or p.is_empty:
            print(f"WARN {m['id']}: bad footprint")
            continue
        polys[m['id']] = (m, p)

    errs = []
    print('overlaps (m2):')
    ids = list(polys.keys())
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            inter = polys[a][1].intersection(polys[b][1]).area
            if inter > 0.01:
                print(f'  {a} x {b}: {inter:.2f}')
            if inter > MAX_OVERLAP_M2:
                errs.append(f'overlap {a} x {b}: {inter:.2f} m2 > {MAX_OVERLAP_M2}')

    # also report creek overlaps for information
    creek_m = next((m for m in man['models'] if m['id'] == 'creek'), None)
    if creek_m and creek_m.get('footprint'):
        cp = footprint_poly(creek_m, ol, oa, mx, my)
        print('creek overlaps (report only):')
        for mid, (m, poly) in polys.items():
            inter = poly.intersection(cp).area
            if inter > 0.01:
                print(f'  creek x {mid}: {inter:.2f}')

    trees = []
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            trees.append((float(row['x_east_dm']) / 10.0, float(row['y_north_dm']) / 10.0))

    print('trees inside footprints:')
    for mid, (m, poly) in list(polys.items()) + (
        [('creek', (creek_m, footprint_poly(creek_m, ol, oa, mx, my)))] if creek_m else []
    ):
        if mid == 'creek' and creek_m is None:
            continue
        hits = [t for t in trees if poly.contains(Point(t[0], t[1]))]
        if not hits:
            continue
        note = m.get('note') or ''
        flag = ''
        if mid in strict and not intentional_clear(note):
            flag = ' STRICT'
            errs.append(f'{mid}: {len(hits)} tree trunks inside moved footprint without clear-note')
        print(f'  {mid}: {len(hits)} trunks{flag}')

    for e in errs:
        print('FAIL', e)
    if errs:
        sys.exit(1)
    print(f'OK {len(polys)} footprints; no overlap > {MAX_OVERLAP_M2} m2 among buildings')


if __name__ == '__main__':
    main()
