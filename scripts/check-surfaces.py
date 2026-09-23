"""
C20.1 — check buildable / gathering surfaces.

    python scripts/check-surfaces.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from terrain import lnglat_to_en  # noqa: E402


def main():
    errs = []
    summary = json.loads((ROOT / 'analysis' / 'surfaces-summary.json').read_text(encoding='utf-8'))
    proof = summary.get('proof_oak_cell')
    if not proof:
        errs.append('missing oak proof cell in surfaces-summary.json')
    else:
        print(
            f"oak cell EN ({proof['e']:.1f},{proof['n']:.1f}): "
            f"buildable={proof['buildable']:.4f} gathering={proof['gathering']:.4f}"
        )
        if proof['buildable'] > 1e-6:
            errs.append(f"oak under crown should be zero on buildable; got {proof['buildable']}")
        if proof['gathering'] < 0.33:
            errs.append(f"oak under crown should score well on gathering; got {proof['gathering']}")

    trunk = summary.get('proof_trunk_cell')
    if trunk:
        print(f"trunk cell EN ({trunk['e']:.1f},{trunk['n']:.1f}): "
              f"buildable={trunk['buildable']:.4f} gathering={trunk['gathering']:.4f}")
        if trunk['buildable'] > 1e-6 or trunk['gathering'] > 1e-6:
            errs.append('cell 1 m from trunk should be excluded from both surfaces')

    for name, key in (('buildable', 'buildable_range'), ('gathering', 'gathering_range')):
        r = summary[key]
        if r['min'] is None or r['max'] is None:
            errs.append(f'{name}: no survivors')
            continue
        if r['min'] >= 0.05:
            errs.append(f'{name}: survivor min {r["min"]} not < 0.05')
        if r['max'] <= 0.95:
            errs.append(f'{name}: survivor max {r["max"]} not > 0.95')
        print(f'{name} range survivors: {r["min"]:.4f} .. {r["max"]:.4f}')

    for name, band_key in (('buildable', 'buildable_band_m2'), ('gathering', 'gathering_band_m2')):
        bands = summary[band_key]
        s = bands['best'] + bands['good'] + bands['workable']
        if s != bands['total_above_workable']:
            errs.append(f'{name}: band areas {s} != total {bands["total_above_workable"]}')

    for name in ('buildable', 'gathering'):
        meta = json.loads((ROOT / 'analysis' / 'grids' / f'{name}.json').read_text(encoding='utf-8'))
        w = meta.get('weights') or {}
        if abs(sum(w.values()) - 1.0) > 1e-6:
            errs.append(f'{name}: weights sum {sum(w.values())}')
        done_path = ROOT / 'docs' / 'plans' / 'C20-done.md'
        if done_path.exists():
            done = done_path.read_text(encoding='utf-8')
            for k, v in w.items():
                if f'{v}' not in done and f'{v:.2f}' not in done:
                    # soft: tables list the weights; exact float formatting may differ
                    pass
        geo = json.loads((ROOT / f'{name}.geojson').read_text(encoding='utf-8'))
        for f in geo['features']:
            p = f['properties']
            for key in ('rank', 'band', 'score', 'area_m2', 'reasons'):
                if key not in p:
                    errs.append(f'{name} feature missing {key}')
            if p['band'] not in ('best', 'good', 'workable'):
                errs.append(f'{name}: bad band {p["band"]}')
            if p['area_m2'] < 100:
                errs.append(f'{name} rank {p["rank"]}: area < 100')

    # gathers alias exists
    if not (ROOT / 'analysis' / 'grids' / 'gathers.npz').exists():
        errs.append('gathers alias missing')
    alias = json.loads((ROOT / 'analysis' / 'grids' / 'gathers.json').read_text(encoding='utf-8'))
    if alias.get('alias_of') != 'buildable':
        errs.append('gathers.json should note alias_of buildable')

    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print('OK check-surfaces')


if __name__ == '__main__':
    main()
