"""
C17.1 — build positions.csv / positions.geojson.

  One row per placed thing: every models.json model, named site features
  (well, ford, gate, road entry, pads), and survey corners.

  UTM: EPSG:32611 (WGS84 / UTM zone 11N).
  Pack EN: pack.json frame (C15.3 WGS84 constants).
  elev_m: scripts/terrain.py 1 m DEM at lng/lat.
  POB: NE corner — first vertex of the surveyed boundary (call 1 from).

    python scripts/build-positions.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

from shapely.geometry import Point, Polygon, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from creek import FORD_EN  # noqa: E402
from terrain import elevation_lnglat, en_to_lnglat, lnglat_to_en  # noqa: E402

OUT_CSV = ROOT / 'positions.csv'
OUT_GEO = ROOT / 'positions.geojson'
COLUMNS = [
    'id', 'kind', 'lng', 'lat', 'utm11_e', 'utm11_n', 'pack_x', 'pack_y',
    'elev_m', 'from_POB_m', 'bearing_from_POB_deg', 'footprint_m2',
    'inside_parcel', 'min_boundary_m', 'source',
]

# WGS84 ellipsoid (EPSG:32611 = WGS84 / UTM zone 11N)
_A = 6378137.0
_F = 1.0 / 298.257223563
_E2 = _F * (2.0 - _F)
_K0 = 0.9996
_ZONE = 11
_LON0 = math.radians(-183.0 + 6.0 * _ZONE)  # -117 deg


def wgs84_to_utm11(lng: float, lat: float) -> tuple[float, float]:
    """Forward projection to EPSG:32611 (metres)."""
    lat_r = math.radians(lat)
    lng_r = math.radians(lng)
    N = _A / math.sqrt(1.0 - _E2 * math.sin(lat_r) ** 2)
    T = math.tan(lat_r) ** 2
    C = (_E2 / (1.0 - _E2)) * math.cos(lat_r) ** 2
    A = (lng_r - _LON0) * math.cos(lat_r)
    e_p2 = _E2 / (1.0 - _E2)
    M = _A * (
        (1.0 - _E2 / 4.0 - 3.0 * _E2 ** 2 / 64.0 - 5.0 * _E2 ** 3 / 256.0) * lat_r
        - (3.0 * _E2 / 8.0 + 3.0 * _E2 ** 2 / 32.0 + 45.0 * _E2 ** 3 / 1024.0) * math.sin(2.0 * lat_r)
        + (15.0 * _E2 ** 2 / 256.0 + 45.0 * _E2 ** 3 / 1024.0) * math.sin(4.0 * lat_r)
        - (35.0 * _E2 ** 3 / 3072.0) * math.sin(6.0 * lat_r)
    )
    e = _K0 * N * (
        A + (1.0 - T + C) * A ** 3 / 6.0
        + (5.0 - 18.0 * T + T ** 2 + 72.0 * C - 58.0 * e_p2) * A ** 5 / 120.0
    ) + 500000.0
    n = _K0 * (
        M + N * math.tan(lat_r) * (
            A ** 2 / 2.0
            + (5.0 - T + 9.0 * C + 4.0 * C ** 2) * A ** 4 / 24.0
            + (61.0 - 58.0 * T + T ** 2 + 600.0 * C - 330.0 * e_p2) * A ** 6 / 720.0
        )
    )
    return e, n


def open_ll(coords):
    if len(coords) >= 2 and coords[0] == coords[-1]:
        return coords[:-1]
    return list(coords)


def ll_ring_to_en(ring_ll):
    return [lnglat_to_en(float(lng), float(lat)) for lng, lat in open_ll(ring_ll)]


def load_parcel_and_pob():
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    boundary = next(f for f in survey['features'] if f['properties'].get('layer') == 'boundary')
    parcel = shape(boundary['geometry'])
    ring = boundary['geometry']['coordinates'][0]
    corners_ll = open_ll(ring)
    # POB = NE corner = first vertex (call 1 from: NE corner found iron pipe)
    pob_ll = (float(corners_ll[0][0]), float(corners_ll[0][1]))
    pob_en = lnglat_to_en(*pob_ll)
    easements = [
        shape(f['geometry'])
        for f in survey['features']
        if f['properties'].get('layer') == 'easement'
    ]
    return survey, parcel, corners_ll, pob_ll, pob_en, easements


def min_boundary_signed(geom, parcel: Polygon) -> float:
    """Nearest distance footprint/point -> surveyed boundary; negative if crosses outside."""
    b_line = parcel.boundary
    if geom.is_empty:
        return 0.0
    if geom.geom_type == 'Point':
        d = geom.distance(b_line)
        return d if parcel.covers(geom) or parcel.contains(geom) else -geom.distance(parcel)
    # Polygon (or Multi)
    if parcel.contains(geom) or parcel.covers(geom):
        return float(geom.distance(b_line))
    outside = geom.difference(parcel)
    if outside.is_empty:
        return float(geom.distance(b_line))
    # penetration: how far outside parts sit from the parcel
    if outside.geom_type == 'Polygon':
        parts = [outside]
    else:
        parts = list(outside.geoms)
    worst = 0.0
    for part in parts:
        for c in part.exterior.coords:
            worst = max(worst, Point(c).distance(parcel))
    return -worst if worst > 0 else -1e-3


def bearing_from_pob(e: float, n: float, pob_en) -> float:
    de, dn = e - pob_en[0], n - pob_en[1]
    # azimuth degrees clockwise from north
    az = math.degrees(math.atan2(de, dn)) % 360.0
    return az


def row_for(
    rid: str,
    kind: str,
    lng: float,
    lat: float,
    footprint_en: list[tuple[float, float]] | None,
    source: str,
    parcel: Polygon,
    pob_en,
):
    pack_x, pack_y = lnglat_to_en(lng, lat)
    utm_e, utm_n = wgs84_to_utm11(lng, lat)
    elev = elevation_lnglat(lng, lat)
    from_pob = math.hypot(pack_x - pob_en[0], pack_y - pob_en[1])
    bearing = bearing_from_pob(pack_x, pack_y, pob_en)

    if footprint_en and len(footprint_en) >= 3:
        poly = Polygon(footprint_en)
        if not poly.is_valid:
            poly = poly.buffer(0)
        area = float(poly.area)
        inside = parcel.contains(poly) or parcel.covers(poly)
        # use EN polygon for boundary distance (parcel is lng/lat — convert)
        # Parcel is geographic; convert footprint to lng/lat polygon for overlays
        fp_ll = [en_to_lnglat(e, n) for e, n in footprint_en]
        poly_ll = Polygon(fp_ll)
        if not poly_ll.is_valid:
            poly_ll = poly_ll.buffer(0)
        # Work in pack EN for metric distance to boundary
        parcel_en = Polygon([lnglat_to_en(x, y) for x, y in open_ll(list(parcel.exterior.coords))])
        if not parcel_en.is_valid:
            parcel_en = parcel_en.buffer(0)
        min_b = min_boundary_signed(poly, parcel_en)
        inside = parcel_en.contains(poly) or parcel_en.covers(poly)
    else:
        area = 0.0
        pt = Point(pack_x, pack_y)
        parcel_en = Polygon([lnglat_to_en(x, y) for x, y in open_ll(list(parcel.exterior.coords))])
        if not parcel_en.is_valid:
            parcel_en = parcel_en.buffer(0)
        inside = parcel_en.contains(pt) or parcel_en.covers(pt) or parcel_en.touches(pt)
        min_b = min_boundary_signed(pt, parcel_en)
        poly_ll = None

    return {
        'id': rid,
        'kind': kind,
        'lng': round(lng, 7),
        'lat': round(lat, 7),
        'utm11_e': round(utm_e, 3),
        'utm11_n': round(utm_n, 3),
        'pack_x': round(pack_x, 3),
        'pack_y': round(pack_y, 3),
        'elev_m': round(elev, 3),
        'from_POB_m': round(from_pob, 3),
        'bearing_from_POB_deg': round(bearing, 3),
        'footprint_m2': round(area, 2),
        'inside_parcel': bool(inside),
        'min_boundary_m': round(min_b, 3),
        'source': source,
        '_footprint_en': footprint_en,
        '_poly_ll': poly_ll,
    }


def collect_models(parcel, pob_en):
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    rows = []
    for m in man['models']:
        lng, lat = float(m['origin'][0]), float(m['origin'][1])
        fp = m.get('footprint')
        fp_en = ll_ring_to_en(fp) if fp else None
        # authority proposal -> derived; owner notes stay owner plan when marked
        auth = (m.get('authority') or 'proposal').lower()
        source = 'owner plan' if auth in ('owner', 'owner plan') else 'derived'
        rows.append(row_for(
            m['id'], 'model', lng, lat, fp_en, source, parcel, pob_en,
        ))
    return rows


def collect_corners(corners_ll, parcel, pob_en):
    rows = []
    for i, (lng, lat) in enumerate(corners_ll):
        rid = 'POB' if i == 0 else f'corner-{i + 1}'
        kind = 'survey_corner'
        rows.append(row_for(
            rid, kind, float(lng), float(lat), None, 'survey', parcel, pob_en,
        ))
    return rows


def rect_en_fp(e0, n0, e1, n1):
    return [(e0, n0), (e1, n0), (e1, n1), (e0, n1)]


def collect_features(parcel, pob_en):
    """Named site features from creek / site-grounds / infrastructure / edits."""
    rows = []
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))

    # --- ford (creek origin) ---
    flng, flat = en_to_lnglat(*FORD_EN)
    # small ford pad ~5x3 m for footprint (crossing stones)
    ford_fp = rect_en_fp(FORD_EN[0] - 2.5, FORD_EN[1] - 1.5, FORD_EN[0] + 2.5, FORD_EN[1] + 1.5)
    rows.append(row_for('ford', 'ford', flng, flat, ford_fp, 'derived', parcel, pob_en))

    # --- well (infrastructure local EN relative to model origin) ---
    infra = next(m for m in man['models'] if m['id'] == 'infrastructure')
    o_lng, o_lat = float(infra['origin'][0]), float(infra['origin'][1])
    o_e, o_n = lnglat_to_en(o_lng, o_lat)
    well_e, well_n = o_e + (-5.5), o_n + 3.5
    wlng, wlat = en_to_lnglat(well_e, well_n)
    well_fp = rect_en_fp(well_e - 0.8, well_n - 0.8, well_e + 0.8, well_n + 0.8)
    rows.append(row_for('well', 'well', wlng, wlat, well_fp, 'derived', parcel, pob_en))

    # --- road entry (drive start on easement) ---
    re_e, re_n = 155.0, 223.0
    rlng, rlat = en_to_lnglat(re_e, re_n)
    rows.append(row_for(
        'road-entry', 'road_entry', rlng, rlat,
        rect_en_fp(re_e - 2.0, re_n - 2.0, re_e + 2.0, re_n + 2.0),
        'derived', parcel, pob_en,
    ))

    # --- gate / gate parking (site-grounds) ---
    barn = next(m for m in man['models'] if m['id'] == 'the-barn')
    be, bn = lnglat_to_en(float(barn['origin'][0]), float(barn['origin'][1]))
    # gate parking pad: be-8..be+8, bn-14..bn-4 — centre is the gate feature
    g_e0, g_n0, g_e1, g_n1 = be - 8.0, bn - 14.0, be + 8.0, bn - 4.0
    g_cx, g_cy = (g_e0 + g_e1) / 2.0, (g_n0 + g_n1) / 2.0
    glng, glat = en_to_lnglat(g_cx, g_cy)
    rows.append(row_for(
        'gate', 'gate', glng, glat,
        rect_en_fp(g_e0, g_n0, g_e1, g_n1),
        'derived', parcel, pob_en,
    ))
    rows.append(row_for(
        'pad-gate-parking', 'pad', glng, glat,
        rect_en_fp(g_e0, g_n0, g_e1, g_n1),
        'derived', parcel, pob_en,
    ))

    # --- oak court parking pad ---
    court_e, court_n = lnglat_to_en(-119.155425, 34.432952)
    oc_fp = rect_en_fp(court_e - 10.0, court_n - 4.0, court_e + 10.0, court_n + 4.0)
    oc_lng, oc_lat = en_to_lnglat(court_e, court_n)
    rows.append(row_for(
        'pad-oak-court-parking', 'pad', oc_lng, oc_lat, oc_fp, 'derived', parcel, pob_en,
    ))

    # --- arrival pad at spawn ---
    se, sn = lnglat_to_en(float(pack['spawn']['lng']), float(pack['spawn']['lat']))
    arr_fp = rect_en_fp(se - 3.0, sn - 3.0, se + 3.0, sn + 3.0)
    rows.append(row_for(
        'pad-arrival', 'pad', float(pack['spawn']['lng']), float(pack['spawn']['lat']),
        arr_fp, 'derived', parcel, pob_en,
    ))

    # --- owner edits: oak-leaf-court pad, oak-lounge ---
    edits = json.loads((ROOT / 'edits.geojson').read_text(encoding='utf-8'))
    for f in edits['features']:
        p = f.get('properties') or {}
        eid = p.get('id') or ''
        if eid == 'oak-leaf-court' and f['geometry']['type'] == 'Polygon':
            ring = f['geometry']['coordinates'][0]
            fp_en = ll_ring_to_en(ring)
            cx = sum(e for e, _ in fp_en) / len(fp_en)
            cy = sum(n for _, n in fp_en) / len(fp_en)
            lng, lat = en_to_lnglat(cx, cy)
            rows.append(row_for(
                'pad-oak-leaf-court', 'pad', lng, lat, fp_en, 'owner plan', parcel, pob_en,
            ))
        elif eid == 'oak-lounge' and f['geometry']['type'] == 'Point':
            lng, lat = f['geometry']['coordinates'][:2]
            rows.append(row_for(
                'oak-lounge', 'feature', float(lng), float(lat), None, 'owner plan', parcel, pob_en,
            ))

    return rows


def write_outputs(rows):
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            out = {k: r[k] for k in COLUMNS}
            out['inside_parcel'] = 'true' if r['inside_parcel'] else 'false'
            w.writerow(out)

    features = []
    for r in rows:
        props = {k: r[k] for k in COLUMNS}
        geom = {'type': 'Point', 'coordinates': [r['lng'], r['lat']]}
        features.append({'type': 'Feature', 'properties': props, 'geometry': geom})
        fp_en = r.get('_footprint_en')
        if fp_en and len(fp_en) >= 3:
            ll = [list(en_to_lnglat(e, n)) for e, n in fp_en]
            if ll[0] != ll[-1]:
                ll.append(ll[0])
            features.append({
                'type': 'Feature',
                'properties': {
                    'id': r['id'] + '-footprint',
                    'kind': 'footprint',
                    'parent': r['id'],
                    'footprint_m2': r['footprint_m2'],
                    'source': r['source'],
                },
                'geometry': {'type': 'Polygon', 'coordinates': [ll]},
            })

    doc = {
        'type': 'FeatureCollection',
        'name': 'positions',
        'crs': {'type': 'name', 'properties': {'name': 'EPSG:4326'}},
        'utm': 'EPSG:32611 (WGS84 UTM 11N) for utm11_e / utm11_n columns',
        'frame': 'pack.json frame (C15.3 WGS84 constants) for pack_x / pack_y',
        'features': features,
    }
    OUT_GEO.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')


def main():
    _, parcel, corners_ll, pob_ll, pob_en, _ = load_parcel_and_pob()
    print(f'POB NE corner lng/lat {pob_ll[0]:.7f}, {pob_ll[1]:.7f}')
    print(f'POB pack EN ({pob_en[0]:.3f}, {pob_en[1]:.3f})')
    print('UTM CRS: EPSG:32611 (WGS84 UTM zone 11N)')

    rows = []
    rows.extend(collect_models(parcel, pob_en))
    rows.extend(collect_corners(corners_ll, parcel, pob_en))
    rows.extend(collect_features(parcel, pob_en))

    # stable order: models, corners, features
    write_outputs(rows)
    n_model = sum(1 for r in rows if r['kind'] == 'model')
    n_corner = sum(1 for r in rows if r['kind'] == 'survey_corner')
    n_feat = len(rows) - n_model - n_corner
    print(f'wrote {OUT_CSV.name}: {len(rows)} rows '
          f'({n_model} models, {n_corner} corners, {n_feat} features)')
    print(f'wrote {OUT_GEO.name}')


if __name__ == '__main__':
    main()
