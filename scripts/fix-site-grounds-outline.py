"""
C23.1 — replace site-grounds AABB vegetation envelope with floors∪ + 3 m.

The models.json footprint was a 4-corner axis-aligned box: walk-floor AABB padded
by 3 m (~35,332 m²), which swallows empty air and ~10,124 m² outside the survey.
True path geometry is ~1,900 m² of floors; the honest clearing envelope is the
union of those floors buffered by 3 m.

    python scripts/fix-site-grounds-outline.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from terrain import en_to_lnglat, lnglat_to_en  # noqa: E402

import importlib.util

spec = importlib.util.spec_from_file_location('cp', ROOT / 'scripts' / 'check-positions.py')
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

PAD_M = 3.0
SIMPLIFY_M = 0.5


def floors_union_en(doc, origin_en, rot_deg: float) -> Polygon:
    extras = cp.walk_extras(doc)
    floors = (extras.get('walk') or {}).get('floors') or []
    ox, oy = origin_en
    polys = []
    for fl in floors:
        ring = fl.get('ring') or []
        if len(ring) < 3:
            continue
        pts = []
        for x, z in ring:
            xr, zr = cp.rotate_xz(float(x), float(z), rot_deg)
            pts.append((ox + xr, oy + (-zr)))
        try:
            p = Polygon(pts)
            if p.is_valid and p.area > 0.05:
                polys.append(p)
        except Exception:
            continue
    if not polys:
        raise SystemExit('site-grounds: no walk floors in GLB extras')
    u = unary_union(polys)
    return u if u.geom_type == 'Polygon' else max(u.geoms, key=lambda g: g.area)


def ring_ll(poly: Polygon) -> list[list[float]]:
    coords = list(poly.exterior.coords)
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    return [[float(en_to_lnglat(e, n)[0]), float(en_to_lnglat(e, n)[1])] for e, n in coords]


def main():
    man_path = ROOT / 'models.json'
    man = json.loads(man_path.read_text(encoding='utf-8'))
    sg = next(m for m in man['models'] if m['id'] == 'site-grounds')
    old = Polygon([lnglat_to_en(a, b) for a, b in sg['footprint']])
    origin_en = lnglat_to_en(*sg['origin'])
    ox, oy = origin_en
    doc = cp.read_glb(ROOT / 'models' / 'site-grounds.glb')
    # Same construction check-positions will compare against (local then place).
    local = cp.glb_plan_outline_en(doc, float(sg.get('rotationDeg') or 0), model_id='site-grounds')
    if local == 'envelope' or not local:
        raise SystemExit('site-grounds: could not derive floors∪+3m outline from GLB')
    envelope = Polygon([(ox + e, oy + n) for e, n in local])
    if not envelope.is_valid:
        envelope = envelope.buffer(0)

    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    parcel = Polygon([
        lnglat_to_en(x, y)
        for x, y in shape(survey['features'][0]['geometry']).exterior.coords
    ])
    outside = float(envelope.difference(parcel).area)
    crosses = outside > 1.0

    sg['footprint'] = [
        [float(en_to_lnglat(ox + e, oy + n)[0]), float(en_to_lnglat(ox + e, oy + n)[1])]
        for e, n in local
    ]
    # area from the EN polygon we will re-read (after ll round-trip)
    written = Polygon([lnglat_to_en(a, b) for a, b in sg['footprint']])
    sg['area_m2'] = round(written.area, 2)
    sg['outline_method'] = f'walk_floors_union_buffer_{PAD_M:g}m'
    sg['crosses_survey'] = bool(crosses)
    prior_note = (sg.get('note') or '').split(' C23.1:')[0].strip()
    sg['note'] = (
        f'{prior_note} C23.1: footprint was AABB+{PAD_M:g}m vegetation envelope '
        f'({old.area:.0f} m²); replaced with floors∪+{PAD_M:g}m '
        f'({written.area:.0f} m²).'
    ).strip()

    # stamp area_m2 on every model from its footprint
    for m in man['models']:
        ring = m.get('footprint') or []
        if len(ring) < 3:
            continue
        poly = Polygon([lnglat_to_en(a, b) for a, b in ring])
        m['area_m2'] = round(poly.area, 2)
        out = float(poly.difference(parcel).area)
        if out > 1.0:
            m['crosses_survey'] = True
        elif m['id'] != 'site-grounds':
            m.pop('crosses_survey', None)

    man_path.write_text(json.dumps(man, indent=2) + '\n', encoding='utf-8')
    print(
        f'OK site-grounds outline: {old.area:.1f} -> {written.area:.1f} m² '
        f'(delta {written.area - old.area:.1f}); crosses_survey={crosses} '
        f'outside={outside:.1f} m²'
    )


if __name__ == '__main__':
    main()
