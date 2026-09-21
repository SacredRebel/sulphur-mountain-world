"""
C12 — Oak Leaf knoll site analysis (land description, not a house design).

  100 × 100 m window centred on [-119.15536, 34.4331]:
    · 0.5 m contours from the pack DEM
    · slope classes <15% / 15–25% / >25%
    · largest contiguous under-15% buildable envelope
    · every trees.csv canopy top in the window (drip-line = crown_radius)

  Writes:
    analysis/oak-leaf-knoll.geojson
    analysis/oak-leaf-knoll.png

    python scripts/oak-leaf-knoll.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
from terrain import elevation_en, en_to_lnglat, lnglat_to_en  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PACK = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
MX = float(PACK['frame']['metres_per_deg_lng'])
MY = float(PACK['frame']['metres_per_deg_lat'])

CENTER_LL = [-119.15536, 34.4331]
WINDOW_M = 100.0
STEP_M = 1.0  # match USGS 3DEP 1 m source resolution
CONTOUR_M = 0.5
SLOPE_EASY = 15.0
SLOPE_CARE = 25.0

OUT_GEO = ROOT / 'analysis' / 'oak-leaf-knoll.geojson'
OUT_PNG = ROOT / 'analysis' / 'oak-leaf-knoll.png'


def point_in_ring(lng: float, lat: float, ring) -> bool:
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def load_house_edit_poly():
    edits = json.loads((ROOT / 'edits.geojson').read_text(encoding='utf-8'))
    for f in edits['features']:
        if f['properties'].get('id') == 'trees-around-the-house':
            return f['geometry']['coordinates'][0]
    return None


def sample_dem(ce: float, cn: float):
    half = WINDOW_M / 2.0
    e0, e1 = ce - half, ce + half
    n0, n1 = cn - half, cn + half
    es = np.arange(e0, e1 + 1e-9, STEP_M)
    ns = np.arange(n0, n1 + 1e-9, STEP_M)
    Z = np.zeros((len(ns), len(es)), dtype=float)
    for i, n in enumerate(ns):
        for j, e in enumerate(es):
            Z[i, j] = elevation_en(float(e), float(n))
    return es, ns, Z, e0, n0, e1, n1


def slope_percent(Z: np.ndarray, step: float) -> np.ndarray:
    # ns increase with row index → north; gradient along axis 0 is dZ/dn
    dZ_dn, dZ_de = np.gradient(Z, step, step)
    return 100.0 * np.sqrt(dZ_de ** 2 + dZ_dn ** 2)


def mask_to_polygons(mask: np.ndarray, es: np.ndarray, ns: np.ndarray):
    """Trace exterior rings of True regions via contour at 0.5 on float mask."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    cs = ax.contour(es, ns, mask.astype(float), levels=[0.5])
    polys = []
    try:
        allsegs = cs.allsegs[0]
    except Exception:
        allsegs = []
    for seg in allsegs:
        if len(seg) < 4:
            continue
        ring = [[float(e), float(n)] for e, n in seg]
        if ring[0] != ring[-1]:
            ring.append(list(ring[0]))
        a = 0.0
        for i in range(len(ring) - 1):
            a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
        if abs(a) * 0.5 < 2.0:
            continue
        ll = [list(en_to_lnglat(e, n)) for e, n in ring]
        polys.append((abs(a) * 0.5, ll))
    plt.close(fig)
    polys.sort(key=lambda x: -x[0])
    return polys


def contours_geo(Z, es, ns, levels):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    cs = ax.contour(es, ns, Z, levels=levels)
    features = []
    # matplotlib ContourSet: levels and allsegs
    for li, level in enumerate(cs.levels):
        for seg in cs.allsegs[li]:
            if len(seg) < 2:
                continue
            coords = [list(en_to_lnglat(float(e), float(n))) for e, n in seg]
            features.append({
                'type': 'Feature',
                'properties': {
                    'kind': 'contour',
                    'elevation_m': round(float(level), 2),
                    'interval_m': CONTOUR_M,
                },
                'geometry': {'type': 'LineString', 'coordinates': coords},
            })
    plt.close(fig)
    return features


