"""
C20.3 — check water-harvest numbers.

    python scripts/check-water.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR  # noqa: E402
from terrain import lnglat_to_en  # noqa: E402


def main():
    errs = []
    summary = json.loads((ROOT / 'water-harvest.json').read_text(encoding='utf-8'))
    a = summary['assumptions']
    storm = summary['storm_mm']
    c = a['runoff_coefficient']
    infil = a['infiltration_mm_during_event']
    parcel = summary['parcel_m2']

    # reproduce parcel runoff
    want = parcel * (max(0.0, storm - infil) / 1000.0) * c
    got = summary['parcel_runoff_m3_25mm']
    if abs(want - got) / max(want, 1) > 0.01:
        errs.append(f'parcel runoff {got} != recomputed {want:.1f}')
    print(f'parcel runoff: {got} m3 (recomputed {want:.1f})')

    catch_sum = summary['catchment_sum_m2']
    limit = summary['parcel_plus_upslope_m2']
    print(f'catchment sum {catch_sum:.0f} m2; parcel+upslope {limit:.0f} m2')
    if catch_sum > limit * 1.01:
        errs.append(f'catchments {catch_sum} exceed parcel+upslope {limit}')

    # each swale volume reproducible
    for s in summary['swales']:
        vol = s['catchment_m2'] * (max(0.0, storm - infil) / 1000.0) * c
        if abs(vol - s['event_volume_m3']) / max(vol, 0.01) > 0.02:
            errs.append(f"{s['id']}: volume {s['event_volume_m3']} != {vol:.2f}")
        cap = s['length_m'] * a['swale_section_m2']
        if abs(cap - s['capacity_m3']) / max(cap, 0.01) > 0.02:
            errs.append(f"{s['id']}: capacity {s['capacity_m3']} != {cap:.2f}")

    build = np.asarray(np.load(GRID_DIR / 'buildable.npz')['data'])
    es = np.asarray(np.load(GRID_DIR / 'buildable.npz')['es'])
    ns = np.asarray(np.load(GRID_DIR / 'buildable.npz')['ns'])
    for p in summary['ponds']:
        e, n = p['east_m'], p['north_m']
        j = int(round(e - es[0]))
        i = int(round(n - ns[0]))
        if not (0 <= i < build.shape[0] and 0 <= j < build.shape[1]):
            errs.append(f"{p['id']}: outside grid")
            continue
        sc = float(build[i, j])
        print(f"{p['id']} buildable={sc:.3f} catch={p['catchment_m2']}")
        if sc < 0.05 or not np.isfinite(sc):
            errs.append(f"{p['id']}: not on buildable ground (score {sc})")

    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print('OK check-water')


if __name__ == '__main__':
    main()
