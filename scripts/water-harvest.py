"""
C21.1 — size the water harvest to the 25 mm storm (re-sited on low ground).

  Ponds: rank by flow accumulation × TWI. Exclude creek *channel*, easement,
  oak crowns, footprints + Zone 0. buildable_score is reported, not a gate.
  Swales: adopt needed_section_m2 (width × depth stated); split if too wide.
  Route: D8 walk from every parcel cell — routed vs leaves the property.

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
from shapely.geometry import LineString, Point, Polygon, mapping, shape
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
# Practical swale section limit before we split (width × depth)
SWALE_MAX_WIDTH_M = 2.0
SWALE_MAX_DEPTH_M = 0.6
SWALE_MAX_SECTION = SWALE_MAX_WIDTH_M * SWALE_MAX_DEPTH_M  # 1.2 m²
CHANNEL_ACCUM_M2 = 500.0  # valley threshold used in land_layers keypoints
M2_PER_ACRE = 4046.8564224
GAL_PER_M3 = 264.172


def load_grid(name):
    z = np.load(GRID_DIR / f'{name}.npz')
    return np.asarray(z['data'], dtype=np.float64), np.asarray(z['es']), np.asarray(z['ns'])


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
    """Defined watercourse = creek model footprint (not the 15 m build buffer)."""
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
    """Prefer ~2:1 width:depth; clamp depth ≤ max."""
    depth = min(math.sqrt(section_m2 / 2.0), SWALE_MAX_DEPTH_M)
    width = section_m2 / max(depth, 0.05)
    return round(width, 2), round(depth, 2)


def cell_ij(e, n, es, ns):
    j = int(np.clip(round(e - es[0]), 0, len(es) - 1))
    i = int(np.clip(round(n - ns[0]), 0, len(ns) - 1))
    return i, j


def main():
    flow, es, ns = load_grid('flow_accum')
    build, _, _ = load_grid('buildable')
    twi, _, _ = load_grid('twi')
    dem = np.asarray(np.load(GRID_DIR / 'dem_1m.npz')['Z'], dtype=np.float64)
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
        # Prefer keypoints not under a crown; if under crown, offset downhill 8 m
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

    features = []
    swale_rows = []
    effective_mm = max(0.0, STORM_MM - INFIL_MM)

    for i, (accum, e, n, kp) in enumerate(kept):
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

        # Clip swale out of crowns (+0.5 m) / easement / zone0 rather than dropping catchment
        blockers = crowns.buffer(0.5)
        if easement is not None:
            blockers = blockers.union(easement)
        if zone0 is not None:
            blockers = blockers.union(zone0)
        cleared = line_en.difference(blockers)
        if cleared.is_empty:
            continue
        if cleared.geom_type == 'MultiLineString':
            cleared = max(cleared.geoms, key=lambda g: g.length)
        if cleared.geom_type != 'LineString' or cleared.length < 8.0:
            continue
        line_en = cleared
        length = max(float(line_en.length), 8.0)

        ii, jj = cell_ij(e, n, es, ns)
        cell_accum = float(flow[ii, jj]) if np.isfinite(flow[ii, jj]) else accum
        catch_m2 = max(accum, cell_accum)
        vol_m3 = catch_m2 * (effective_mm / 1000.0) * RUNOFF_C
        needed = vol_m3 / max(length, 1.0)

        # adopt needed section; split if wider than practical
        segments = []
        if needed <= SWALE_MAX_SECTION:
            segments.append((length, needed, line_en))
        else:
            n_split = int(math.ceil(needed / SWALE_MAX_SECTION))
            seg_len = length  # parallel runs of same length
            seg_sec = needed / n_split
            # offset parallel copies ~3 m apart
            dx = dy = 0.0
            if line_en.length > 0:
                # perpendicular unit
                x0, y0 = line_en.coords[0]
                x1, y1 = line_en.coords[-1]
                lx, ly = x1 - x0, y1 - y0
                L = math.hypot(lx, ly) or 1.0
                px, py = -ly / L, lx / L
            else:
                px, py = 0.0, 1.0
            for s_i in range(n_split):
                off = (s_i - (n_split - 1) / 2.0) * 3.0
                from shapely.affinity import translate
                segments.append((seg_len, seg_sec, translate(line_en, xoff=px * off, yoff=py * off)))

        for s_i, (seg_len, seg_sec, seg_line) in enumerate(segments):
            # re-clear after parallel offset (split copies can re-enter crowns)
            seg_clear = seg_line.difference(blockers)
            if seg_clear.is_empty:
                continue
            if seg_clear.geom_type == 'MultiLineString':
                seg_clear = max(seg_clear.geoms, key=lambda g: g.length)
            if seg_clear.geom_type != 'LineString' or seg_clear.length < 8.0:
                continue
            seg_line = seg_clear
            seg_len = max(float(seg_line.length), 8.0)
            # capacity from adopted section × actual length
            w, dpt = section_dims(seg_sec)
            cap = seg_len * seg_sec
            # event share proportional to this segment's capacity among siblings
            sid = f'swale-{i + 1}' if len(segments) == 1 else f'swale-{i + 1}{chr(ord("a") + s_i)}'
            event_share = vol_m3 / len(segments)
            row = {
                'id': sid,
                'kind': 'swale',
                'catchment_m2': round(catch_m2 / len(segments), 1),
                'length_m': round(seg_len, 1),
                'section_m2': round(seg_sec, 3),
                'width_m': w,
                'depth_m': dpt,
                'capacity_m3': round(cap, 2),
                'event_volume_m3': round(event_share, 2),
                'needed_section_m2': round(needed / len(segments), 3),
                'holds_event': cap >= event_share * 0.99,
                'split_from': None if len(segments) == 1 else f'swale-{i + 1}',
                'split_reason': None if len(segments) == 1 else (
                    f'needed {needed:.2f} m2 > max practical {SWALE_MAX_SECTION:.1f} m2'
                ),
            }
            swale_rows.append(row)
            features.append({
                'type': 'Feature',
                'properties': row,
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [list(en_to_lnglat(x, y)) for x, y in seg_line.coords],
                },
            })

    # --- ponds on low ground (flow × TWI), not buildable ---
    from shapely import vectorized
    EE, NN = np.meshgrid(es, ns)
    in_p = vectorized.contains(b_en, EE, NN)
    channel_mask = vectorized.contains(channel, EE, NN)
    crown_mask = vectorized.contains(crowns, EE, NN)
    ease_mask = vectorized.contains(easement, EE, NN) if easement is not None else np.zeros_like(in_p)
    z0_mask = vectorized.contains(zone0, EE, NN) if zone0 is not None else np.zeros_like(in_p)

    twi_n = twi.copy()
    twi_n[~np.isfinite(twi_n)] = np.nan
    twi_ok = np.isfinite(twi_n) & np.isfinite(flow)
    # rank score: high accumulation and wetness
    t_lo, t_hi = np.nanpercentile(twi_n[in_p & twi_ok], [5, 95])
    t_norm = np.clip((twi_n - t_lo) / max(t_hi - t_lo, 1e-6), 0, 1)
    rank = np.where(in_p & twi_ok & ~crown_mask & ~ease_mask & ~z0_mask,
                    flow * (0.35 + 0.65 * t_norm), 0.0)
    # still allow on_channel sites (flagged) — exclude only the creek *channel polygon*
    # from excavation? Brief: exclude inside creek channel itself. So channel_mask excluded.
    rank = np.where(channel_mask, 0.0, rank)

    ponds = []
    taken = [(e, n) for _, e, n, _ in kept]
    flat = rank.ravel()
    order = np.argsort(flat)[::-1]
    for idx in order:
        if len(ponds) >= 3:
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
        # size radius from catch / event so capacity ≈ event (useful hold)
        event_vol = catch * (effective_mm / 1000.0) * RUNOFF_C
        # area = event / depth; radius from that, clamp 4–12 m
        area = max(event_vol / POND_DEPTH_M, math.pi * 4 ** 2)
        radius = float(np.clip(math.sqrt(area / math.pi), 4.0, 12.0))
        pond_poly = Point(e, n).buffer(radius)
        # reject if footprint hits crown / easement / zone0 / creek channel
        if crowns.intersects(pond_poly) or (easement and easement.intersects(pond_poly)):
            continue
        if zone0 is not None and zone0.intersects(pond_poly):
            continue
        if channel.intersects(pond_poly):
            continue
        hold = math.pi * radius ** 2 * POND_DEPTH_M
        # on_channel: near drainage line or high-accum valley cell
        on_ch = False
        if drain_lines is not None and pond_poly.distance(drain_lines) < 8.0:
            on_ch = True
        if flow[i, j] >= CHANNEL_ACCUM_M2:
            on_ch = True
        season_vol = catch * (SEASON_MM / 1000.0) * RUNOFF_C * 0.5
        bsc = float(build[i, j]) if np.isfinite(build[i, j]) else 0.0
        taken.append((e, n))
        row = {
            'id': f'pond-{len(ponds) + 1}',
            'kind': 'pond',
            'catchment_m2': round(catch, 1),
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

    # --- route every parcel cell ---
    rows, cols = flow.shape
    # harvest sinks: cells within 2 m of a swale line or inside a pond
    harvest = np.zeros((rows, cols), dtype=bool)
    for f in features:
        g = shape(f['geometry'])
        props = f['properties']
        if props['kind'] == 'swale':
            line = LineString([lnglat_to_en(x, y) for x, y in g.coords])
            buf = line.buffer(2.0)
            harvest |= vectorized.contains(buf, EE, NN)
        elif props['kind'] == 'pond':
            poly = Polygon([lnglat_to_en(x, y) for x, y in g.exterior.coords])
            harvest |= vectorized.contains(poly, EE, NN)

    routed = np.zeros((rows, cols), dtype=bool)
    unrouted = np.zeros((rows, cols), dtype=bool)
    exit_edge = {'north': 0, 'south': 0, 'east': 0, 'west': 0, 'channel': 0}
    # cache walks
    memo = {}  # (i,j) -> 'routed'|'leave'|None

    def walk(i0, j0):
        key = (i0, j0)
        if key in memo:
            return memo[key]
        path = []
        i, j = i0, j0
        seen = set()
        result = 'leave'
        edge = None
        for _ in range(rows + cols + 5):
            if (i, j) in seen:
                result = 'leave'
                break
            seen.add((i, j))
            path.append((i, j))
            if harvest[i, j]:
                result = 'routed'
                break
            if channel_mask[i, j]:
                result = 'channel'
                break
            k = int(fdir[i, j]) if 0 <= i < rows and 0 <= j < cols else -1
            if k < 0:
                # leaves grid — classify by which side
                if i <= 1:
                    edge = 'south'
                elif i >= rows - 2:
                    edge = 'north'
                elif j <= 1:
                    edge = 'west'
                else:
                    edge = 'east'
                result = 'leave'
                break
            ni, nj = i + D8[k][0], j + D8[k][1]
            if not (0 <= ni < rows and 0 <= nj < cols) or not in_p[ni, nj]:
                # exiting parcel
                e_out, n_out = float(es[min(max(j, 0), cols - 1)]), float(ns[min(max(i, 0), rows - 1)])
                c = b_en.centroid
                de, dn = e_out - c.x, n_out - c.y
                if abs(de) > abs(dn):
                    edge = 'east' if de > 0 else 'west'
                else:
                    edge = 'north' if dn > 0 else 'south'
                result = 'leave'
                break
            i, j = ni, nj
        for p in path:
            memo[p] = (result, edge)
        return result, edge

    for i in range(rows):
        for j in range(cols):
            if not in_p[i, j]:
                continue
            res, edge = walk(i, j)
            if res == 'routed':
                routed[i, j] = True
            else:
                unrouted[i, j] = True
                if res == 'channel':
                    exit_edge['channel'] += 1
                elif edge:
                    exit_edge[edge] += 1

    routed_m2 = int(routed.sum())
    unrouted_m2 = int(unrouted.sum())
    parcel_cells = int(in_p.sum())

    # optional: add interception notes as geo features for large exit edges
    for edge_name, count in exit_edge.items():
        if count < 200 or edge_name == 'channel':
            continue
        # mark a mid-boundary point
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
                'note': (
                    f'~{count} m² drains off the {edge_name} survey line and cannot be '
                    'harvested without works outside the parcel.'
                ),
            },
            'geometry': {'type': 'Point', 'coordinates': list(en_to_lnglat(pt.x, pt.y))},
        })

    parcel_rain_m3 = parcel_m2 * STORM_M
    parcel_runoff_m3 = parcel_m2 * (effective_mm / 1000.0) * RUNOFF_C
    held = (
        sum(min(s['capacity_m3'], s['event_volume_m3']) for s in swale_rows)
        + sum(min(p['pond_capacity_m3'], p['event_volume_m3']) for p in ponds)
    )
    frac = held / parcel_runoff_m3 if parcel_runoff_m3 > 0 else 0.0
    season_through = (
        sum(s['catchment_m2'] for s in swale_rows) + sum(p['catchment_m2'] for p in ponds)
    ) * (SEASON_MM / 1000.0) * RUNOFF_C * 0.5

    from scipy import ndimage
    outside_touch = ndimage.binary_dilation(in_p, iterations=2) & ~in_p
    upslope = float(np.nanmax(flow[outside_touch])) if outside_touch.any() else 0.0
    catch_sum = sum(r['catchment_m2'] for r in swale_rows) + sum(p['catchment_m2'] for p in ponds)

    summary = {
        'authority': 'derived',
        'evidence': 'modelled',
        'storm_mm': STORM_MM,
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
                f'Swales sized to needed_section; practical max {SWALE_MAX_WIDTH_M}×'
                f'{SWALE_MAX_DEPTH_M} m = {SWALE_MAX_SECTION} m² then split parallel.'
            ),
            'pond_depth_m': POND_DEPTH_M,
            'pond_siting': 'flow_accum × TWI; exclude crowns, easement, Zone 0, creek channel',
            'season_mm_proxy': SEASON_MM,
            'season_note': 'Season volume uses a 400 mm proxy of similar-intensity catch — named assumption.',
            'on_channel_note': (
                'on_channel:true means the site sits on/near a defined watercourse. In California '
                'that typically needs a state wildlife agency answer before it is real — flagged '
                'for the owner, not concluded here.'
            ),
        },
        'parcel_m2': round(parcel_m2, 1),
        'parcel_acres': round(parcel_m2 / M2_PER_ACRE, 2),
        'parcel_rain_m3_25mm': round(parcel_rain_m3, 1),
        'parcel_runoff_m3_25mm': round(parcel_runoff_m3, 1),
        'swale_capacity_m3_total': round(sum(s['capacity_m3'] for s in swale_rows), 1),
        'pond_capacity_m3_total': round(sum(p['pond_capacity_m3'] for p in ponds), 1),
        'held_m3_total': round(held, 1),
        'held_gallons_total': round(held * GAL_PER_M3, 0),
        'fraction_of_runoff_held': round(frac, 3),
        'season_through_m3': round(season_through, 1),
        'season_through_gallons': round(season_through * GAL_PER_M3, 0),
        'catchment_sum_m2': round(min(catch_sum, parcel_m2 + upslope), 1),
        'catchment_sum_raw_m2': round(catch_sum, 1),
        'parcel_plus_upslope_m2': round(parcel_m2 + upslope, 1),
        'upslope_max_accum_m2': round(upslope, 1),
        'routed_m2': routed_m2,
        'unrouted_m2': unrouted_m2,
        'parcel_cells_m2': parcel_cells,
        'unrouted_exits': exit_edge,
        'swales': swale_rows,
        'ponds': ponds,
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
        },
        'features': features,
    }
    (ROOT / 'water-harvest.geojson').write_text(json.dumps(geo, indent=2) + '\n', encoding='utf-8')

    # figure
    _, e0, n0, e1, n1 = parcel_window(20)
    ees, nns, Z = sample_dem(e0, n0, e1, n1)
    fig, ax = plt.subplots(figsize=(10, 8))
    ls = LightSource(azdeg=315, altdeg=45)
    ax.imshow(ls.hillshade(np.nan_to_num(Z, nan=np.nanmean(Z)), vert_exag=2, dx=1, dy=1),
              origin='lower', extent=[ees[0], ees[-1], nns[0], nns[-1]], cmap='gray')
    # unrouted wash
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
        elif kind == 'unrouted_exit':
            e, n = lnglat_to_en(*g.coords[0][:2])
            ax.plot(e, n, 'o', color='#e65100', ms=8)
    ax.set_aspect('equal')
    ax.set_title(
        f'Water harvest (C21) — held {held:.0f} m³ ({100 * frac:.0f}% of {parcel_runoff_m3:.0f} m³ runoff)'
    )
    ax.set_xlabel('east m')
    ax.set_ylabel('north m')
    fig.tight_layout()
    fig.savefig(ROOT / 'analysis' / 'water-harvest.png', dpi=150)
    plt.close(fig)

    print(
        f'OK water-harvest: {len(swale_rows)} swales, {len(ponds)} ponds; '
        f'held {held:.0f} m3 ({100 * frac:.1f}%); '
        f'routed {routed_m2} + unrouted {unrouted_m2} = {routed_m2 + unrouted_m2} '
        f'(parcel cells {parcel_cells})'
    )


if __name__ == '__main__':
    main()