def largest_component(mask: np.ndarray):
    labeled, n = ndimage.label(mask)
    if n == 0:
        return np.zeros_like(mask, dtype=bool), 0.0
    sizes = ndimage.sum(mask, labeled, index=range(1, n + 1))
    best = int(np.argmax(sizes)) + 1
    out = labeled == best
    return out, float(sizes[best - 1]) * (STEP_M ** 2)


def load_oaks(e0, n0, e1, n1, house_poly):
    oaks = []
    with (ROOT / 'trees.csv').open(encoding='utf-8') as f:
        next(f)
        for line in f:
            parts = line.strip().split(',')
            if len(parts) < 5:
                continue
            e = int(parts[0]) / 10.0
            n = int(parts[1]) / 10.0
            if not (e0 <= e <= e1 and n0 <= n <= n1):
                continue
            h = int(parts[2]) / 10.0
            crown = int(parts[3]) / 10.0
            ground = int(parts[4]) / 10.0
            lng, lat = en_to_lnglat(e, n)
            removed = False
            if house_poly is not None:
                # edit removes tops within 12 m of house footprint
                if point_in_ring(lng, lat, house_poly):
                    removed = True
                else:
                    # also buffer check — edit says buffer_m 12 around footprint
                    # approximate: distance to polygon edges; simple centroid buffer insufficient
                    # Use point-in expanded: if within 12 m of any vertex or edge
                    removed = dist_to_ring_m(lng, lat, house_poly) <= 12.0
            oaks.append({
                'type': 'Feature',
                'properties': {
                    'kind': 'oak',
                    'height_m': round(h, 2),
                    'drip_line_radius_m': round(crown, 2),
                    'ground_m_lidar': round(ground, 2),
                    'east_m': round(e, 2),
                    'north_m': round(n, 2),
                    'removed_by_owner_edit': removed,
                    'note': 'crown_radius from trees.csv — drip-line protection zone',
                },
                'geometry': {'type': 'Point', 'coordinates': [round(lng, 7), round(lat, 7)]},
            })
    return oaks


def dist_to_ring_m(lng, lat, ring):
    e, n = lnglat_to_en(lng, lat)
    best = 1e9
    for i in range(len(ring) - 1):
        e0, n0 = lnglat_to_en(ring[i][0], ring[i][1])
        e1, n1 = lnglat_to_en(ring[i + 1][0], ring[i + 1][1])
        vx, vy = e1 - e0, n1 - n0
        wx, wy = e - e0, n - n0
        c1 = vx * wx + vy * wy
        if c1 <= 0:
            d = math.hypot(e - e0, n - n0)
        else:
            c2 = vx * vx + vy * vy
            if c2 <= c1:
                d = math.hypot(e - e1, n - n1)
            else:
                t = c1 / c2
                d = math.hypot(e - (e0 + t * vx), n - (n0 + t * vy))
        best = min(best, d)
    return best


