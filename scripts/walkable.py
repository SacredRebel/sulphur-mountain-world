"""
C24 — walkable ground, connectivity graph, and a low-triangle collision mesh.

  Slope threshold: 30° — above this, walking becomes scrambling for most people
  on unimproved ground (steeper than a 1:1.7 rise; trails and codes usually
  stay well below). Named assumption, not a field measurement.

  Excluded: building footprints, trunk radius, slope > 30°, creek channel.
  Not excluded: tree canopy (you walk under oaks — same rule as C20 gathering).

    python scripts/walkable.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union
from skimage import measure

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR  # noqa: E402
from terrain import en_to_lnglat, lnglat_to_en  # noqa: E402
from glb import Model, surface  # noqa: E402

SLOPE_MAX_DEG = 30.0
TRUNK_RADIUS_M = 0.45
COLLISION_STEP_M = 3.0
COLLISION_MAX_TRIS = 50_000
COLLISION_MAX_DEV_M = 2.5


def load_grid(name):
    z = np.load(GRID_DIR / f'{name}.npz')
    return np.asarray(z['data']), np.asarray(z['es']), np.asarray(z['ns'])


def dem_on_grid(es, ns):
    pack = np.load(GRID_DIR / 'dem_1m.npz')
    des, dns, zd = np.asarray(pack['es']), np.asarray(pack['ns']), np.asarray(pack['Z'], dtype=np.float64)
    jj = np.clip(np.round(es - des[0]).astype(int), 0, zd.shape[1] - 1)
    ii = np.clip(np.round(ns - dns[0]).astype(int), 0, zd.shape[0] - 1)
    jj_g, ii_g = np.meshgrid(jj, ii)
    z = zd[ii_g, jj_g].copy()
    ee, nn = np.meshgrid(es, ns)
    valid = (ee >= des[0]) & (ee <= des[-1]) & (nn >= dns[0]) & (nn <= dns[-1])
    z[~valid] = np.nan
    return z


def slope_deg(Z, step=1.0):
    gy, gx = np.gradient(Z, step)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def parcel_en():
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    return Polygon([lnglat_to_en(x, y) for x, y in shape(survey['features'][0]['geometry']).exterior.coords])


def footprints_en():
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    parts = []
    for m in man['models']:
        if m['id'] in ('site-grounds', 'creek') or not m.get('footprint'):
            continue
        parts.append(Polygon([lnglat_to_en(a, b) for a, b in m['footprint']]))
    return unary_union(parts) if parts else None


def creek_en():
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    creek = next(m for m in man['models'] if m['id'] == 'creek')
    return Polygon([lnglat_to_en(a, b) for a, b in creek['footprint']])


def trunks_en():
    pts = []
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            pts.append(Point(float(row['x_east_dm']) / 10.0, float(row['y_north_dm']) / 10.0))
    return unary_union([p.buffer(TRUNK_RADIUS_M) for p in pts]) if pts else None


def mask_polygon(geom, es, ns):
    EE, NN = np.meshgrid(es, ns)
    from shapely import contains_xy
    return contains_xy(geom, EE, NN)


def polygonize_component(mask, es, ns, component_id):
    """Contour the binary mask → polygons in EN, then lng/lat features."""
    # pad so contours close at edges
    padded = np.pad(mask.astype(np.uint8), 1, mode='constant')
    contours = measure.find_contours(padded.astype(float), 0.5)
    polys = []
    for cont in contours:
        # cont is (row, col) in padded coords; row 0 = south-1
        coords = []
        for r, c in cont:
            i = r - 1
            j = c - 1
            e = float(es[0] + j * (es[1] - es[0] if len(es) > 1 else 1.0))
            n = float(ns[0] + i * (ns[1] - ns[0] if len(ns) > 1 else 1.0))
            coords.append((e, n))
        if len(coords) < 4:
            continue
        try:
            p = Polygon(coords)
            if not p.is_valid:
                p = p.buffer(0)
            if p.is_empty or p.area < 2.0:
                continue
            if p.geom_type == 'Polygon':
                polys.append(p)
            elif p.geom_type == 'MultiPolygon':
                polys.extend([g for g in p.geoms if g.area >= 2.0])
        except Exception:
            continue
    if not polys:
        return []
    u = unary_union(polys)
    geoms = [u] if u.geom_type == 'Polygon' else list(u.geoms)
    out = []
    for g in geoms:
        if g.area < 2.0:
            continue
        out.append(g)
    return out


def build_collision(es, ns, Z, footprints, parcel, max_tris=COLLISION_MAX_TRIS):
    """Downsampled DEM tiles + extruded building shells."""
    step = COLLISION_STEP_M
    e0, n0, e1, n1 = parcel.bounds
    cols = int(math.ceil((e1 - e0) / step)) + 1
    rows = int(math.ceil((n1 - n0) / step)) + 1
    ces = e0 + np.arange(cols) * step
    cns = n0 + np.arange(rows) * step
    jj = np.clip(np.round((ces - es[0]) / (es[1] - es[0])).astype(int), 0, len(es) - 1)
    ii = np.clip(np.round((cns - ns[0]) / (ns[1] - ns[0])).astype(int), 0, len(ns) - 1)
    jj_g, ii_g = np.meshgrid(jj, ii)
    zc = Z[ii_g, jj_g]

    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    spawn = lnglat_to_en(pack['spawn']['lng'], pack['spawn']['lat'])
    js = int(np.clip(round((spawn[0] - es[0]) / (es[1] - es[0])), 0, len(es) - 1))
    iss = int(np.clip(round((spawn[1] - ns[0]) / (ns[1] - ns[0])), 0, len(ns) - 1))
    z_spawn = float(Z[iss, js]) if np.isfinite(Z[iss, js]) else float(np.nanmean(Z))

    from shapely import contains_xy
    EE, NN = np.meshgrid(ces, cns)
    inside = contains_xy(parcel, EE, NN) & np.isfinite(zc)

    def local(e, n, z):
        return (float(e - spawn[0]), float(z - z_spawn), float(-(n - spawn[1])))

    m = Model('collision')
    dirt = surface('dirt')
    timber = surface('timber')
    tris = 0

    for i in range(rows - 1):
        stop = False
        for j in range(cols - 1):
            if not (inside[i, j] and inside[i, j + 1] and inside[i + 1, j] and inside[i + 1, j + 1]):
                continue
            if tris + 2 > max_tris - 8000:
                stop = True
                break
            a = local(ces[j], cns[i], float(zc[i, j]))
            b = local(ces[j + 1], cns[i], float(zc[i, j + 1]))
            c = local(ces[j + 1], cns[i + 1], float(zc[i + 1, j + 1]))
            d = local(ces[j], cns[i + 1], float(zc[i + 1, j]))
            m.quad(dirt, a, b, c, d)
            tris += 2
        if stop:
            break

    if footprints is not None:
        geoms = [footprints] if footprints.geom_type == 'Polygon' else list(footprints.geoms)
        wall_h = 2.5
        for g in geoms:
            ring = list(g.exterior.coords)
            for (e0_, n0_), (e1_, n1_) in zip(ring, ring[1:]):
                if tris + 2 > max_tris:
                    break
                j0 = int(np.clip(round((e0_ - es[0]) / (es[1] - es[0])), 0, len(es) - 1))
                i0 = int(np.clip(round((n0_ - ns[0]) / (ns[1] - ns[0])), 0, len(ns) - 1))
                j1 = int(np.clip(round((e1_ - es[0]) / (es[1] - es[0])), 0, len(es) - 1))
                i1 = int(np.clip(round((n1_ - ns[0]) / (ns[1] - ns[0])), 0, len(ns) - 1))
                z0 = float(Z[i0, j0]) if np.isfinite(Z[i0, j0]) else z_spawn
                z1 = float(Z[i1, j1]) if np.isfinite(Z[i1, j1]) else z_spawn
                a = local(e0_, n0_, z0)
                b = local(e1_, n1_, z1)
                c = local(e1_, n1_, z1 + wall_h)
                d = local(e0_, n0_, z0 + wall_h)
                m.quad(timber, a, b, c, d)
                tris += 2

    out = ROOT / 'models' / 'collision.glb'
    out.parent.mkdir(parents=True, exist_ok=True)
    m.write(out)

    rng = np.random.default_rng(24)
    samples = []
    # sample random points inside parcel; bilinear from fine DEM vs nearest coarse node
    for _ in range(200):
        e = float(rng.uniform(e0, e1))
        n = float(rng.uniform(n0, n1))
        if not parcel.contains(__import__('shapely.geometry', fromlist=['Point']).Point(e, n)):
            continue
        jc = int(np.clip(round((e - ces[0]) / step), 0, len(ces) - 1))
        ic = int(np.clip(round((n - cns[0]) / step), 0, len(cns) - 1))
        if not inside[ic, jc]:
            continue
        z_coarse = float(zc[ic, jc])
        jf = int(np.clip(round((e - es[0]) / (es[1] - es[0])), 0, len(es) - 1))
        iff = int(np.clip(round((n - ns[0]) / (ns[1] - ns[0])), 0, len(ns) - 1))
        z_fine = float(Z[iff, jf])
        if np.isfinite(z_fine) and np.isfinite(z_coarse):
            samples.append(abs(z_coarse - z_fine))
    max_dev = float(max(samples)) if samples else 0.0
    return tris, max_dev, out


def main():
    build, es, ns = load_grid('buildable')
    Z = dem_on_grid(es, ns)
    sl = slope_deg(Z)
    parcel = parcel_en()
    EE, NN = np.meshgrid(es, ns)
    from shapely import contains_xy
    in_p = contains_xy(parcel, EE, NN)

    fp = footprints_en()
    creek = creek_en()
    trunks = trunks_en()

    walk = in_p & np.isfinite(Z) & np.isfinite(sl) & (sl <= SLOPE_MAX_DEG)
    if fp is not None:
        walk &= ~mask_polygon(fp, es, ns)
    walk &= ~mask_polygon(creek, es, ns)
    if trunks is not None:
        walk &= ~mask_polygon(trunks, es, ns)

    labeled, n_comp = ndimage.label(walk)
    print(f'walkable cells={int(walk.sum())} components={n_comp}')

    features = []
    polys_by_id = {}
    total_area = 0.0
    for cid in range(1, n_comp + 1):
        mask = labeled == cid
        if int(mask.sum()) < 4:
            continue
        mean_sl = float(np.nanmean(sl[mask]))
        geoms = polygonize_component(mask, es, ns, cid)
        if not geoms:
            continue
        for gi, g in enumerate(geoms):
            trimmed = g
            if fp is not None:
                trimmed = trimmed.difference(fp)
            trimmed = trimmed.difference(creek)
            if trunks is not None:
                trimmed = trimmed.difference(trunks)
            if trimmed.is_empty:
                continue
            parts = [trimmed] if trimmed.geom_type == 'Polygon' else list(trimmed.geoms)
            for pi, g in enumerate(parts):
                if g.area < 2.0:
                    continue
                area = float(g.area)
                total_area += area
                eid = f'{cid}' if len(geoms) == 1 and len(parts) == 1 else f'{cid}.{gi + 1}.{pi + 1}'
                polys_by_id[eid] = g
                features.append({
                    'type': 'Feature',
                    'properties': {
                        'component_id': eid,
                        'area_m2': round(area, 1),
                        'mean_slope_deg': round(mean_sl, 2),
                        'kind': 'walkable',
                    },
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [
                            [list(en_to_lnglat(e, n)) for e, n in g.exterior.coords],
                            *[
                                [list(en_to_lnglat(e, n)) for e, n in hole.coords]
                                for hole in g.interiors
                            ],
                        ],
                    },
                })

    # walk graph
    ids = sorted(polys_by_id.keys())
    touches = []
    gaps = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ga, gb = polys_by_id[a], polys_by_id[b]
            d = ga.distance(gb)
            if d < 1.05:  # share edge / corner at 1 m grid
                touches.append({'a': a, 'b': b, 'distance_m': round(d, 3)})
            else:
                gaps.append({'a': a, 'b': b, 'narrowest_gap_m': round(d, 3)})
    gaps.sort(key=lambda x: x['narrowest_gap_m'])

    graph = {
        'authority': 'derived',
        'evidence': 'modelled',
        'slope_max_deg': SLOPE_MAX_DEG,
        'slope_note': (
            '30° is the usual limit before walking becomes scrambling on unimproved '
            'ground; not an accessibility standard.'
        ),
        'exclusions': [
            'building footprints (not site-grounds / creek)',
            f'trunk radius {TRUNK_RADIUS_M} m',
            f'slope > {SLOPE_MAX_DEG}°',
            'creek channel footprint',
        ],
        'not_excluded': ['tree canopy'],
        'component_count': len(ids),
        'total_area_m2': round(total_area, 1),
        'touches': touches,
        'gaps': gaps[:50],  # narrowest 50 non-touching pairs
        'gaps_note': 'narrowest_gap_m between components that do not touch; path candidates',
    }
    (ROOT / 'walk-graph.json').write_text(json.dumps(graph, indent=2) + '\n', encoding='utf-8')

    geo = {
        'type': 'FeatureCollection',
        'properties': {
            'authority': 'derived',
            'evidence': 'modelled',
            'slope_max_deg': SLOPE_MAX_DEG,
            'style_by': 'component_id',
            'generator': 'scripts/walkable.py',
        },
        'features': features,
    }
    (ROOT / 'walkable.geojson').write_text(json.dumps(geo, indent=2) + '\n', encoding='utf-8')

    n_tris, max_dev, coll_path = build_collision(es, ns, Z, fp, parcel)
    meta = {
        'authority': 'derived',
        'evidence': 'modelled',
        'path': 'models/collision.glb',
        'triangles': n_tris,
        'max_deviation_from_dem_m': round(max_dev, 3),
        'deviation_bound_m': COLLISION_MAX_DEV_M,
        'step_m': COLLISION_STEP_M,
        'frame': 'pack spawn origin; x east, y up, z south',
    }
    (ROOT / 'collision.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')

    # register lightly in pack.json
    pack_path = ROOT / 'pack.json'
    pack = json.loads(pack_path.read_text(encoding='utf-8'))
    pack['layers']['walkable'] = {
        'file': 'walkable.geojson',
        'authority': 'derived',
        'evidence': 'modelled',
        'kind': 'vector',
        'units': 'geometry; area_m2; mean_slope_deg',
        'generator': 'scripts/walkable.py',
    }
    pack['layers']['walk_graph'] = {
        'file': 'walk-graph.json',
        'authority': 'derived',
        'evidence': 'modelled',
        'kind': 'table',
        'generator': 'scripts/walkable.py',
    }
    pack['layers']['collision'] = {
        'file': 'models/collision.glb',
        'meta': 'collision.json',
        'authority': 'derived',
        'evidence': 'modelled',
        'kind': 'mesh',
        'generator': 'scripts/walkable.py',
    }
    pack_path.write_text(json.dumps(pack, indent=2) + '\n', encoding='utf-8')

    print(
        f'OK walkable: {len(features)} polygons, {total_area:.0f} m²; '
        f'collision tris={n_tris} max_dev={max_dev:.2f} m -> {coll_path.name}'
    )


if __name__ == '__main__':
    main()
