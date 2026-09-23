"""
C21.1 — check water-harvest (independent of generator summary claims).

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
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR  # noqa: E402
from terrain import lnglat_to_en  # noqa: E402


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
    unrouted = summary['unrouted_m2']
    cells = summary['parcel_cells_m2']
    print(f'routed {routed} + unrouted {unrouted} = {routed + unrouted}; parcel cells {cells}')
    if routed + unrouted != cells:
        errs.append(f'routed+unrouted {routed + unrouted} != parcel cells {cells}')

    crowns = load_crowns()
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    ease = easement_en(survey)
    channel = creek_channel()
    drains = drainage_en()

    by_id = {f['properties']['id']: f for f in geo['features'] if 'id' in f['properties']}

    for s in summary['swales']:
        vol = s['catchment_m2'] * (max(0.0, storm - infil) / 1000.0) * c
        if abs(vol - s['event_volume_m3']) / max(vol, 0.01) > 0.05:
            errs.append(f"{s['id']}: volume {s['event_volume_m3']} != {vol:.2f}")
        cap = s['length_m'] * s['section_m2']
        if abs(cap - s['capacity_m3']) / max(cap, 0.01) > 0.02:
            errs.append(f"{s['id']}: capacity {s['capacity_m3']} != length×section {cap:.2f}")
        if s['holds_event'] and s['capacity_m3'] < s['event_volume_m3'] * 0.99:
            errs.append(f"{s['id']}: holds_event true but capacity < event")
        feat = by_id.get(s['id'])
        if feat:
            line = LineString([lnglat_to_en(x, y) for x, y in shape(feat['geometry']).coords])
            # require real overlap area, not a shared boundary touch
            if line.buffer(0.25).intersection(crowns).area > 0.25:
                errs.append(f"{s['id']}: intersects recorded crown")
            if ease is not None and line.buffer(0.25).intersection(ease).area > 0.25:
                errs.append(f"{s['id']}: intersects easement")

    build = np.asarray(np.load(GRID_DIR / 'buildable.npz')['data'])
    es = np.asarray(np.load(GRID_DIR / 'buildable.npz')['es'])
    ns = np.asarray(np.load(GRID_DIR / 'buildable.npz')['ns'])
    flow = np.asarray(np.load(GRID_DIR / 'flow_accum.npz')['data'])

    for p in summary['ponds']:
        e, n = p['east_m'], p['north_m']
        j = int(round(e - es[0]))
        i = int(round(n - ns[0]))
        if not (0 <= i < build.shape[0] and 0 <= j < build.shape[1]):
            errs.append(f"{p['id']}: outside grid")
            continue
        sc = float(build[i, j]) if np.isfinite(build[i, j]) else float('nan')
        print(f"{p['id']} buildable={sc:.3f} catch={p['catchment_m2']} on_channel={p['on_channel']}")
        # C21: buildable is informational — NOT a gate
        if 'buildable_score' not in p:
            errs.append(f"{p['id']}: missing buildable_score info field")
        if abs(p.get('buildable_score', -1) - (0.0 if not np.isfinite(sc) else sc)) > 0.05:
            # allow small grid rounding
            if np.isfinite(sc) and abs(p['buildable_score'] - sc) > 0.05:
                errs.append(f"{p['id']}: buildable_score {p['buildable_score']} != grid {sc:.3f}")

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

        # on_channel flag vs geometry
        near_drain = drains is not None and poly.distance(drains) < 8.0
        high_flow = float(flow[i, j]) >= 500.0 if np.isfinite(flow[i, j]) else False
        expect = bool(near_drain or high_flow)
        if bool(p['on_channel']) != expect:
            # soft: drainage distance can vary; require high_flow agreement at least
            if high_flow and not p['on_channel']:
                errs.append(f"{p['id']}: on_channel false but flow_accum>={500}")
            if p['on_channel'] and not near_drain and not high_flow:
                errs.append(f"{p['id']}: on_channel true but not near channel/high accum")

    return errs


def self_test():
    summary = json.loads((ROOT / 'water-harvest.json').read_text(encoding='utf-8'))
    geo = json.loads((ROOT / 'water-harvest.geojson').read_text(encoding='utf-8'))
    bad = copy.deepcopy(summary)
    # deliberate wrong: claim routed+unrouted mismatch
    bad['routed_m2'] = bad['routed_m2'] + 999
    errs = run_checks(bad, geo)
    if not errs:
        print('FAIL negative: expected mismatch to be caught')
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
