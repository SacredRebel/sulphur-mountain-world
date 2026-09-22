"""
Check pack frame against survey calls, and that trees keep their lng/lat.

  · every survey call length within 0.1 ft of distance_ft
  · every tree's longitude/latitude unchanged within 1 cm vs a baseline snapshot
    written on first run after fix-frame (or vs --baseline)

    python scripts/check-frame.py
    python scripts/check-frame.py --write-baseline
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'analysis' / 'trees-lnglat-baseline.json'
FT = 0.3048  # international foot; survey uses US survey foot ≈ 1200/3937 m
US_FT = 1200.0 / 3937.0


def load_pack():
    return json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))


def en_to_ll(e, n, fr):
    return (
        float(fr['origin_lng']) + e / float(fr['metres_per_deg_lng']),
        float(fr['origin_lat']) + n / float(fr['metres_per_deg_lat']),
    )


def haversine_m(a, b):
    R = 6378137.0
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = math.radians(b[0] - a[0])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def check_calls(fr) -> list[str]:
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    errs = []
    for f in survey['features']:
        p = f.get('properties') or {}
        if p.get('layer') != 'call' or 'distance_ft' not in p:
            continue
        coords = f['geometry']['coordinates']
        if len(coords) < 2:
            continue
        # length from lng/lat along ellipsoid chord ≈ haversine
        length_m = 0.0
        for i in range(len(coords) - 1):
            length_m += haversine_m(coords[i], coords[i + 1])
        # also via pack frame
        e0 = (coords[0][0] - fr['origin_lng']) * fr['metres_per_deg_lng']
        n0 = (coords[0][1] - fr['origin_lat']) * fr['metres_per_deg_lat']
        e1 = (coords[-1][0] - fr['origin_lng']) * fr['metres_per_deg_lng']
        n1 = (coords[-1][1] - fr['origin_lat']) * fr['metres_per_deg_lat']
        frame_m = math.hypot(e1 - e0, n1 - n0)
        # survey distances are US survey feet
        recorded_m = float(p['distance_ft']) * US_FT
        frame_ft = frame_m / US_FT
        delta_ft = abs(frame_ft - float(p['distance_ft']))
        if delta_ft > 0.1:
            errs.append(
                f"call {p.get('n')}: frame {frame_ft:.3f} ft vs recorded {p['distance_ft']} "
                f"(d {delta_ft:.3f} ft > 0.1)"
            )
    return errs


def tree_lnglats(fr):
    out = []
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            e = float(row['x_east_dm']) / 10.0
            n = float(row['y_north_dm']) / 10.0
            lng, lat = en_to_ll(e, n, fr)
            out.append([round(lng, 10), round(lat, 10)])
    return out


def check_trees(fr, baseline) -> list[str]:
    now = tree_lnglats(fr)
    if len(now) != len(baseline):
        return [f'tree count {len(now)} != baseline {len(baseline)}']
    errs = []
    worst = 0.0
    for i, (a, b) in enumerate(zip(now, baseline)):
        d = haversine_m(a, b)
        worst = max(worst, d)
        if d > 0.01:  # 1 cm
            errs.append(f'tree {i}: moved {d * 100:.2f} cm')
            if len(errs) > 20:
                errs.append('…')
                break
    if not errs:
        print(f'trees lng/lat stable; worst shift {worst * 1000:.2f} mm')
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write-baseline', action='store_true')
    args = ap.parse_args()
    pack = load_pack()
    fr = pack['frame']

    call_errs = check_calls(fr)
    for e in call_errs:
        print('FAIL', e)

    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'note': 'lng/lat of every trees.csv row after C15.3 reproject; check-frame compares to this',
            'frame': {
                'metres_per_deg_lng': fr['metres_per_deg_lng'],
                'metres_per_deg_lat': fr['metres_per_deg_lat'],
            },
            'trees': tree_lnglats(fr),
        }
        BASELINE.write_text(json.dumps(data) + '\n', encoding='utf-8')
        print(f'wrote baseline {BASELINE} ({len(data["trees"])} trees)')
        # after write, stability vs self is trivial — still check calls
        if call_errs:
            sys.exit(1)
        print('OK calls')
        return

    if not BASELINE.exists():
        print('FAIL no baseline — run: python scripts/check-frame.py --write-baseline')
        sys.exit(1)
    base = json.loads(BASELINE.read_text(encoding='utf-8'))
    # Baseline stores absolute lng/lat. After reproject, trees at new dm must yield same lng/lat.
    tree_errs = check_trees(fr, base['trees'])
    for e in tree_errs:
        print('FAIL', e)

    if call_errs or tree_errs:
        sys.exit(1)
    print(f'OK {len(base["trees"])} trees; all survey calls within 0.1 ft')


if __name__ == '__main__':
    main()
