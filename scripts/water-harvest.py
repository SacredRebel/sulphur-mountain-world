"""
C20.3 — size the water harvest to the 25 mm storm.

  Per keyline swale: catchment from flow_accum, runoff volume, swale capacity.
  Up to three pond/tank sites on buildable ground.
  Whole-parcel 25 mm event total.

    python scripts/water-harvest.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LightSource
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR, parcel_window, sample_dem  # noqa: E402
from terrain import en_to_lnglat, lnglat_to_en  # noqa: E402

STORM_MM = 25.0
STORM_M = STORM_MM / 1000.0
# Assumed runoff coefficient for a 1-hour 25 mm event on this semi-arid hillside
# (mixed oak / grass / compacted ground). Named assumption — not measured.
RUNOFF_C = 0.45
# Assumed soil infiltration during the event (mm). Named assumption — sandy loam order.
INFIL_MM = 5.0
# Swale typical cross-section: 0.6 m wide × 0.3 m deep trapezoid ≈ 0.15 m²
SWALE_SECTION_M2 = 0.15
PARCEL_ACRES = 9.47
M2_PER_ACRE = 4046.8564224


def load_grid(name):
    z = np.load(GRID_DIR / f'{name}.npz')
    return np.asarray(z['data'], dtype=np.float64), np.asarray(z['es']), np.asarray(z['ns'])


def main():
    flow, es, ns = load_grid('flow_accum')
    build, _, _ = load_grid('buildable')
    twi, _, _ = load_grid('twi')

    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    b_ll = shape(survey['features'][0]['geometry'])
    b_en = Polygon([lnglat_to_en(x, y) for x, y in b_ll.exterior.coords])
    parcel_m2 = float(b_en.area)

    keys = json.loads((ROOT / 'keylines.geojson').read_text(encoding='utf-8'))
    keypoints = [f for f in keys['features'] if (f.get('properties') or {}).get('kind') == 'keypoint']
    swales = [f for f in keys['features'] if (f.get('properties') or {}).get('kind') in ('swale_line', 'keyline')]

    # Rank keypoints by accum; keep spatially independent ones (nested basins double-count)
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
        if any(math.hypot(e - ee, n - nn) < 35 for _, ee, nn, _ in kept):
            continue
        kept.append((accum, e, n, kp))
        if len(kept) >= 12:
            break

    features = []
    swale_rows = []
    total_swale_cap = 0.0

    for i, (accum, e, n, kp) in enumerate(kept):
        best = None
        best_d = 1e9
        for s in swales:
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

        j = int(np.clip(round(e - es[0]), 0, len(es) - 1))
        ii = int(np.clip(round(n - ns[0]), 0, len(ns) - 1))
        cell_accum = float(flow[ii, j]) if np.isfinite(flow[ii, j]) else accum
        catch_m2 = max(accum, cell_accum)

        effective_mm = max(0.0, STORM_MM - INFIL_MM)
        vol_m3 = catch_m2 * (effective_mm / 1000.0) * RUNOFF_C
        capacity_m3 = length * SWALE_SECTION_M2
        needed_section = vol_m3 / max(length, 1.0)
        total_swale_cap += capacity_m3

        row = {
            'id': f'swale-{i + 1}',
            'kind': 'swale',
            'catchment_m2': round(catch_m2, 1),
            'length_m': round(length, 1),
            'section_m2': SWALE_SECTION_M2,
            'capacity_m3': round(capacity_m3, 2),
            'event_volume_m3': round(vol_m3, 2),
            'needed_section_m2': round(needed_section, 3),
            'holds_event': capacity_m3 >= vol_m3 * 0.9,
        }
        swale_rows.append(row)
        features.append({
            'type': 'Feature',
            'properties': row,
            'geometry': {
                'type': 'LineString',
                'coordinates': [list(en_to_lnglat(x, y)) for x, y in line_en.coords],
            },
        })

    # pond sites: top buildable cells with high flow_accum, spaced apart
    usable = np.isfinite(build) & (build >= 0.5) & np.isfinite(flow)
    score = np.where(usable, flow * (0.5 + 0.5 * build), 0.0)
    ponds = []
    taken = [(e, n) for _, e, n, _ in kept]
    flat = score.ravel()
    order = np.argsort(flat)[::-1]
    for idx in order:
        if len(ponds) >= 3:
            break
        if flat[idx] <= 0:
            break
        i = int(idx // score.shape[1])
        j = int(idx % score.shape[1])
        e, n = float(es[j]), float(ns[i])
        if not b_en.contains(Point(e, n)):
            continue
        if any(math.hypot(e - te, n - tn) < 40 for te, tn in taken):
            continue
        if build[i, j] < 0.33:
            continue
        catch = float(flow[i, j])
        if catch < 200:
            continue
        taken.append((e, n))
        effective_mm = max(0.0, STORM_MM - INFIL_MM)
        event_vol = catch * (effective_mm / 1000.0) * RUNOFF_C
        season_mm = 400.0
        season_vol = catch * (season_mm / 1000.0) * RUNOFF_C * 0.5
        radius = 8.0
        pond_poly = Point(e, n).buffer(radius)
        hold = math.pi * radius ** 2 * 1.2
        row = {
            'id': f'pond-{len(ponds) + 1}',
            'kind': 'pond',
            'catchment_m2': round(catch, 1),
            'event_volume_m3': round(event_vol, 2),
            'season_volume_m3': round(season_vol, 1),
            'pond_capacity_m3': round(hold, 1),
            'radius_m': radius,
            'depth_m_assumed': 1.2,
            'buildable_score': round(float(build[i, j]), 3),
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

    parcel_rain_m3 = parcel_m2 * STORM_M
    parcel_runoff_m3 = parcel_m2 * (max(0.0, STORM_MM - INFIL_MM) / 1000.0) * RUNOFF_C
    # useful hold = min(capacity, that feature's event volume) — don't credit empty volume
    held = (
        sum(min(s['capacity_m3'], s['event_volume_m3']) for s in swale_rows)
        + sum(min(p['pond_capacity_m3'], p['event_volume_m3']) for p in ponds)
    )
    frac = held / parcel_runoff_m3 if parcel_runoff_m3 > 0 else 0.0

    from shapely import vectorized
    from scipy import ndimage
    EE, NN = np.meshgrid(es, ns)
    in_p = vectorized.contains(b_en, EE, NN)
    outside_touch = ndimage.binary_dilation(in_p, iterations=2) & ~in_p
    upslope = float(np.nanmax(flow[outside_touch])) if outside_touch.any() else 0.0
    # Independent basins: sum is valid after spatial thinning; still cap at parcel+upslope
    catch_sum = sum(r['catchment_m2'] for r in swale_rows) + sum(p['catchment_m2'] for p in ponds)
    catch_sum_capped = min(catch_sum, parcel_m2 + upslope)

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
            'swale_section_m2': SWALE_SECTION_M2,
            'swale_section_note': 'Assumed 0.6 m wide × 0.3 m deep trapezoid ≈ 0.15 m².',
            'pond_depth_m': 1.2,
            'season_mm_proxy': 400,
            'season_note': 'Season volume uses a 400 mm proxy of similar-intensity catch — named assumption.',
        },
        'parcel_m2': round(parcel_m2, 1),
        'parcel_acres': round(parcel_m2 / M2_PER_ACRE, 2),
        'parcel_rain_m3_25mm': round(parcel_rain_m3, 1),
        'parcel_runoff_m3_25mm': round(parcel_runoff_m3, 1),
        'swale_capacity_m3_total': round(total_swale_cap, 1),
        'pond_capacity_m3_total': round(sum(p['pond_capacity_m3'] for p in ponds), 1),
        'held_m3_total': round(held, 1),
        'fraction_of_runoff_held': round(frac, 3),
        'catchment_sum_m2': round(catch_sum_capped, 1),
        'catchment_sum_raw_m2': round(catch_sum, 1),
        'parcel_plus_upslope_m2': round(parcel_m2 + upslope, 1),
        'upslope_max_accum_m2': round(upslope, 1),
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
    bx, by = b_en.exterior.xy
    ax.plot(bx, by, color='black', lw=1.2)
    for f in features:
        g = shape(f['geometry'])
        if f['properties']['kind'] == 'swale' and g.geom_type == 'LineString':
            xs, ys = zip(*[lnglat_to_en(a, b) for a, b in g.coords])
            ax.plot(xs, ys, color='#1565c0', lw=2)
        elif f['properties']['kind'] == 'pond' and g.geom_type == 'Polygon':
            xs, ys = zip(*[lnglat_to_en(a, b) for a, b in g.exterior.coords])
            ax.fill(xs, ys, color='#0277bd', alpha=0.45)
            ax.plot(xs, ys, color='#01579b', lw=1)
    ax.set_aspect('equal')
    ax.set_title(f'Water harvest (C20) — {STORM_MM:.0f} mm event, C={RUNOFF_C}')
    ax.set_xlabel('east m')
    ax.set_ylabel('north m')
    fig.tight_layout()
    fig.savefig(ROOT / 'analysis' / 'water-harvest.png', dpi=150)
    plt.close(fig)

    print(
        f'OK water-harvest: {len(swale_rows)} swales, {len(ponds)} ponds; '
        f'parcel runoff {parcel_runoff_m3:.0f} m3; held {held:.0f} m3 ({100 * frac:.1f}%)'
    )


if __name__ == '__main__':
    main()
