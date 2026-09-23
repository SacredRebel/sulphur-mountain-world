"""
C27 — snap guides, pack-frame grid, and a symbolic construction layer.

    python scripts/build-guides.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union
from skimage.measure import find_contours

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR, parcel_window  # noqa: E402
from terrain import en_to_lnglat, lnglat_to_en  # noqa: E402

OUT_GUIDES = ROOT / 'guides.geojson'
OUT_GRID = ROOT / 'grid.json'
OUT_CONSTRUCTION = ROOT / 'construction-grid.geojson'

STRUCTURE_SKIP = {'site-grounds', 'creek'}
BUILDING_EXTEND_M = 5.0
CONTOUR_INTERVAL_M = 2.0
CONTOUR_TOL_M = 1.5  # DEM follow tolerance published for the check
GRID_SPACING_M = 10.0
CONSTRUCTION_SPACING_M = 30.0 * 0.3048  # 30 survey feet
FT_TO_M = 0.3048


def pack():
    return json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))


def aoi_poly():
    bb = pack()['aoi']['bbox']
    # lnglat box → EN polygon
    corners = [
        lnglat_to_en(bb[0], bb[1]),
        lnglat_to_en(bb[2], bb[1]),
        lnglat_to_en(bb[2], bb[3]),
        lnglat_to_en(bb[0], bb[3]),
    ]
    return Polygon(corners)


def clip_to_aoi(geom, aoi):
    if geom is None or geom.is_empty:
        return None
    g = geom.intersection(aoi)
    if g.is_empty:
        return None
    return g


def feat(kind, source, priority, geom, extra=None, authority='derived', evidence='modelled'):
    if geom is None or geom.is_empty:
        return None
    props = {
        'kind': kind,
        'source': source,
        'priority': priority,
        'authority': authority,
        'evidence': evidence,
    }
    if extra:
        props.update(extra)
    return {
        'type': 'Feature',
        'properties': props,
        'geometry': mapping(geom),
    }


def to_lnglat_geom(geom_en):
    """Map shapely EN geometry to lng/lat shapely geometry."""
    if geom_en.geom_type == 'Point':
        lng, lat = en_to_lnglat(geom_en.x, geom_en.y)
        return Point(lng, lat)
    if geom_en.geom_type == 'LineString':
        return LineString([en_to_lnglat(x, y) for x, y in geom_en.coords])
    if geom_en.geom_type == 'Polygon':
        exterior = [en_to_lnglat(x, y) for x, y in geom_en.exterior.coords]
        holes = [
            [en_to_lnglat(x, y) for x, y in ring.coords]
            for ring in geom_en.interiors
        ]
        return Polygon(exterior, holes)
    if geom_en.geom_type.startswith('Multi') or geom_en.geom_type == 'GeometryCollection':
        parts = []
        for g in getattr(geom_en, 'geoms', []):
            parts.append(to_lnglat_geom(g))
        from shapely.geometry import GeometryCollection
        return unary_union(parts) if parts else GeometryCollection()
    return geom_en


def survey_guides(aoi_en):
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    out = []
    for f in survey['features']:
        p = f.get('properties') or {}
        layer = p.get('layer')
        g = shape(f['geometry'])
        # keep in lnglat for 0.1 ft check against source; clip via EN
        coords_en = None
        if g.geom_type == 'Point':
            e, n = lnglat_to_en(g.x, g.y)
            ge = Point(e, n)
        elif g.geom_type == 'LineString':
            ge = LineString([lnglat_to_en(x, y) for x, y in g.coords])
        elif g.geom_type == 'Polygon':
            ge = Polygon([lnglat_to_en(x, y) for x, y in g.exterior.coords])
        else:
            continue
        ge = clip_to_aoi(ge, aoi_en)
        if ge is None:
            continue
        gll = to_lnglat_geom(ge)
        if layer == 'call':
            out.append(feat(
                'survey_call', f'survey.geojson#call-{p.get("n")}', 100, gll,
                {'call_n': p.get('n'), 'bearing': p.get('bearing'),
                 'distance_ft': p.get('distance_ft')},
                authority='survey', evidence='measured',
            ))
        elif layer == 'monument':
            out.append(feat(
                'monument', f'survey.geojson#monument:{p.get("label")}', 100, gll,
                {'label': p.get('label')},
                authority='survey', evidence='measured',
            ))
        elif layer == 'easement':
            # edges only
            if ge.geom_type == 'Polygon':
                edge = LineString(list(ge.exterior.coords))
                edge = clip_to_aoi(edge, aoi_en)
                if edge is not None:
                    out.append(feat(
                        'easement_edge',
                        f'survey.geojson#easement-part-{p.get("part")}',
                        90, to_lnglat_geom(edge),
                        {'name': p.get('name'), 'part': p.get('part')},
                        authority='survey', evidence='measured',
                    ))
    return [f for f in out if f]


def building_edge_guides(aoi_en):
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    out = []
    for m in man['models']:
        if m['id'] in STRUCTURE_SKIP:
            continue
        fp = m.get('footprint')
        if not fp or len(fp) < 3:
            continue
        ring = [lnglat_to_en(a, b) for a, b in fp]
        if ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        poly = Polygon(ring)
        # extend each edge beyond endpoints
        coords = list(poly.exterior.coords)
        for i in range(len(coords) - 1):
            e0, n0 = coords[i]
            e1, n1 = coords[i + 1]
            dx, dy = e1 - e0, n1 - n0
            L = math.hypot(dx, dy)
            if L < 1e-6:
                continue
            ux, uy = dx / L, dy / L
            ee0 = e0 - ux * BUILDING_EXTEND_M
            nn0 = n0 - uy * BUILDING_EXTEND_M
            ee1 = e1 + ux * BUILDING_EXTEND_M
            nn1 = n1 + uy * BUILDING_EXTEND_M
            line = clip_to_aoi(LineString([(ee0, nn0), (ee1, nn1)]), aoi_en)
            if line is None:
                continue
            out.append(feat(
                'building_edge',
                f'models.json#{m["id"]}',
                70, to_lnglat_geom(line),
                {
                    'structure_id': m['id'],
                    'extend_m': BUILDING_EXTEND_M,
                },
            ))
    return [f for f in out if f]


def keyline_guides(aoi_en):
    doc = json.loads((ROOT / 'keylines.geojson').read_text(encoding='utf-8'))
    out = []
    for i, f in enumerate(doc['features']):
        p = f.get('properties') or {}
        if p.get('kind') not in ('keyline', 'swale_line'):
            continue
        g = shape(f['geometry'])
        if g.geom_type != 'LineString':
            continue
        ge = LineString([lnglat_to_en(x, y) for x, y in g.coords])
        ge = clip_to_aoi(ge, aoi_en)
        if ge is None:
            continue
        out.append(feat(
            'keyline', f'keylines.geojson#{i}', 60, to_lnglat_geom(ge),
            {'keyline_kind': p.get('kind')},
        ))
    return [f for f in out if f]


def contour_guides(aoi_en):
    """Contour-parallel lines on buildable ground at CONTOUR_INTERVAL_M."""
    dem = np.load(GRID_DIR / 'dem_1m.npz')
    es, ns, Z = dem['es'], dem['ns'], dem['Z'].astype(float)
    # buildable mask from buildable.geojson bands
    bdoc = json.loads((ROOT / 'buildable.geojson').read_text(encoding='utf-8'))
    polys = []
    for f in bdoc['features']:
        band = (f.get('properties') or {}).get('band')
        if band not in ('best', 'good', 'workable'):
            continue
        g = shape(f['geometry'])
        if g.geom_type == 'Polygon':
            polys.append(Polygon([lnglat_to_en(x, y) for x, y in g.exterior.coords]))
        elif g.geom_type == 'MultiPolygon':
            for p in g.geoms:
                polys.append(Polygon([lnglat_to_en(x, y) for x, y in p.exterior.coords]))
    if not polys:
        return [], CONTOUR_TOL_M
    buildable = unary_union(polys).intersection(aoi_en)
    zmin = float(np.nanmin(Z))
    zmax = float(np.nanmax(Z))
    levels = np.arange(
        math.ceil(zmin / CONTOUR_INTERVAL_M) * CONTOUR_INTERVAL_M,
        zmax, CONTOUR_INTERVAL_M,
    )
    out = []
    # find_contours expects row,col; Z[i,j] at ns[i], es[j]
    for level in levels:
        try:
            contours = find_contours(Z, level)
        except Exception:
            continue
        for c in contours:
            # c[:,0]=row, c[:,1]=col
            coords = []
            for row, col in c:
                ri = int(round(row))
                ci = int(round(col))
                if ri < 0 or ci < 0 or ri >= len(ns) or ci >= len(es):
                    continue
                # bilinear-ish: use fractional
                r0 = min(max(int(row), 0), len(ns) - 2)
                c0 = min(max(int(col), 0), len(es) - 2)
                fr, fc = row - r0, col - c0
                n = ns[r0] * (1 - fr) + ns[min(r0 + 1, len(ns) - 1)] * fr
                e = es[c0] * (1 - fc) + es[min(c0 + 1, len(es) - 1)] * fc
                coords.append((float(e), float(n)))
            if len(coords) < 2:
                continue
            line = LineString(coords)
            clipped = clip_to_aoi(line.intersection(buildable), aoi_en)
            if clipped is None or clipped.is_empty:
                continue
            geoms = [clipped] if clipped.geom_type == 'LineString' else list(
                getattr(clipped, 'geoms', [])
            )
            for g in geoms:
                if g.geom_type != 'LineString' or g.length < 5.0:
                    continue
                out.append(feat(
                    'contour',
                    f'dem_1m@{level:.0f}m',
                    40, to_lnglat_geom(g),
                    {
                        'elevation_m': round(float(level), 1),
                        'interval_m': CONTOUR_INTERVAL_M,
                        'dem_tol_m': CONTOUR_TOL_M,
                    },
                ))
    return [f for f in out if f], CONTOUR_TOL_M


def grid_lines(origin_en, spacing, rotation_deg, aoi_en, kind, source, priority,
               authority='derived', evidence='modelled', n_lines=40):
    """Axis-aligned lines in a rotated frame through origin, clipped to AOI."""
    ox, oy = origin_en
    rad = math.radians(rotation_deg)
    # unit vectors: along-grid-x (eastward in rotated frame), along-grid-y
    # rotation_deg is clockwise from true north for the "north" axis of the grid
    # Grid north direction in EN: (sin(az), cos(az)); grid east: (cos(az), -sin(az))?
    # True-north grid: rotation 0 → lines of constant E and constant N.
    # Solar grid: rotation = sunrise az → one family parallel to sun ray.
    ux, uy = math.sin(rad), math.cos(rad)       # "north" axis of grid
    vx, vy = math.cos(rad), -math.sin(rad)      # "east" axis of grid
    out = []
    half = n_lines // 2
    span = spacing * half * 1.5
    for i in range(-half, half + 1):
        # line parallel to north-axis through point origin + i*spacing*east
        cx = ox + i * spacing * vx
        cy = oy + i * spacing * vy
        line = LineString([
            (cx - ux * span, cy - uy * span),
            (cx + ux * span, cy + uy * span),
        ])
        line = clip_to_aoi(line, aoi_en)
        if line is not None and not line.is_empty:
            geoms = [line] if line.geom_type == 'LineString' else list(line.geoms)
            for g in geoms:
                if g.length < 1:
                    continue
                out.append(feat(
                    kind, source, priority, to_lnglat_geom(g),
                    {'index': i, 'axis': 'N', 'spacing_m': spacing,
                     'rotation_deg': rotation_deg},
                    authority=authority, evidence=evidence,
                ))
        # line parallel to east-axis
        cx = ox + i * spacing * ux
        cy = oy + i * spacing * uy
        line = LineString([
            (cx - vx * span, cy - vy * span),
            (cx + vx * span, cy + vy * span),
        ])
        line = clip_to_aoi(line, aoi_en)
        if line is not None and not line.is_empty:
            geoms = [line] if line.geom_type == 'LineString' else list(line.geoms)
            for g in geoms:
                if g.length < 1:
                    continue
                out.append(feat(
                    kind, source, priority, to_lnglat_geom(g),
                    {'index': i, 'axis': 'E', 'spacing_m': spacing,
                     'rotation_deg': rotation_deg},
                    authority=authority, evidence=evidence,
                ))
    return [f for f in out if f]


def june_sunrise_az():
    sky = json.loads((ROOT / 'sky-events.json').read_text(encoding='utf-8'))
    for o in sky['observers']:
        if o['id'] == 'gathering_best':
            return float(o['events']['june_solstice']['sunrise']['flat']['azimuth_deg'])
    return 60.53


def build_grid_json(origin_en, spacing, rotation_deg):
    fr = pack()['frame']
    ox, oy = origin_en
    # worked example: index (3, -2)
    ix, iy = 3, -2
    rad = math.radians(rotation_deg)
    ux, uy = math.sin(rad), math.cos(rad)
    vx, vy = math.cos(rad), -math.sin(rad)
    e = ox + ix * spacing * vx + iy * spacing * ux
    n = oy + ix * spacing * vy + iy * spacing * uy
    lng, lat = en_to_lnglat(e, n)

    def index_to_lnglat(i, j):
        ee = ox + i * spacing * vx + j * spacing * ux
        nn = oy + i * spacing * vy + j * spacing * uy
        return list(en_to_lnglat(ee, nn))

    def lnglat_to_index(lng_, lat_):
        ee, nn = lnglat_to_en(lng_, lat_)
        de, dn = ee - ox, nn - oy
        det = vx * uy - ux * vy
        i = (de * uy - ux * dn) / det / spacing
        j = (vx * dn - de * vy) / det / spacing
        return [i, j]

    back = lnglat_to_index(lng, lat)
    return {
        'authority': 'derived',
        'evidence': 'modelled',
        'generator': 'scripts/build-guides.py',
        'frame': {
            'origin_lng': fr['origin_lng'],
            'origin_lat': fr['origin_lat'],
            'metres_per_deg_lng': fr['metres_per_deg_lng'],
            'metres_per_deg_lat': fr['metres_per_deg_lat'],
            'axes': 'x east, y north (pack metres)',
        },
        'grid': {
            'origin_east_m': round(ox, 4),
            'origin_north_m': round(oy, 4),
            'origin_lnglat': list(en_to_lnglat(ox, oy)),
            'spacing_m': spacing,
            'rotation_deg_from_true_north': rotation_deg,
            'rotation_note': (
                '0 = true-north grid (axes aligned to pack E/N). '
                'Non-zero rotates grid-north clockwise from true north.'
            ),
            'index_axes': (
                'index i along grid-east, index j along grid-north; '
                'EN = origin + i*spacing*east_hat + j*spacing*north_hat'
            ),
        },
        'formulas': {
            'index_to_lnglat': (
                'east_hat=(cos θ, −sin θ), north_hat=(sin θ, cos θ) with θ=rotation_deg; '
                'E = E0 + i·s·east_e + j·s·north_e; N similar; '
                'lng = origin_lng + E/metres_per_deg_lng; lat = origin_lat + N/metres_per_deg_lat'
            ),
            'lnglat_to_index': 'invert the linear map above (exact for equirectangular frame)',
        },
        'worked_example': {
            'index': [ix, iy],
            'lnglat': [round(lng, 8), round(lat, 8)],
            'east_m': round(e, 4),
            'north_m': round(n, 4),
            'roundtrip_index': [round(back[0], 12), round(back[1], 12)],
            'note': 'roundtrip_index must equal index within float noise',
        },
    }


def construction_grid_layer(origin_en, solar_az, aoi_en):
    """Symbolic geometric construction: 30 ft module, solar-aligned, through origin."""
    lines = grid_lines(
        origin_en, CONSTRUCTION_SPACING_M, solar_az, aoi_en,
        kind='construction',
        source='construction-grid:30ft-solar',
        priority=20,
        authority='symbolic',
        evidence='design-intent',
        n_lines=24,
    )
    doc = {
        'type': 'FeatureCollection',
        'name': 'construction-grid',
        'properties': {
            'authority': 'symbolic',
            'evidence': 'design-intent',
            'generator': 'scripts/build-guides.py',
            'construction_method': (
                f'Square module of {CONSTRUCTION_SPACING_M:.4f} m (30 US survey feet) '
                f'through origin EN{origin_en}, rotated so grid-north equals the '
                f'{YEAR_NOTE} June flat-horizon sunrise azimuth {solar_az:.2f}° '
                '(clockwise from true north). Reproducible from origin + spacing + azimuth alone. '
                'No claim about measured ground.'
            ),
            'spacing_m': CONSTRUCTION_SPACING_M,
            'rotation_deg_from_true_north': solar_az,
            'origin_en_m': [round(origin_en[0], 3), round(origin_en[1], 3)],
        },
        'features': lines,
    }
    return doc


YEAR_NOTE = '2026'


def main():
    aoi_en = aoi_poly()
    # origin: parcel centroid (horizon viewpoint)
    hz = json.loads((ROOT / 'horizon.json').read_text(encoding='utf-8'))
    pc = hz['viewpoints']['parcel_centroid']
    origin_en = lnglat_to_en(pc['lng'], pc['lat'])
    solar_az = june_sunrise_az()

    feats = []
    feats.extend(survey_guides(aoi_en))
    feats.extend(building_edge_guides(aoi_en))
    feats.extend(keyline_guides(aoi_en))
    contours, contour_tol = contour_guides(aoi_en)
    feats.extend(contours)
    feats.extend(grid_lines(
        origin_en, GRID_SPACING_M, 0.0, aoi_en,
        'true_north_grid', 'grid.json#true_north', 50,
    ))
    feats.extend(grid_lines(
        origin_en, GRID_SPACING_M, solar_az, aoi_en,
        'solar_grid', 'grid.json#solar', 45,
    ))

    guides_doc = {
        'type': 'FeatureCollection',
        'name': 'guides',
        'properties': {
            'authority': 'derived',
            'evidence': 'modelled',
            'generator': 'scripts/build-guides.py',
            'building_extend_m': BUILDING_EXTEND_M,
            'contour_interval_m': CONTOUR_INTERVAL_M,
            'contour_dem_tol_m': contour_tol,
            'grid_spacing_m': GRID_SPACING_M,
            'grid_origin_lnglat': [pc['lng'], pc['lat']],
            'solar_rotation_deg': solar_az,
            'priority_note': '100=survey legal truth; lower = weaker snap preference',
        },
        'features': feats,
    }
    OUT_GUIDES.write_text(json.dumps(guides_doc, indent=2) + '\n', encoding='utf-8')

    grid_doc = build_grid_json(origin_en, GRID_SPACING_M, 0.0)
    grid_doc['solar_aligned'] = {
        'rotation_deg_from_true_north': solar_az,
        'spacing_m': GRID_SPACING_M,
        'note': 'Same origin and spacing as true-north grid; rotate by June flat sunrise az',
    }
    OUT_GRID.write_text(json.dumps(grid_doc, indent=2) + '\n', encoding='utf-8')

    const = construction_grid_layer(origin_en, solar_az, aoi_en)
    OUT_CONSTRUCTION.write_text(json.dumps(const, indent=2) + '\n', encoding='utf-8')

    print(
        f'wrote {OUT_GUIDES.name} features={len(feats)}; '
        f'{OUT_GRID.name}; {OUT_CONSTRUCTION.name} features={len(const["features"])}'
    )


if __name__ == '__main__':
    main()
