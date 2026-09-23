"""
C20.2 — defensible-space zones around each structure.

  Zone 0: 0–1.5 m (0–5 ft) ember-resistant
  Zone 1: 1.5–9.1 m (5–30 ft) lean and green
  Zone 2: 9.1–30.5 m (30–100 ft) reduced fuel
  On slopes > 20%, Zone 2 extends downhill by 1.5×.

    python scripts/defensible-space.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LightSource
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import parcel_window, sample_dem  # noqa: E402
from terrain import en_to_lnglat, lnglat_to_en, elevation_en  # noqa: E402

Z0 = (0.0, 1.5)
Z1 = (1.5, 9.1)
Z2 = (9.1, 30.5)
SLOPE_EXTEND = 1.5  # Zone 2 downhill multiplier when slope > 20%


def footprint_en(m):
    return Polygon([lnglat_to_en(a, b) for a, b in m['footprint']])


def load_trees():
    trees = []
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            trees.append({
                'e': float(row['x_east_dm']) / 10.0,
                'n': float(row['y_north_dm']) / 10.0,
                'h': float(row.get('height_dm') or 0) / 10.0,
                'r': float(row.get('crown_radius_dm') or 30) / 10.0,
            })
    return trees


def downhill_bearing(fp: Polygon, Z_fn):
    """Unit vector of steepest descent at footprint centroid (east, north)."""
    c = fp.centroid
    e, n = c.x, c.y
    try:
        z0 = Z_fn(e, n)
        ze = Z_fn(e + 1.0, n)
        zn = Z_fn(e, n + 1.0)
    except Exception:
        return 0.0, -1.0, 0.0
    de, dn = ze - z0, zn - z0
    # gradient points uphill; downhill is opposite
    mag = math.hypot(de, dn)
    if mag < 1e-9:
        return 0.0, -1.0, 0.0
    slope_pct = mag * 100.0  # rise/run * 100 for 1 m step
    return -de / mag, -dn / mag, slope_pct


def zone_ring(fp: Polygon, r_in: float, r_out: float, downhill=None, extend_out=None):
    """Annulus between r_in and r_out; on steep ground Zone 2 uses a larger outer radius."""
    outer_r = extend_out if (extend_out and extend_out > r_out) else r_out
    outer = fp.buffer(outer_r)
    inner = fp.buffer(r_in) if r_in > 0 else None
    ring = outer.difference(inner) if inner is not None else outer
    return ring


def crowns_in_zone(zone: Polygon, trees, overhang_fp=None):
    """Count crowns whose centre is in zone; also crowns that overhang Zone 0."""
    count = 0
    overhanging = []
    for i, t in enumerate(trees):
        pt = Point(t['e'], t['n'])
        if zone.contains(pt) or zone.distance(pt) <= t['r']:
            # centre in zone OR crown intersects zone
            if zone.intersects(pt.buffer(t['r'])):
                count += 1
                if overhang_fp is not None and pt.buffer(t['r']).intersects(overhang_fp):
                    overhanging.append({
                        'e': round(t['e'], 2), 'n': round(t['n'], 2),
                        'height_m': round(t['h'], 2), 'crown_r_m': round(t['r'], 2),
                    })
    return count, overhanging


def canopy_pct(zone: Polygon, trees, samples: int = 400):
    if zone.is_empty or zone.area < 1:
        return 0.0
    minx, miny, maxx, maxy = zone.bounds
    rng = np.random.default_rng(42)
    hits = 0
    tried = 0
    for _ in range(samples * 3):
        e = float(rng.uniform(minx, maxx))
        n = float(rng.uniform(miny, maxy))
        if not zone.contains(Point(e, n)):
            continue
        tried += 1
        under = any((e - t['e']) ** 2 + (n - t['n']) ** 2 <= t['r'] ** 2 for t in trees)
        if under:
            hits += 1
        if tried >= samples:
            break
    return 100.0 * hits / max(tried, 1)


def main():
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    boundary = shape(survey['features'][0]['geometry'])
    b_en = Polygon([lnglat_to_en(x, y) for x, y in boundary.exterior.coords])
    trees = load_trees()

    features = []
    rows = []
    for m in man['models']:
        mid = m['id']
        if mid in ('site-grounds',) or not m.get('footprint'):
            continue
        try:
            fp = footprint_en(m)
        except Exception:
            continue
        if fp.is_empty or fp.area < 1:
            continue

        de, dn, slope_pct = downhill_bearing(fp, elevation_en)
        extend = Z2[1] * SLOPE_EXTEND if slope_pct > 20.0 else Z2[1]

        zones = [
            ('0', Z0[0], Z0[1], Z0[1]),
            ('1', Z1[0], Z1[1], Z1[1]),
            ('2', Z2[0], Z2[1], extend),
        ]
        row = {
            'structure_id': mid,
            'slope_pct_at_centroid': round(slope_pct, 1),
            'zone2_outer_m': round(extend, 2),
        }
        for zname, r_in, r_out, r_ext in zones:
            ring = zone_ring(fp, r_in, r_out, downhill=(de, dn, slope_pct),
                             extend_out=r_ext if zname == '2' else None)
            if ring.is_empty:
                continue
            crosses = bool(ring.intersects(b_en.exterior) or not b_en.contains(ring))
            # clip reporting to what we can manage on-parcel for note, but keep full ring
            crowns, overhang = crowns_in_zone(
                ring, trees, overhang_fp=fp if zname == '0' else None,
            )
            pct = canopy_pct(ring, trees)
            props = {
                'structure_id': mid,
                'zone': zname,
                'area_m2': round(float(ring.area), 1),
                'crowns_in_zone': int(crowns),
                'canopy_pct': round(pct, 1),
                'crosses_boundary': crosses,
                'outer_m': round(r_ext if zname == '2' else r_out, 2),
            }
            if zname == '0':
                props['overhanging_crowns'] = overhang[:20]
                row['zone0_crowns'] = crowns
                row['zone0_overhang'] = len(overhang)
            if zname == '1':
                row['zone1_crowns'] = crowns
                row['zone1_canopy_pct'] = round(pct, 1)
            if zname == '2':
                row['zone2_crowns'] = crowns
                row['zone2_canopy_pct'] = round(pct, 1)
                row['zone2_crosses_boundary'] = crosses

            if ring.geom_type == 'Polygon':
                rings = [[list(en_to_lnglat(x, y)) for x, y in ring.exterior.coords]]
                for interior in ring.interiors:
                    rings.append([list(en_to_lnglat(x, y)) for x, y in interior.coords])
                geom = {'type': 'Polygon', 'coordinates': rings}
            else:
                polys = []
                for p in ring.geoms:
                    if p.geom_type != 'Polygon':
                        continue
                    rings = [[list(en_to_lnglat(x, y)) for x, y in p.exterior.coords]]
                    for interior in p.interiors:
                        rings.append([list(en_to_lnglat(x, y)) for x, y in interior.coords])
                    polys.append(rings)
                geom = {'type': 'MultiPolygon', 'coordinates': polys}
            features.append({'type': 'Feature', 'properties': props, 'geometry': geom})
        rows.append(row)

    geo = {
        'type': 'FeatureCollection',
        'properties': {
            'authority': 'derived',
            'evidence': 'modelled',
            'note': (
                'Geometric reading of published defensible-space distances (0–5 / 5–30 / 30–100 ft). '
                'Not a fire-agency inspection. No tree removal is implied.'
            ),
            'generator': 'scripts/defensible-space.py',
        },
        'features': features,
    }
    (ROOT / 'defensible-space.geojson').write_text(json.dumps(geo, indent=2) + '\n', encoding='utf-8')
    summary = {
        'authority': 'derived',
        'evidence': 'modelled',
        'zones_m': {'0': list(Z0), '1': list(Z1), '2': list(Z2)},
        'slope_extend_factor': SLOPE_EXTEND,
        'structures': rows,
    }
    (ROOT / 'defensible.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')

    # figure
    _, e0, n0, e1, n1 = parcel_window(20)
    es, ns, Z = sample_dem(e0, n0, e1, n1)
    fig, ax = plt.subplots(figsize=(10, 8))
    ls = LightSource(azdeg=315, altdeg=45)
    ax.imshow(ls.hillshade(np.nan_to_num(Z, nan=np.nanmean(Z)), vert_exag=2, dx=1, dy=1),
              origin='lower', extent=[es[0], es[-1], ns[0], ns[-1]], cmap='gray')
    bx, by = b_en.exterior.xy
    ax.plot(bx, by, color='black', lw=1.2)
    colors = {'0': '#c62828', '1': '#ef6c00', '2': '#f9a825'}
    for f in features:
        z = f['properties']['zone']
        g = shape(f['geometry'])
        if g.geom_type == 'Polygon':
            xs, ys = zip(*[lnglat_to_en(a, b) for a, b in g.exterior.coords])
            ax.fill(xs, ys, color=colors[z], alpha=0.25)
            ax.plot(xs, ys, color=colors[z], lw=0.6)
    # crowns as dots
    for t in trees:
        if e0 <= t['e'] <= e1 and n0 <= t['n'] <= n1:
            ax.plot(t['e'], t['n'], '.', color='#2e7d32', markersize=1, alpha=0.4)
    ax.set_aspect('equal')
    ax.set_title('Defensible space (C20) — Zones 0 / 1 / 2')
    ax.set_xlabel('east m')
    ax.set_ylabel('north m')
    fig.tight_layout()
    fig.savefig(ROOT / 'analysis' / 'defensible-space.png', dpi=150)
    plt.close(fig)
    print(f'OK defensible-space: {len(rows)} structures, {len(features)} zone rings')


if __name__ == '__main__':
    main()
