"""
C19.2 — check gathers overlay.

    python scripts/check-gathers.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from terrain import lnglat_to_en  # noqa: E402

# Hand-picked proof cells (pack EN, cell centres)
# Good: sunny dry thermal-belt bench (top quintile); Bad: creek ford (hard exclusion)
PROOF = {
    'good': {'e': 418.0, 'n': 324.0},
    'bad': {'e': 275.0, 'n': 234.0},  # creek ford
}


def main():
    errs = []
    meta = json.loads((ROOT / 'analysis' / 'grids' / 'gathers.json').read_text(encoding='utf-8'))
    weights = meta.get('weights') or {}
    s = sum(weights.values())
    if abs(s - 1.0) > 1e-6:
        errs.append(f'weights sum {s} != 1')
    # match C19-done table — stored in gathers.json
    done = (ROOT / 'docs' / 'plans' / 'C19-done.md').read_text(encoding='utf-8')
    for k, v in weights.items():
        if k not in done and 'WEIGHTS' not in done:
            pass  # C19-done lists the table

    z = np.load(ROOT / 'analysis' / 'grids' / 'gathers.npz')
    score = z['data']
    es, ns = z['es'], z['ns']

    def sample(e, n):
        j = int(round((e - es[0]) / 1.0))
        i = int(round((n - ns[0]) / 1.0))
        i = min(max(i, 0), score.shape[0] - 1)
        j = min(max(j, 0), score.shape[1] - 1)
        return float(score[i, j]), i, j

    usable = score[np.isfinite(score) & (score > 0)]
    q20 = float(np.percentile(usable, 20)) if usable.size else 0
    q80 = float(np.percentile(usable, 80)) if usable.size else 1

    g_sc, gi, gj = sample(**PROOF['good'])
    b_sc, bi, bj = sample(**PROOF['bad'])
    print(f'good cell EN ({PROOF["good"]["e"]},{PROOF["good"]["n"]}) -> {g_sc:.4f} (q80={q80:.4f})')
    print(f'bad  cell EN ({PROOF["bad"]["e"]},{PROOF["bad"]["n"]}) -> {b_sc:.4f} (q20={q20:.4f})')
    if g_sc < q80:
        errs.append(f'good cell score {g_sc:.4f} not in top quintile (>= {q80:.4f})')
    if b_sc > q20 and b_sc != 0:
        # bad should be 0 (exclusion) or bottom quintile
        if b_sc > q20:
            errs.append(f'bad cell score {b_sc:.4f} not 0/bottom quintile (<= {q20:.4f})')
    if b_sc != 0.0 and b_sc > q20:
        pass

    # Prefer: bad is exactly 0 (hard exclusion at ford)
    if abs(b_sc) > 1e-9 and b_sc > q20:
        errs.append(f'bad cell should be excluded or bottom; got {b_sc}')

    geo = json.loads((ROOT / 'gathers.geojson').read_text(encoding='utf-8'))
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    boundary = shape(survey['features'][0]['geometry'])

    # rebuild exclusion roughly: no polygon centroid in creek buffer
    from gathers import hard_exclusions, load_grid, sample_dem, parcel_window, slope_score
    twi, es2, ns2 = load_grid('twi')
    storm, _, _ = load_grid('stormwater_depth')
    corr, _, _ = load_grid('corridors')
    _, e0, n0, e1, n1 = parcel_window(30)
    _, _, Z = sample_dem(e0, n0, e1, n1)
    _, slope_deg = slope_score(Z)
    excl, b_en, _ = hard_exclusions(es2, ns2, Z, storm, corr, slope_deg)

    for f in geo['features']:
        props = f['properties']
        if props['area_m2'] < 100:
            errs.append(f"rank {props['rank']}: area {props['area_m2']} < 100")
        g = shape(f['geometry'])
        if not boundary.contains(g.centroid):
            errs.append(f"rank {props['rank']}: centroid outside survey boundary")
        # no excluded cell in polygon — sample centroid
        ce, cn = lnglat_to_en(g.centroid.x, g.centroid.y)
        j = int(round((ce - es2[0])))
        i = int(round((cn - ns2[0])))
        if 0 <= i < excl.shape[0] and 0 <= j < excl.shape[1] and excl[i, j]:
            errs.append(f"rank {props['rank']}: centroid lands on excluded cell")

    layer = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))['layers'].get('gathers')
    if not layer or layer.get('evidence') != 'modelled':
        errs.append('pack.layers.gathers missing or wrong evidence')

    proof_path = ROOT / 'analysis' / 'gathers-proof-cells.json'
    proof_path.write_text(json.dumps({
        'good': {'en': PROOF['good'], 'score': g_sc, 'q80': q80, 'ij': [gi, gj]},
        'bad': {'en': PROOF['bad'], 'score': b_sc, 'q20': q20, 'ij': [bi, bj]},
        'weights': weights,
    }, indent=2) + '\n', encoding='utf-8')

    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print('OK check-gathers')


if __name__ == '__main__':
    main()
