"""
C23.1 — outline audit for every models.json footprint.

  · recomputed EN area agrees with recorded area_m2 within 1%
  · ring is simple, closed, non-self-intersecting
  · outline lies inside the survey, or crosses_survey is true

    python scripts/check-outlines.py
    python scripts/check-outlines.py --self-test
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from shapely.geometry import Polygon, shape
from shapely.validation import explain_validity

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from terrain import lnglat_to_en  # noqa: E402

AREA_TOL = 0.01


def parcel_en():
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    return Polygon([
        lnglat_to_en(x, y)
        for x, y in shape(survey['features'][0]['geometry']).exterior.coords
    ])


def poly_from_footprint(ring):
    if len(ring) < 3:
        return None
    coords = [lnglat_to_en(float(a), float(b)) for a, b in ring]
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    return Polygon(coords)


def run_checks(man: dict) -> list[str]:
    errs = []
    parcel = parcel_en()
    models = man.get('models') or []
    print(f"{'id':28} {'claimed':>10} {'recomp':>10} {'delta':>10} {'pct':>7}  verdict")
    for m in models:
        mid = m['id']
        ring = m.get('footprint') or []
        poly = poly_from_footprint(ring)
        if poly is None:
            errs.append(f'{mid}: missing footprint')
            print(f'{mid:28} {"—":>10} {"—":>10} {"—":>10} {"—":>7}  FAIL missing')
            continue
        claimed = m.get('area_m2')
        if claimed is None:
            errs.append(f'{mid}: missing area_m2')
            claimed = poly.area
        claimed = float(claimed)
        recomp = float(poly.area)
        delta = claimed - recomp
        pct = abs(delta) / max(recomp, 1e-6)
        ok_area = pct <= AREA_TOL
        simple = poly.is_simple and poly.is_valid
        outside = float(poly.difference(parcel).area)
        flagged = bool(m.get('crosses_survey'))
        inside_ok = outside <= 1.0 or flagged
        if outside > 1.0 and not flagged:
            errs.append(f'{mid}: {outside:.1f} m² outside survey without crosses_survey')
        if outside <= 1.0 and flagged:
            errs.append(f'{mid}: crosses_survey set but outline is inside survey')
        if not simple:
            errs.append(f'{mid}: not a simple ring ({explain_validity(poly)})')
        if not ok_area:
            errs.append(
                f'{mid}: area_m2 {claimed:.1f} vs recomputed {recomp:.1f} '
                f'({100 * pct:.2f}% > {100 * AREA_TOL:.0f}%)'
            )
        verdict = 'OK' if (ok_area and simple and inside_ok) else 'FAIL'
        print(
            f'{mid:28} {claimed:10.1f} {recomp:10.1f} {delta:10.1f} '
            f'{100 * pct:6.2f}%  {verdict}'
            + (f'  crosses_survey outside={outside:.1f}' if outside > 1.0 else '')
        )
    return errs


def self_test():
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    bad = copy.deepcopy(man)
    # forge: inflate first model's claimed area
    bad['models'][0]['area_m2'] = float(bad['models'][0]['area_m2']) * 1.5
    errs = run_checks(bad)
    if not errs:
        print('FAIL negative: inflated area should fail')
        raise SystemExit(1)
    print(f'OK negative check-outlines ({len(errs)} errs as expected)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    errs = run_checks(man)
    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print(f'OK check-outlines: {len(man["models"])} models')


if __name__ == '__main__':
    main()
