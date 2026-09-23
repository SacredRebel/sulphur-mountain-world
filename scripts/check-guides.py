"""
C27 — check guides + grid (+ symbolic isolation).

    python scripts/check-guides.py
    python scripts/check-guides.py --self-test
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR  # noqa: E402
from terrain import lnglat_to_en  # noqa: E402

GUIDES = ROOT / 'guides.geojson'
GRID = ROOT / 'grid.json'
CONSTRUCTION = ROOT / 'construction-grid.geojson'
SURVEY = ROOT / 'survey.geojson'

SURVEY_TOL_M = 0.1 * 0.3048  # 0.1 ft
PHYSICAL_SCRIPTS = [
    ROOT / 'scripts' / 'surfaces.py',
    ROOT / 'scripts' / 'water-harvest.py',
    ROOT / 'scripts' / 'defensible-space.py',
]
SYMBOLIC_NAMES = ('construction-grid', 'construction_grid', 'authority: symbolic')


def pack_bbox_en():
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    bb = pack['aoi']['bbox']
    corners = [
        lnglat_to_en(bb[0], bb[1]),
        lnglat_to_en(bb[2], bb[1]),
        lnglat_to_en(bb[2], bb[3]),
        lnglat_to_en(bb[0], bb[3]),
    ]
    es = [c[0] for c in corners]
    ns = [c[1] for c in corners]
    return min(es), min(ns), max(es), max(ns)


def geom_outside_aoi(g, pad_m=0.5) -> bool:
    e0, n0, e1, n1 = pack_bbox_en()
    e0 -= pad_m
    n0 -= pad_m
    e1 += pad_m
    n1 += pad_m

    def check_pt(lng, lat):
        e, n = lnglat_to_en(lng, lat)
        return e < e0 or e > e1 or n < n0 or n > n1

    if g.geom_type == 'Point':
        return check_pt(g.x, g.y)
    if g.geom_type == 'LineString':
        return any(check_pt(x, y) for x, y in g.coords)
    if g.geom_type == 'Polygon':
        return any(check_pt(x, y) for x, y in g.exterior.coords)
    if hasattr(g, 'geoms'):
        return any(geom_outside_aoi(p, pad_m) for p in g.geoms)
    return False


def run_checks() -> list[str]:
    errs: list[str] = []
    guides = json.loads(GUIDES.read_text(encoding='utf-8'))
    grid = json.loads(GRID.read_text(encoding='utf-8'))
    construction = json.loads(CONSTRUCTION.read_text(encoding='utf-8'))
    survey = json.loads(SURVEY.read_text(encoding='utf-8'))

    print(f"guides={len(guides['features'])} construction={len(construction['features'])}")

    # --- survey-derived within 0.1 ft of source ---
    calls = {
        (f.get('properties') or {}).get('n'): shape(f['geometry'])
        for f in survey['features']
        if (f.get('properties') or {}).get('layer') == 'call'
    }
    monuments = {
        (f.get('properties') or {}).get('label'): shape(f['geometry'])
        for f in survey['features']
        if (f.get('properties') or {}).get('layer') == 'monument'
    }
    n_survey = 0
    for f in guides['features']:
        p = f.get('properties') or {}
        g = shape(f['geometry'])
        if p.get('kind') == 'survey_call':
            src = calls.get(p.get('call_n'))
            if src is None:
                errs.append(f"survey_call missing source n={p.get('call_n')}")
                continue
            # Hausdorff-ish: max distance between corresponding roughly by nearest
            d = g.hausdorff_distance(src)  # degrees — convert via mid-lat metres
            # use EN
            def to_en_line(geom):
                if geom.geom_type == 'LineString':
                    return [(lnglat_to_en(x, y)) for x, y in geom.coords]
                return []
            a = to_en_line(g)
            b = to_en_line(src)
            if len(a) >= 2 and len(b) >= 2:
                # endpoint distances
                d0 = math.hypot(a[0][0] - b[0][0], a[0][1] - b[0][1])
                d1 = math.hypot(a[-1][0] - b[-1][0], a[-1][1] - b[-1][1])
                # also reverse match
                d0r = math.hypot(a[0][0] - b[-1][0], a[0][1] - b[-1][1])
                d1r = math.hypot(a[-1][0] - b[0][0], a[-1][1] - b[0][1])
                dist = min(max(d0, d1), max(d0r, d1r))
                n_survey += 1
                if dist > SURVEY_TOL_M:
                    errs.append(
                        f"survey_call n={p.get('call_n')} {dist:.4f} m > {SURVEY_TOL_M:.4f} m"
                    )
        elif p.get('kind') == 'monument':
            src = monuments.get(p.get('label'))
            if src is None:
                errs.append(f"monument missing source {p.get('label')}")
                continue
            e, n = lnglat_to_en(g.x, g.y)
            se, sn = lnglat_to_en(src.x, src.y)
            dist = math.hypot(e - se, n - sn)
            n_survey += 1
            if dist > SURVEY_TOL_M:
                errs.append(f"monument {p.get('label')} {dist:.4f} m > tol")

    print(f'survey-derived guides checked={n_survey} tol={SURVEY_TOL_M:.4f} m')

    # --- contour DEM follow ---
    dem = np.load(GRID_DIR / 'dem_1m.npz')
    es, ns, Z = dem['es'], dem['ns'], dem['Z'].astype(float)
    tol = float((guides.get('properties') or {}).get('contour_dem_tol_m') or 1.5)
    n_c, worst = 0, 0.0
    for f in guides['features']:
        p = f.get('properties') or {}
        if p.get('kind') != 'contour':
            continue
        elev = float(p['elevation_m'])
        g = shape(f['geometry'])
        if g.geom_type != 'LineString':
            continue
        # sample every ~5th vertex
        coords = list(g.coords)
        step = max(1, len(coords) // 20)
        for lng, lat in coords[::step]:
            e, n = lnglat_to_en(lng, lat)
            # nearest cell
            ci = int(np.clip(np.round((e - es[0]) / (es[1] - es[0])), 0, len(es) - 1))
            ri = int(np.clip(np.round((n - ns[0]) / (ns[1] - ns[0])), 0, len(ns) - 1))
            z = float(Z[ri, ci])
            if not np.isfinite(z):
                continue
            err = abs(z - elev)
            worst = max(worst, err)
            n_c += 1
            if err > tol:
                errs.append(f'contour {elev}m DEM err {err:.2f} > {tol}')
                break
    print(f'contour samples={n_c} worst_err={worst:.3f} m tol={tol}')

    # --- grid worked example round-trip ---
    ex = grid.get('worked_example') or {}
    ix, iy = ex.get('index') or [None, None]
    lnglat = ex.get('lnglat')
    back = ex.get('roundtrip_index')
    if ix is None or lnglat is None or back is None:
        errs.append('grid.json missing worked_example')
    else:
        if abs(back[0] - ix) > 1e-9 or abs(back[1] - iy) > 1e-9:
            errs.append(f'grid roundtrip {back} != index {[ix, iy]}')
        # independently recompute
        gdef = grid['grid']
        ox = float(gdef['origin_east_m'])
        oy = float(gdef['origin_north_m'])
        spacing = float(gdef['spacing_m'])
        rot = float(gdef['rotation_deg_from_true_north'])
        rad = math.radians(rot)
        ux, uy = math.sin(rad), math.cos(rad)
        vx, vy = math.cos(rad), -math.sin(rad)
        e = ox + ix * spacing * vx + iy * spacing * ux
        n = oy + ix * spacing * vy + iy * spacing * uy
        fr = grid['frame']
        lng = fr['origin_lng'] + e / fr['metres_per_deg_lng']
        lat = fr['origin_lat'] + n / fr['metres_per_deg_lat']
        if abs(lng - lnglat[0]) > 1e-7 or abs(lat - lnglat[1]) > 1e-7:
            errs.append(
                f'independent lnglat ({lng},{lat}) != published {lnglat}'
            )
        print(f'grid worked example index={ex["index"]} lnglat={lnglat} OK')

    # --- no guide outside pack AOI ---
    outside = 0
    for f in guides['features'] + construction['features']:
        g = shape(f['geometry'])
        if geom_outside_aoi(g):
            outside += 1
            if outside <= 3:
                errs.append(
                    f"outside AOI: {f.get('properties', {}).get('kind')} "
                    f"{f.get('properties', {}).get('source')}"
                )
    if outside:
        errs.append(f'{outside} features outside pack AOI')
    else:
        print('all guides inside pack AOI')

    # --- symbolic authority on construction layer ---
    cp = construction.get('properties') or {}
    if cp.get('authority') != 'symbolic' or cp.get('evidence') != 'design-intent':
        errs.append('construction-grid must be authority=symbolic evidence=design-intent')

    # --- symbolic absent from physical generators ---
    for script in PHYSICAL_SCRIPTS:
        text = script.read_text(encoding='utf-8')
        for name in SYMBOLIC_NAMES:
            if name in text or 'construction-grid.geojson' in text:
                errs.append(f'{script.name} references symbolic layer ({name})')
        if "authority': 'symbolic'" in text or 'authority": "symbolic"' in text:
            # allow comments? fail if loading construction
            if 'construction' in text.lower() and 'symbolic' in text.lower():
                errs.append(f'{script.name} may mix symbolic into physical')
    print('symbolic isolation: surfaces/water/defensible do not reference construction-grid')

    return errs


def self_test() -> list[str]:
    errs: list[str] = []
    guides = json.loads(GUIDES.read_text(encoding='utf-8'))
    grid = json.loads(GRID.read_text(encoding='utf-8'))

    # 1) move a survey call
    bad = copy.deepcopy(guides)
    for f in bad['features']:
        if f['properties'].get('kind') == 'survey_call':
            coords = f['geometry']['coordinates']
            f['geometry']['coordinates'] = [
                [c[0] + 0.001, c[1] + 0.001] for c in coords
            ]
            break
    GUIDES.write_text(json.dumps(bad) + '\n', encoding='utf-8')
    try:
        found = run_checks()
        if not any('survey_call' in e for e in found):
            errs.append('self-test: survey displacement not caught')
        else:
            print('self-test: survey displacement caught')
    finally:
        GUIDES.write_text(json.dumps(guides, indent=2) + '\n', encoding='utf-8')

    # 2) break grid roundtrip
    badg = copy.deepcopy(grid)
    badg['worked_example']['roundtrip_index'] = [99.0, 99.0]
    GRID.write_text(json.dumps(badg) + '\n', encoding='utf-8')
    try:
        found = run_checks()
        if not any('roundtrip' in e for e in found):
            errs.append('self-test: grid roundtrip fault not caught')
        else:
            print('self-test: grid roundtrip fault caught')
    finally:
        GRID.write_text(json.dumps(grid, indent=2) + '\n', encoding='utf-8')

    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        errs = self_test()
    else:
        errs = run_checks()
    if errs:
        print('FAIL check-guides:')
        for e in errs[:40]:
            print(' ', e)
        raise SystemExit(1)
    print('OK check-guides')


if __name__ == '__main__':
    main()