def draw_plan(es, ns, Z, slope, easy_mask, build_mask, oaks, e0, n0, e1, n1, stats):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, FancyBboxPatch, Rectangle
    from matplotlib.lines import Line2D
    from matplotlib.colors import ListedColormap, BoundaryNorm

    fig, ax = plt.subplots(figsize=(10, 10), dpi=150)
    # north up: ns as y
    EE, NN = np.meshgrid(es, ns)
    # slope classes raster
    cls = np.zeros_like(slope, dtype=int)
    cls[slope < SLOPE_EASY] = 1
    cls[(slope >= SLOPE_EASY) & (slope < SLOPE_CARE)] = 2
    cls[slope >= SLOPE_CARE] = 3
    cmap = ListedColormap(['#ffffff', '#c8e6c9', '#fff9c4', '#ffcdd2'])
    ax.pcolormesh(EE, NN, cls, cmap=cmap, shading='nearest', vmin=0, vmax=3, zorder=1)

    # contours
    zmin, zmax = float(np.nanmin(Z)), float(np.nanmax(Z))
    levels = np.arange(math.floor(zmin / CONTOUR_M) * CONTOUR_M,
                       math.ceil(zmax / CONTOUR_M) * CONTOUR_M + CONTOUR_M * 0.5,
                       CONTOUR_M)
    cs = ax.contour(es, ns, Z, levels=levels, colors='#37474f', linewidths=0.45, zorder=3)
    ax.clabel(cs, inline=True, fontsize=6, fmt='%.1f')

    # buildable envelope outline
    ax.contour(es, ns, build_mask.astype(float), levels=[0.5],
               colors='#1b5e20', linewidths=2.0, zorder=4)

    # oaks — drip lines (skip removed for clarity but draw both styles)
    for o in oaks:
        e, n = o['properties']['east_m'], o['properties']['north_m']
        r = o['properties']['drip_line_radius_m']
        removed = o['properties']['removed_by_owner_edit']
        color = '#9e9e9e' if removed else '#2e7d32'
        ls = ':' if removed else '-'
        ax.add_patch(Circle((e, n), r, fill=False, edgecolor=color, linewidth=0.8,
                            linestyle=ls, zorder=5))
        ax.plot(e, n, 'o', color=color, markersize=2.2, zorder=6)

    # window frame + centre
    ax.add_patch(Rectangle((e0, n0), WINDOW_M, WINDOW_M, fill=False,
                           edgecolor='#212121', linewidth=1.2, zorder=7))
    ce, cn = (e0 + e1) / 2, (n0 + n1) / 2
    ax.plot(ce, cn, '+', color='#000', markersize=10, zorder=8)

    # north arrow
    ax.annotate('N', xy=(e1 - 6, n1 - 14), fontsize=14, fontweight='bold', ha='center')
    ax.annotate('', xy=(e1 - 6, n1 - 6), xytext=(e1 - 6, n1 - 18),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))

    # scale bar 20 m
    sb_x0, sb_y = e0 + 6, n0 + 5
    ax.plot([sb_x0, sb_x0 + 20], [sb_y, sb_y], color='black', lw=2.5, solid_capstyle='butt')
    ax.plot([sb_x0, sb_x0], [sb_y - 1, sb_y + 1], color='black', lw=1.5)
    ax.plot([sb_x0 + 20, sb_x0 + 20], [sb_y - 1, sb_y + 1], color='black', lw=1.5)
    ax.text(sb_x0 + 10, sb_y + 2.5, '20 m', ha='center', va='bottom', fontsize=9)

    ax.set_aspect('equal')
    ax.set_xlim(e0, e1)
    ax.set_ylim(n0, n1)
    ax.set_xlabel('east (m, pack frame)')
    ax.set_ylabel('north (m, pack frame)')
    ax.set_title(
        'Oak Leaf knoll — site analysis (C12)\n'
        f'centre {CENTER_LL[0]}, {CENTER_LL[1]}  ·  100×100 m  ·  contours {CONTOUR_M} m',
        fontsize=11,
    )

    legend = [
        Line2D([0], [0], color='#c8e6c9', lw=8, label='slope < 15% (easy)'),
        Line2D([0], [0], color='#fff9c4', lw=8, label='slope 15–25% (care)'),
        Line2D([0], [0], color='#ffcdd2', lw=8, label='slope > 25% (avoid)'),
        Line2D([0], [0], color='#1b5e20', lw=2, label='buildable envelope (<15%)'),
        Line2D([0], [0], color='#37474f', lw=0.8, label=f'{CONTOUR_M} m contours'),
        Line2D([0], [0], marker='o', color='#2e7d32', lw=0, label='oak + drip line'),
        Line2D([0], [0], marker='o', color='#9e9e9e', lw=0, label='removed (owner edit)'),
    ]
    ax.legend(handles=legend, loc='lower right', fontsize=7, framealpha=0.92)

    # source strip
    src = (
        f"DEM: USGS 3DEP 1 m terrarium (pack z{PACK['layers']['terrain']['maxzoom']}, "
        f"baked 2016–2018 SoCal Wildfires)  ·  sampled {STEP_M:g} m  ·  "
        f"oaks: trees.csv lidar crowns  ·  "
        f"buildable {stats['buildable_area_m2']:.0f} m²  ·  "
        f"Δz across window {stats['relief_m']:.2f} m  ·  analysis only — no house"
    )
    fig.text(0.5, 0.01, src, ha='center', va='bottom', fontsize=6.5, wrap=True)
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)


