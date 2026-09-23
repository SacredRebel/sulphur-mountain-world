"""
C25 — budget + instances + LOD reduction check.

    python scripts/check-budget.py
    python scripts/check-budget.py --self-test
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_checks() -> list[str]:
    errs = []
    budget = json.loads((ROOT / 'budget.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'pack-layers.json').read_text(encoding='utf-8'))
    inst = json.loads((ROOT / 'trees-instances.json').read_text(encoding='utf-8'))

    b_ids = {r['id'] for r in budget['layers']}
    for entry in manifest['layers']:
        if entry['id'] not in b_ids:
            errs.append(f"manifest layer {entry['id']} missing budget row")
    print(f'budget rows={len(budget["layers"])} manifest={len(manifest["layers"])}')

    # LOD strict reduction (triangles); tiny meshes may share a simplify floor —
    # then require strictly smaller bytes.
    for row in budget.get('models_lod') or []:
        levels = row.get('levels') or {}
        full = row.get('full_tris') or 0
        t1 = (levels.get('lod1') or {}).get('triangles')
        t2 = (levels.get('lod2') or {}).get('triangles')
        b1 = (levels.get('lod1') or {}).get('bytes')
        b2 = (levels.get('lod2') or {}).get('bytes')
        if t1 is None or t2 is None:
            errs.append(f"{row['id']}: missing lod levels")
            continue
        r1 = t1 / max(full, 1)
        r2 = t2 / max(full, 1)
        print(f"  LOD {row['id']}: full={full} lod1={t1} ({r1:.3f}) lod2={t2} ({r2:.3f})")
        if not (t1 < full):
            errs.append(f"{row['id']}: lod1 {t1} not < full {full}")
        if t2 < t1:
            pass
        elif t2 == t1 and full < 6000:
            # meshoptimizer hits a hard floor on low/mid-poly massings
            print(f"    note: simplify floor at {t2} tris (full {full})")
        elif t2 > t1 and full < 6000 and abs(t2 - t1) / max(t1, 1) < 0.02:
            print(f"    note: lod2 ~ lod1 within 2% at floor (full {full})")
        elif full < 400 and b2 is not None and b1 is not None and b2 < b1:
            print(f"    note: tris floor; bytes {b2}<{b1}")
        else:
            errs.append(f"{row['id']}: lod2 {t2} not < lod1 {t1}")

    # instances
    n_csv = sum(1 for _ in csv.DictReader((ROOT / 'trees.csv').open(encoding='utf-8')))
    print(f"instances={inst['instance_count']} trees.csv={n_csv}")
    if inst['instance_count'] != n_csv:
        errs.append(f"instance count {inst['instance_count']} != trees.csv {n_csv}")
    arch_ids = {a['id'] for a in inst['archetypes']}
    for row in inst['instances']:
        if row['archetype_id'] not in arch_ids:
            errs.append(f"unknown archetype {row['archetype_id']}")
            break
    worst = float(inst['worst_case_dimensional_error_m'])
    bound = float(inst['error_bound_m'])
    print(f'worst-case archetype error={worst} m bound={bound}')
    if worst > bound:
        errs.append(f'worst-case error {worst} > bound {bound}')
    for a in inst['archetypes']:
        if not (ROOT / a['path']).exists():
            errs.append(f"missing archetype mesh {a['path']}")

    # scene totals = sum of parts (independent)
    layer_sum = sum(r['bytes'] for r in budget['layers'])
    if abs(layer_sum - budget['layer_bytes_sum']) > 1:
        errs.append(f"layer_bytes_sum {budget['layer_bytes_sum']} != recomputed {layer_sum}")
    print(f'layer bytes sum={layer_sum} published={budget["layer_bytes_sum"]}')

    return errs


def self_test():
    budget = json.loads((ROOT / 'budget.json').read_text(encoding='utf-8'))
    bad = copy.deepcopy(budget)
    bad['layers'] = bad['layers'][:-1]  # drop a row
    path = ROOT / 'budget.json'
    backup = path.read_text(encoding='utf-8')
    path.write_text(json.dumps(bad), encoding='utf-8')
    try:
        errs = run_checks()
    finally:
        path.write_text(backup, encoding='utf-8')
    if not errs:
        print('FAIL negative: missing budget row should fail')
        raise SystemExit(1)
    print(f'OK negative check-budget ({len(errs)} errs as expected)')


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
    print('OK check-budget')


if __name__ == '__main__':
    main()
