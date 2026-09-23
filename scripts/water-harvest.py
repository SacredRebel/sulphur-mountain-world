"""
C22 — water harvest with exclusive first-hit D8 catchments.

  Ponds: flow accumulation × TWI; exclude creek channel, easement, crowns, Zone 0.
  Swales: sized from exclusive catchment event volume (max 1.2 m² section).
  Route: D8 walk from every parcel cell — first harvest work wins; creek is NOT a sink.

    python scripts/water-harvest.py
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
from shapely import contains_xy
from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR, parcel_window, sample_dem  # noqa: E402
from land_layers import D8, d8_accum  # noqa: E402
from terrain import en_to_lnglat, lnglat_to_en  # noqa: E402

STORM_MM = 25.0
STORM_M = STORM_MM / 1000.0
RUNOFF_C = 0.45
INFIL_MM = 5.0
POND_DEPTH_M = 1.2
SEASON_MM = 400.0
ZONE0_M = 1.5
SWALE_MAX_WIDTH_M = 2.0
SWALE_MAX_DEPTH_M = 0.6
SWALE_MAX_SECTION = SWALE_MAX_WIDTH_M * SWALE_MAX_DEPTH_M
CHANNEL_ACCUM_M2 = 500.0
M2_PER_ACRE = 4046.8564224
GAL_PER_M3 = 264.172
HARVEST_BUFFER_M = 2.0
CATCHMENT_METHOD = 'exclusive_first_hit_d8'

C21_HEADLINE = {
    'held_m3': 117.2,
    'fraction_of_runoff_held': 0.34,
    'routed_m2': 3752,
    'catchment_sum_m2': 13026,
}


def load_grid(name):
    z = np.load(GRID_DIR / f'{name}.npz')
    return np.asarray(z['data'], dtype=np.float64), np.asarray(z['es']), np.asarray(z['ns'])


def dem_on_flow_grid(es, ns):
    """Sample cached dem_1m onto the flow/buildable 1 m grid (same es/ns)."""
    pack = np.load(GRID_DIR / 'dem_1m.npz')
    des, dns, zd = np.asarray(pack['es']), np.asarray(pack['ns']), np.asarray(pack['Z'], dtype=np.float64)
    jj = np.clip(np.round(es - des[0]).astype(int), 0, zd.shape[1] - 1)
    ii = np.clip(np.round(ns - dns[0]).astype(int), 0, zd.shape[0] - 1)
    jj_grid, ii_grid = np.meshgrid(jj, ii)
    z = zd[ii_grid, jj_grid].copy()
    ee, nn = np.meshgrid(es, ns)
    valid = (ee >= des[0]) & (ee <= des[-1]) & (nn >= dns[0]) & (nn <= dns[-1])
    z[~valid] = np.nan
    return z


def load_trees():
    trees = []
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            trees.append((
                float(row['x_east_dm']) / 10.0,
                float(row['y_north_dm']) / 10.0,
                float(row.get('crown_radius_dm') or 30) / 10.0,
            ))
    return trees


def easement_poly(survey_features):
    parts = []
    for f in survey_features:
        name = str((f.get('properties') or {}).get('name') or '').lower()
        if 'easement' not in name:
            continue
        g = shape(f['geometry'])
        if g.geom_type == 'Polygon':
            parts.append(Polygon([lnglat_to_en(x, y) for x, y in g.exterior.coords]).buffer(2.5))
        elif g.geom_type == 'MultiPolygon':
            for p in g.geoms:
                parts.append(Polygon([lnglat_to_en(x, y) for x, y in p.exterior.coords]).buffer(2.5))
    return unary_union(parts) if parts else None


def creek_channel():
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    creek = next(m for m in man['models'] if m['id'] == 'creek')
    return Polygon([lnglat_to_en(a, b) for a, b in creek['footprint']])


def footprints_zone0():
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    polys = []
    for m in man['models']:
        if m['id'] in ('site-grounds', 'creek') or not m.get('footprint'):
            continue
        fp = Polygon([lnglat_to_en(a, b) for a, b in m['footprint']])
        polys.append(fp.buffer(ZONE0_M))
    return unary_union(polys) if polys else None


def crown_union(trees):
    return unary_union([Point(e, n).buffer(r) for e, n, r in trees])


def drainage_channels_en():
    d = json.loads((ROOT / 'drainage.geojson').read_text(encoding='utf-8'))
    lines = []
    for f in d['features']:
        g = shape(f['geometry'])
        if g.geom_type == 'LineString':
            lines.append(LineString([lnglat_to_en(x, y) for x, y in g.coords]))
        elif g.geom_type == 'MultiLineString':
            for part in g.geoms:
                lines.append(LineString([lnglat_to_en(x, y) for x, y in part.coords]))
    return unary_union(lines) if lines else None


def section_dims(section_m2: float):
    depth = min(math.sqrt(section_m2 / 2.0), SWALE_MAX_DEPTH_M)
    width = section_m2 / max(depth, 0.05)
    return round(width, 2), round(depth, 2)


def cell_ij(e, n, es, ns):
    j = int(np.clip(round(e - es[0]), 0, len(es) - 1))
    i = int(np.clip(round(n - ns[0]), 0, len(ns) - 1))
    return i, j


def pond_on_channel(e, n, i, j, pond_poly, flow, drain_lines):
    on_ch = False
    if drain_lines is not None and pond_poly.distance(drain_lines) < 8.0:
        on_ch = True
    if np.isfinite(flow[i, j]) and flow[i, j] >= CHANNEL_ACCUM_M2:
        on_ch = True
    return on_ch


def place_swales(
    *,
    b_en,
    es,
    ns,
    fdir,
    crowns,
    easement,
    zone0,
    kept_keypoints,
    swales_g,
):
    features = []
    swale_rows = []
    blockers = crowns.buffer(0.5)
    if easement is not None:
        blockers = blockers.union(easement)
    if zone0 is not None:
        blockers = blockers.union(zone0)

    for i, (accum, e, n, kp) in enumerate(kept_keypoints):
        best = None
        best_d = 1e9
        for s in swales_g:
            line = shape(s['geometry'])
            d = line.distance(Point(e, n))
            if d < best_d:
                best_d = d
                best = line
        if best is None or best_d > 25:
            length = 25.0
            line_en = LineString([(e - 12.5, n), (e + 12.5, n)])
        else:
            coords_en = [lnglat_to_en(x, y) for x, y in best.coords]
            line_en = LineString(coords_en)
            length = max(float(line_en.length), 10.0)

        cleared = line_en.difference(blockers)
        if cleared.is_empty:
            continue
        if cleared.geom_type == 'MultiLineString':
            cleared = max(cleared.geoms, key=lambda g: g.length)
        if cleared.geom_type != 'LineString' or cleared.length < 8.0:
            continue
        line_en = cleared
        length = max(float(line_en.length), 8.0)

        # placeholder section; exclusive routing resizes from catchment
        seg_len = length
        seg_sec = 0.15
        segments = [(seg_len, seg_sec, line_en)]

        for s_i, (seg_len, seg_sec, seg_line) in enumerate(segments):
            seg_clear = seg_line.difference(blockers)
            if seg_clear.is_empty:
                continue
            if seg_clear.geom_type == 'MultiLineString':
                seg_clear = max(seg_clear.geoms, key=lambda g: g.length)
            if seg_clear.geom_type != 'LineString' or seg_clear.length < 8.0:
                continue
            seg_line = seg_clear
            seg_len = max(float(seg_line.length), 8.0)
            sid = f'swale-{i + 1}' if len(segments) == 1 else f'swale-{i + 1}{chr(ord("a") + s_i)}'
            row_stub = {
                'id': sid,
                'kind': 'swale',
                'on_channel': False,
                'length_m': round(seg_len, 1),
                'section_m2': 0.0,
                'width_m': 0.0,
                'depth_m': 0.0,
                'capacity_m3': 0.0,
                'event_volume_m3': 0.0,
                'needed_section_m2': 0.0,
                'catchment_m2': 0.0,
                'exclusive_area_m2': 0.0,
                'holds_event': False,
                'split_from': None,
                'split_reason': None,
            }
            swale_rows.append(row_stub)
            features.append({
                'type': 'Feature',
                'properties': row_stub,
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [list(en_to_lnglat(x, y)) for x, y in seg_line.coords],
                },
            })

    return swale_rows, features


def place_ponds(
    *,
    b_en,
    es,
    ns,
    flow,
    twi,
    build,
    crowns,
    easement,
    zone0,
    channel,
    drain_lines,
    taken_centers,
    max_ponds=3,
    require_off_channel=False,
):
    EE, NN = np.meshgrid(es, ns)
    in_p_mask = contains_xy(b_en, EE, NN)
    channel_mask = contains_xy(channel, EE, NN)
    crown_mask = contains_xy(crowns, EE, NN)
    ease_mask = contains_xy(easement, EE, NN) if easement is not None else np.zeros_like(in_p_mask)
    z0_mask = contains_xy(zone0, EE, NN) if zone0 is not None else np.zeros_like(in_p_mask)

    twi_n = twi.copy()
    twi_n[~np.isfinite(twi_n)] = np.nan
    twi_ok = np.isfinite(twi_n) & np.isfinite(flow)
    t_lo, t_hi = np.nanpercentile(twi_n[in_p_mask & twi_ok], [5, 95])
    t_norm = np.clip((twi_n - t_lo) / max(t_hi - t_lo, 1e-6), 0, 1)
    rank = np.where(
        in_p_mask & twi_ok & ~crown_mask & ~ease_mask & ~z0_mask,
        flow * (0.35 + 0.65 * t_norm),
        0.0,
    )
    rank = np.where(channel_mask, 0.0, rank)

    ponds = []
    features = []
    taken = list(taken_centers)
    flat = rank.ravel()
    order = np.argsort(flat)[::-1]
    effective_mm = max(0.0, STORM_MM - INFIL_MM)

    for idx in order:
        if len(ponds) >= max_ponds:
            break
        if flat[idx] <= 0:
            break
        i = int(idx // rank.shape[1])
        j = int(idx % rank.shape[1])
        e, n = float(es[j]), float(ns[i])
        if not b_en.contains(Point(e, n)):
            continue
        if any(math.hypot(e - te, n - tn) < 40 for te, tn in taken):
            continue
        catch = float(flow[i, j])
        if catch < 150:
            continue
        event_vol = catch * (effective_mm / 1000.0) * RUNOFF_C
        area = max(event_vol / POND_DEPTH_M, math.pi * 4 ** 2)
        radius = float(np.clip(math.sqrt(area / math.pi), 4.0, 12.0))
        pond_poly = Point(e, n).buffer(radius)
        if crowns.intersects(pond_poly) or (easement and easement.intersects(pond_poly)):
            continue
        if zone0 is not None and zone0.intersects(pond_poly):
            continue
        if channel.intersects(pond_poly):
            continue
        on_ch = pond_on_channel(e, n, i, j, pond_poly, flow, drain_lines)
        if require_off_channel and on_ch:
            continue
        hold = math.pi * radius ** 2 * POND_DEPTH_M
        season_vol = catch * (SEASON_MM / 1000.0) * RUNOFF_C * 0.5
        bsc = float(build[i, j]) if np.isfinite(build[i, j]) else 0.0
        taken.append((e, n))
        row = {
            'id': f'pond-{len(ponds) + 1}',
            'kind': 'pond',
            'catchment_m2': 0.0,
            'exclusive_area_m2': 0.0,
            'event_volume_m3': round(event_vol, 2),
            'season_volume_m3': round(season_vol, 1),
            'pond_capacity_m3': round(hold, 1),
            'radius_m': round(radius, 2),
            'depth_m_assumed': POND_DEPTH_M,
            'buildable_score': round(bsc, 3),
            'on_channel': bool(on_ch),
            'twi': round(float(twi[i, j]), 3) if np.isfinite(twi[i, j]) else None,
            'flow_accum_m2': round(catch, 1),
            'east_m': round(e, 1),
            'north_m': round(n, 1),
        }
        ponds.append(row)
        features.append({
            'type': 'Feature',
            'properties': row,
            'geometry': {
                'type': 'Polygon',
                'coordinates': [[list(en_to_lnglat(x, y)) for x, y in pond_poly.exterior.coords]],
            },
        })

    return ponds, features


def work_geometries(works, geo_features):
    """Map work id -> shapely geometry in pack EN metres (harvest footprint)."""
    by_id = {f['properties']['id']: f for f in geo_features}
    geoms = []
    for w in works:
        feat = by_id[w['id']]
        g = shape(feat['geometry'])
        if w['kind'] == 'swale':
            line = LineString([lnglat_to_en(x, y) for x, y in g.coords])
            geoms.append(line.buffer(HARVEST_BUFFER_M))
        else:
            poly = Polygon([lnglat_to_en(x, y) for x, y in g.exterior.coords])
            geoms.append(poly)
    return geoms


def build_owner_grid(works, geoms, es, ns, rows, cols):
    owner = np.full((rows, cols), -1, dtype=np.int32)
    EE, NN = np.meshgrid(es, ns)
    for wi, geom in enumerate(geoms):
        # geom is already in pack EN metres
        mask = contains_xy(geom, EE, NN)
        claim = mask & (owner < 0)
        owner[claim] = wi
    return owner


def classify_exit(i, j, es, ns, cols, b_en):
    e_out = float(es[min(max(j, 0), cols - 1)])
    n_out = float(ns[min(max(i, 0), len(ns) - 1)])
    c = b_en.centroid
    de, dn = e_out - c.x, n_out - c.y
    if abs(de) > abs(dn):
        return 'east' if de > 0 else 'west'
    return 'north' if dn > 0 else 'south'


def exclusive_route(in_p, fdir, owner, es, ns, b_en):
    rows, cols = in_p.shape
    assign = np.full((rows, cols), -1, dtype=np.int32)
    unrouted = np.zeros((rows, cols), dtype=bool)
    exit_edge = {'north': 0, 'south': 0, 'east': 0, 'west': 0}
    memo = {}

    def walk(i0, j0):
        if (i0, j0) in memo:
            return memo[(i0, j0)]
        path = []
        i, j = i0, j0
        seen = set()
        edge = None
        while True:
            if (i, j) in memo:
                result = memo[(i, j)]
                for pi, pj in path:
                    memo[(pi, pj)] = result
                memo[(i0, j0)] = result
                return result
            if (i, j) in seen:
                result = ('leave', edge)
                for pi, pj in path:
                    memo[(pi, pj)] = result
                memo[(i0, j0)] = result
                return result
            seen.add((i, j))
            path.append((i, j))
            ow = int(owner[i, j])
            if ow >= 0:
                result = ('routed', ow)
                for pi, pj in path:
                    memo[(pi, pj)] = result
                return result
            k = int(fdir[i, j]) if 0 <= i < rows and 0 <= j < cols else -1
            if k < 0:
                if i <= 1:
                    edge = 'south'
                elif i >= rows - 2:
                    edge = 'north'
                elif j <= 1:
                    edge = 'west'
                else:
                    edge = 'east'
                result = ('leave', edge)
                for pi, pj in path:
                    memo[(pi, pj)] = result
                memo[(i0, j0)] = result
                return result
            ni, nj = i + D8[k][0], j + D8[k][1]
            if not (0 <= ni < rows and 0 <= nj < cols) or not in_p[ni, nj]:
                edge = classify_exit(i, j, es, ns, cols, b_en)
                result = ('leave', edge)
                for pi, pj in path:
                    memo[(pi, pj)] = result
                memo[(i0, j0)] = result
                return result
            i, j = ni, nj

    for i in range(rows):
        for j in range(cols):
            if not in_p[i, j]:
                continue
            res, extra = walk(i, j)
            if res == 'routed':
                assign[i, j] = extra
            else:
                unrouted[i, j] = True
                if extra:
                    exit_edge[extra] += 1

    return assign, unrouted, exit_edge


def poly_en_to_ll(geom):
    """Pack-EN shapely polygon/multipolygon → GeoJSON lng/lat coordinates."""
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == 'Polygon':
        return {
            'type': 'Polygon',
            'coordinates': [[list(en_to_lnglat(x, y)) for x, y in geom.exterior.coords]],
        }
    if geom.geom_type == 'MultiPolygon':
        return {
            'type': 'MultiPolygon',
            'coordinates': [
                [[list(en_to_lnglat(x, y)) for x, y in p.exterior.coords]]
                for p in geom.geoms
            ],
        }
    return None


def cells_to_polygon(cells, es, ns):
    """Approximate catchment footprint: buffered convex hull of cell centres (fast)."""
    if not cells:
        return None
    from shapely.geometry import MultiPoint
    step = max(1, len(cells) // 800)
    pts = [(float(es[j]), float(ns[i])) for i, j in cells[::step]]
    if len(pts) < 3:
        i, j = cells[0]
        return Point(float(es[j]), float(ns[i])).buffer(1.0)
    return MultiPoint(pts).convex_hull.buffer(0.75)



def apply_exclusive_volumes(works, assign, effective_mm):
    counts = [0] * len(works)
    cells_by_work = [[] for _ in works]
    rows, cols = assign.shape
    for i in range(rows):
        for j in range(cols):
            wi = int(assign[i, j])
            if wi >= 0:
                counts[wi] += 1
                cells_by_work[wi].append((i, j))

    for wi, w in enumerate(works):
        area = float(counts[wi])
        w['exclusive_area_m2'] = round(area, 1)
        w['catchment_m2'] = round(area, 1)
        ev = area * (effective_mm / 1000.0) * RUNOFF_C
        w['event_volume_m3'] = round(ev, 2)
        if w['kind'] == 'swale':
            length = max(float(w['length_m']), 1.0)
            needed = ev / length
            if needed <= SWALE_MAX_SECTION:
                sec = needed
            else:
                sec = SWALE_MAX_SECTION
            width_m, dpt = section_dims(sec)
            w['section_m2'] = round(sec, 3)
            w['width_m'] = width_m
            w['depth_m'] = dpt
            w['needed_section_m2'] = round(needed, 3)
            cap = length * sec
            w['capacity_m3'] = round(cap, 2)
            w['holds_event'] = cap >= ev * 0.99
        else:
            w['holds_event'] = w['pond_capacity_m3'] >= ev * 0.99

    return cells_by_work, counts


def variant_metrics(works, assign, parcel_runoff_m3):
    routed_m2 = int((assign >= 0).sum())
    catchment_sum_m2 = round(sum(w['exclusive_area_m2'] for w in works), 1)
    held = (
        sum(min(w['capacity_m3'], w['event_volume_m3']) for w in works if w['kind'] == 'swale')
        + sum(min(w['pond_capacity_m3'], w['event_volume_m3']) for w in works if w['kind'] == 'pond')
    )
    frac = held / parcel_runoff_m3 if parcel_runoff_m3 > 0 else 0.0
    return {
        'works': works,
        'held_m3': round(held, 1),
        'held_gallons': round(held * GAL_PER_M3, 0),
        'fraction': round(frac, 3),
        'routed_m2': routed_m2,
        'catchment_sum_m2': catchment_sum_m2,
        'note': f'exclusive first-hit D8; {len(works)} harvest works',
    }


def run_variant(works, work_features, in_p, fdir, es, ns, b_en, parcel_runoff_m3, effective_mm):
    geoms = work_geometries(works, work_features)
    owner = build_owner_grid(works, geoms, es, ns, in_p.shape[0], in_p.shape[1])
    assign, unrouted, exit_edge = exclusive_route(in_p, fdir, owner, es, ns, b_en)
    cells_by_work, _ = apply_exclusive_volumes(works, assign, effective_mm)
    metrics = variant_metrics(works, assign, parcel_runoff_m3)
    return metrics, assign, unrouted, exit_edge, cells_by_work, owner


def main():
    flow, es, ns = load_grid('flow_accum')
    build, _, _ = load_grid('buildable')
    twi, _, _ = load_grid('twi')
    dem = dem_on_flow_grid(es, ns)
    fdir, _, _ = d8_accum(dem)

    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    b_ll = shape(survey['features'][0]['geometry'])
    b_en = Polygon([lnglat_to_en(x, y) for x, y in b_ll.exterior.coords])
    parcel_m2 = float(b_en.area)

    trees = load_trees()
    crowns = crown_union(trees)
    easement = easement_poly(survey['features'])
    channel = creek_channel()
    zone0 = footprints_zone0()
    drain_lines = drainage_channels_en()

    keys = json.loads((ROOT / 'keylines.geojson').read_text(encoding='utf-8'))
    keypoints = [f for f in keys['features'] if (f.get('properties') or {}).get('kind') == 'keypoint']
    swales_g = [f for f in keys['features'] if (f.get('properties') or {}).get('kind') in ('swale_line', 'keyline')]

    ranked = []
    for kp in keypoints:
        lng, lat = kp['geometry']['coordinates'][:2]
        e, n = lnglat_to_en(lng, lat)
        if not b_en.buffer(5).contains(Point(e, n)):
            continue
        ranked.append((float(kp['properties'].get('accum_m2') or 0), e, n, kp))
    ranked.sort(key=lambda t: -t[0])
    kept = []
    for accum, e, n, kp in ranked:
        if any(math.hypot(e - ee, n - nn) < 30 for _, ee, nn, _ in kept):
            continue
        pt = Point(e, n)
        if crowns.contains(pt):
            ii, jj = cell_ij(e, n, es, ns)
            k = int(fdir[ii, jj]) if 0 <= ii < fdir.shape[0] and 0 <= jj < fdir.shape[1] else -1
            if k < 0:
                continue
            e = e + D8[k][1] * 8.0
            n = n + D8[k][0] * 8.0
            pt = Point(e, n)
            if crowns.contains(pt) or not b_en.contains(pt):
                continue
        if easement and easement.contains(pt):
            continue
        if zone0 is not None and zone0.contains(pt):
            continue
        kept.append((accum, e, n, kp))
        if len(kept) >= 10:
            break

    swale_rows, swale_features = place_swales(
        b_en=b_en, es=es, ns=ns, fdir=fdir, crowns=crowns, easement=easement,
        zone0=zone0, kept_keypoints=kept, swales_g=swales_g,
    )
    taken = [(e, n) for _, e, n, _ in kept]
    ponds, pond_features = place_ponds(
        b_en=b_en, es=es, ns=ns, flow=flow, twi=twi, build=build,
        crowns=crowns, easement=easement, zone0=zone0, channel=channel,
        drain_lines=drain_lines, taken_centers=taken, max_ponds=3, require_off_channel=False,
    )

    EE, NN = np.meshgrid(es, ns)
    in_p = contains_xy(b_en, EE, NN)

    all_works_list = swale_rows + ponds
    all_work_features = swale_features + pond_features
    effective_mm = max(0.0, STORM_MM - INFIL_MM)
    parcel_runoff_m3 = parcel_m2 * (effective_mm / 1000.0) * RUNOFF_C

    all_metrics, assign, unrouted, exit_edge, cells_by_work, _ = run_variant(
        [dict(w) for w in all_works_list],
        all_work_features,
        in_p, fdir, es, ns, b_en, parcel_runoff_m3, effective_mm,
    )
    # sync rows back
    for i, w in enumerate(all_metrics['works']):
        all_works_list[i].update(w)

    # off_channel: drop on_channel ponds; add off-channel ponds up to 3 total ponds in variant
    off_swales = [dict(w) for w in swale_rows]
    off_ponds = [dict(p) for p in ponds if not p['on_channel']]
    off_features = [f for f in swale_features] + [f for f in pond_features if not f['properties']['on_channel']]
    off_taken = taken + [(p['east_m'], p['north_m']) for p in off_ponds]
    need = 3 - len(off_ponds)
    if need > 0:
        extra_ponds, extra_feats = place_ponds(
            b_en=b_en, es=es, ns=ns, flow=flow, twi=twi, build=build,
            crowns=crowns, easement=easement, zone0=zone0, channel=channel,
            drain_lines=drain_lines, taken_centers=off_taken, max_ponds=need,
            require_off_channel=True,
        )
        for p, f in zip(extra_ponds, extra_feats):
            p['id'] = f'pond-off-{len(off_ponds) + 1}'
            f['properties']['id'] = p['id']
            off_ponds.append(p)
            off_features.append(f)

    off_works = off_swales + off_ponds
    off_metrics, off_assign, _, _, off_cells, _ = run_variant(
        [dict(w) for w in off_works],
        off_features,
        in_p, fdir, es, ns, b_en, parcel_runoff_m3, effective_mm,
    )

    features = list(all_work_features)
    for wi, w in enumerate(all_works_list):
        cells = cells_by_work[wi]
        poly = cells_to_polygon(cells, es, ns)
        if poly is None or poly.is_empty:
            continue
        features.append({
            'type': 'Feature',
            'properties': {
                'id': f"catchment-{w['id']}",
                'kind': 'catchment',
                'work_id': w['id'],
                'area_m2': w['exclusive_area_m2'],
                'method': CATCHMENT_METHOD,
            },
            'geometry': poly_en_to_ll(poly),
        })

    for edge_name, count in exit_edge.items():
        if count < 200:
            continue
        minx, miny, maxx, maxy = b_en.bounds
        if edge_name == 'north':
            pt = Point((minx + maxx) / 2, maxy)
        elif edge_name == 'south':
            pt = Point((minx + maxx) / 2, miny)
        elif edge_name == 'east':
            pt = Point(maxx, (miny + maxy) / 2)
        else:
            pt = Point(minx, (miny + maxy) / 2)
        features.append({
            'type': 'Feature',
            'properties': {
                'id': f'unrouted-exit-{edge_name}',
                'kind': 'unrouted_exit',
                'edge': edge_name,
                'cells': count,
                'area_m2': count,
            },
            'geometry': {'type': 'Point', 'coordinates': list(en_to_lnglat(pt.x, pt.y))},
        })

    swales_out = [w for w in all_works_list if w['kind'] == 'swale']
    ponds_out = [w for w in all_works_list if w['kind'] == 'pond']
    routed_m2 = all_metrics['routed_m2']
    catchment_sum_m2 = all_metrics['catchment_sum_m2']
    held = all_metrics['held_m3']
    frac = all_metrics['fraction']
    unrouted_m2 = int(unrouted.sum())
    parcel_cells = int(in_p.sum())

    season_through = sum(w['catchment_m2'] for w in all_works_list) * (SEASON_MM / 1000.0) * RUNOFF_C * 0.5

    summary = {
        'authority': 'derived',
        'evidence': 'modelled',
        'storm_mm': STORM_MM,
        'catchment_method': CATCHMENT_METHOD,
        'assumptions': {
            'runoff_coefficient': RUNOFF_C,
            'runoff_coefficient_note': (
                'Assumed 0.45 for a 1-hour 25 mm event on mixed oak/grass/compacted hillside '
                '— not measured on site.'
            ),
            'infiltration_mm_during_event': INFIL_MM,
            'infiltration_note': (
                'Assumed 5 mm infiltrates during the event (sandy-loam order of magnitude) '
                '— not a field measurement.'
            ),
            'swale_max_section_m2': SWALE_MAX_SECTION,
            'swale_section_note': (
                f'Swales sized to exclusive catchment; practical max {SWALE_MAX_WIDTH_M}×'
                f'{SWALE_MAX_DEPTH_M} m = {SWALE_MAX_SECTION} m² then capped.'
            ),
            'pond_depth_m': POND_DEPTH_M,
            'pond_siting': 'flow_accum × TWI; exclude crowns, easement, Zone 0, creek channel',
            'season_mm_proxy': SEASON_MM,
            'season_note': 'Season volume uses a 400 mm proxy — named assumption.',
            'on_channel_note': (
                'on_channel:true means the site sits on/near a defined watercourse — flagged for the owner.'
            ),
            'c21_headline_was': C21_HEADLINE,
        },
        'parcel_m2': round(parcel_m2, 1),
        'parcel_acres': round(parcel_m2 / M2_PER_ACRE, 2),
        'parcel_rain_m3_25mm': round(parcel_m2 * STORM_M, 1),
        'parcel_runoff_m3_25mm': round(parcel_runoff_m3, 1),
        'swale_capacity_m3_total': round(sum(w['capacity_m3'] for w in swales_out), 1),
        'pond_capacity_m3_total': round(sum(p['pond_capacity_m3'] for p in ponds_out), 1),
        'held_m3_total': held,
        'held_gallons_total': round(held * GAL_PER_M3, 0),
        'fraction_of_runoff_held': frac,
        'season_through_m3': round(season_through, 1),
        'season_through_gallons': round(season_through * GAL_PER_M3, 0),
        'catchment_sum_m2': catchment_sum_m2,
        'catchment_union_m2': catchment_sum_m2,
        'routed_m2': routed_m2,
        'unrouted_m2': unrouted_m2,
        'parcel_cells_m2': parcel_cells,
        'unrouted_exits': exit_edge,
        'swales': swales_out,
        'ponds': ponds_out,
        'variants': {
            'all_works': all_metrics,
            'off_channel': {
                **off_metrics,
                'note': (
                    f'exclusive first-hit D8; on_channel ponds excluded; '
                    f'{len(off_ponds)} off-channel pond(s), '
                    f'{sum(1 for w in off_works if w["kind"] == "swale")} swale(s)'
                ),
            },
        },
    }
    (ROOT / 'water-harvest.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    geo = {
        'type': 'FeatureCollection',
        'properties': {
            'authority': 'derived',
            'evidence': 'modelled',
            'storm_mm': STORM_MM,
            'generator': 'scripts/water-harvest.py',
            'style_by': 'kind',
            'catchment_method': CATCHMENT_METHOD,
        },
        'features': features,
    }
    (ROOT / 'water-harvest.geojson').write_text(json.dumps(geo, indent=2) + '\n', encoding='utf-8')

    _, e0, n0, e1, n1 = parcel_window(20)
    ees, nns, Z = sample_dem(e0, n0, e1, n1)
    fig, ax = plt.subplots(figsize=(10, 8))
    ls = LightSource(azdeg=315, altdeg=45)
    ax.imshow(ls.hillshade(np.nan_to_num(Z, nan=np.nanmean(Z)), vert_exag=2, dx=1, dy=1),
              origin='lower', extent=[ees[0], ees[-1], nns[0], nns[-1]], cmap='gray')
    ur = np.ma.array(unrouted.astype(float), mask=~unrouted)
    ax.imshow(ur, origin='lower', extent=[es[0], es[-1], ns[0], ns[-1]],
              cmap='Oranges', alpha=0.35, vmin=0, vmax=1)
    bx, by = b_en.exterior.xy
    ax.plot(bx, by, color='black', lw=1.2)
    for f in features:
        g = shape(f['geometry'])
        kind = f['properties']['kind']
        if kind == 'swale' and g.geom_type == 'LineString':
            xs, ys = zip(*[lnglat_to_en(a, b) for a, b in g.coords])
            ax.plot(xs, ys, color='#1565c0', lw=2)
        elif kind == 'pond' and g.geom_type == 'Polygon':
            xs, ys = zip(*[lnglat_to_en(a, b) for a, b in g.exterior.coords])
            col = '#c62828' if f['properties'].get('on_channel') else '#0277bd'
            ax.fill(xs, ys, color=col, alpha=0.45)
            ax.plot(xs, ys, color=col, lw=1)
    ax.set_aspect('equal')
    ax.set_title(f'Water harvest (C22) — held {held:.0f} m³ ({100 * frac:.0f}% runoff)')
    ax.set_xlabel('east m')
    ax.set_ylabel('north m')
    fig.tight_layout()
    fig.savefig(ROOT / 'analysis' / 'water-harvest.png', dpi=150)
    plt.close(fig)

    print(
        f'OK water-harvest C22: all_works held {held:.1f} m3 ({100 * frac:.1f}%); '
        f'routed={routed_m2} catch_sum={catchment_sum_m2} (must match); '
        f'off_channel held {off_metrics["held_m3"]:.1f} m3 ({100 * off_metrics["fraction"]:.1f}%) '
        f'routed={off_metrics["routed_m2"]} catch_sum={off_metrics["catchment_sum_m2"]}'
    )


if __name__ == '__main__':
    main()