def main():
    ce, cn = lnglat_to_en(*CENTER_LL)
    print(f'centre EN ({ce:.2f}, {cn:.2f}) elev {elevation_en(ce, cn):.2f} m')

    es, ns, Z, e0, n0, e1, n1 = sample_dem(ce, cn)
    slope = slope_percent(Z, STEP_M)
    easy = slope < SLOPE_EASY
    care = (slope >= SLOPE_EASY) & (slope < SLOPE_CARE)
    avoid = slope >= SLOPE_CARE
    build_mask, build_area = largest_component(easy)

    zmin, zmax = float(np.nanmin(Z)), float(np.nanmax(Z))
    # fall across current footprint direction was SW — report window relief + SW drop from centre
    sw_e, sw_n = ce + 50 * math.cos(math.radians(228)), cn + 50 * math.sin(math.radians(228))
    # bearing 228° from north clockwise? User said "lowest toward the south-west (bearing 228°)"
    # standard: bearing from north clockwise: 228° = SSW. In EN: east = sin(bearing), north = cos(bearing)
    be = math.radians(228)
    sw_e = ce + 50 * math.sin(be)
    sw_n = cn + 50 * math.cos(be)
    # clamp to window
    sw_e = min(max(sw_e, e0), e1)
    sw_n = min(max(sw_n, n0), n1)

    levels = np.arange(
        math.floor(zmin / CONTOUR_M) * CONTOUR_M,
        math.ceil(zmax / CONTOUR_M) * CONTOUR_M + CONTOUR_M * 0.5,
        CONTOUR_M,
    )
    contour_feats = contours_geo(Z, es, ns, levels)

    # slope class polygons (merged)
    features = []
    for name, mask, note in (
        ('slope_under_15', easy, 'easy to build on'),
        ('slope_15_to_25', care, 'build with care'),
        ('slope_over_25', avoid, 'avoid'),
    ):
        polys = mask_to_polygons(mask, es, ns)
        if not polys:
            continue
        # MultiPolygon of all regions in class
        coords = [[p[1]] for p in polys]  # each poly is exterior-only ring list
        geom = {'type': 'MultiPolygon', 'coordinates': coords} if len(coords) > 1 else {
            'type': 'Polygon', 'coordinates': coords[0]
        }
        features.append({
            'type': 'Feature',
            'properties': {
                'kind': 'slope_class',
                'class': name,
                'note': note,
                'area_m2': round(sum(p[0] for p in polys), 1),
            },
            'geometry': geom,
        })

    build_polys = mask_to_polygons(build_mask, es, ns)
    if build_polys:
        features.append({
            'type': 'Feature',
            'properties': {
                'kind': 'buildable_envelope',
                'criterion': 'largest contiguous slope < 15%',
                'area_m2': round(build_area, 1),
                'note': 'analysis only — not a house footprint',
            },
            'geometry': {'type': 'Polygon', 'coordinates': [build_polys[0][1]]},
        })

    features.extend(contour_feats)

    house_poly = load_house_edit_poly()
    oaks = load_oaks(e0, n0, e1, n1, house_poly)
    features.extend(oaks)

    stats = {
        'relief_m': round(zmax - zmin, 2),
        'elev_min_m': round(zmin, 2),
        'elev_max_m': round(zmax, 2),
        'elev_centre_m': round(float(elevation_en(ce, cn)), 2),
        'slope_under_15_pct_of_window': round(100.0 * float(easy.mean()), 1),
        'slope_15_to_25_pct_of_window': round(100.0 * float(care.mean()), 1),
        'slope_over_25_pct_of_window': round(100.0 * float(avoid.mean()), 1),
        'buildable_area_m2': round(build_area, 1),
        'oaks_in_window': len(oaks),
        'oaks_removed_by_edit': sum(1 for o in oaks if o['properties']['removed_by_owner_edit']),
        'oaks_standing': sum(1 for o in oaks if not o['properties']['removed_by_owner_edit']),
    }

    sources = [
        {
            'layer': 'elevation / contours / slope',
            'file': 'terrain/{z}/{x}/{y}.png',
            'source': 'USGS 3DEP 1 m (CA_SoCal_Wildfires_B3_2018), terrarium-encoded',
            'resolution': '1 m (sampled at 1 m over the window)',
            'authority': 'derived',
            'captured': '2018',
            'pack_maxzoom': PACK['layers']['terrain']['maxzoom'],
        },
        {
            'layer': 'oaks (canopy tops + drip line)',
            'file': 'trees.csv',
            'source': '2018 lidar CHM local maxima; crown_radius_dm as drip-line radius',
            'resolution': 'tops under 2.5 m not listed; positions integer decimetres',
            'authority': 'derived',
            'captured': '2018',
            'note': 'No species column — on this knoll the recorded canopy is treated as the surveyed oaks. Owner edit trees-around-the-house flags removals within 12 m of the house footprint.',
        },
        {
            'layer': 'owner tree removals (flag only)',
            'file': 'edits.geojson#trees-around-the-house',
            'source': 'owner confirmation 2026-09-18',
            'resolution': '12 m buffer around county house footprint',
            'authority': 'owner',
        },
        {
            'layer': 'plan frame',
            'file': 'pack.json frame',
            'source': 'equirectangular metres at origin_lat',
            'resolution': f"{MX:.3f} m/deg lng, {MY:.3f} m/deg lat",
            'authority': 'pack',
        },
    ]

    meta = {
        'type': 'Feature',
        'properties': {
            'kind': 'analysis_metadata',
            'id': 'oak-leaf-knoll',
            'phase': 'C12',
            'title': 'Oak Leaf knoll site analysis',
            'purpose': 'Describe the land for a slope-following redesign. Analysis only — no house proposed.',
            'centre': CENTER_LL,
            'window_m': WINDOW_M,
            'contour_interval_m': CONTOUR_M,
            'sample_step_m': STEP_M,
            'slope_classes_pct': {'easy': SLOPE_EASY, 'care': SLOPE_CARE},
            'stats': stats,
            'sources': sources,
            'plan_image': 'analysis/oak-leaf-knoll.png',
            'measured_note': (
                'Across the current Oak Leaf footprint the pack DEM falls 5.44 m, '
                'lowest toward the south-west (bearing 228°). This analysis covers the 100×100 m knoll window.'
            ),
        },
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[
                list(en_to_lnglat(e0, n0)),
                list(en_to_lnglat(e1, n0)),
                list(en_to_lnglat(e1, n1)),
                list(en_to_lnglat(e0, n1)),
                list(en_to_lnglat(e0, n0)),
            ]],
        },
    }

    fc = {
        'type': 'FeatureCollection',
        'name': 'oak-leaf-knoll',
        'features': [meta] + features,
    }
    OUT_GEO.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEO.write_text(json.dumps(fc, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    draw_plan(es, ns, Z, slope, easy, build_mask, oaks, e0, n0, e1, n1, stats)

    print(json.dumps({
        'geojson': str(OUT_GEO.relative_to(ROOT)),
        'png': str(OUT_PNG.relative_to(ROOT)),
        'stats': stats,
        'contours': sum(1 for f in features if f['properties'].get('kind') == 'contour'),
    }, indent=2))


if __name__ == '__main__':
    main()
