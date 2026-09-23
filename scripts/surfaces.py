"""
C20.1 — buildable vs gathering surfaces (bands, not a top-three cut).

  buildable — C19 gathers renamed; canopy + 3 m still excludes (foundations).
  gathering — canopy earns shade points; trunks exclude at 1.5 m only.

    python scripts/surfaces.py
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
from PIL import Image
from scipy import ndimage
from shapely.geometry import Point, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR, sample_dem, parcel_window, write_grid  # noqa: E402
from terrain import en_to_lnglat, lnglat_to_en  # noqa: E402

# C19 weights — unchanged for buildable (must sum to 1)
WEIGHTS_BUILDABLE = {
    'sun_hours_annual': 0.18,
    'sun_hours_dec': 0.12,
    'cold_air_inv': 0.12,
    'thermal_belt': 0.08,
    'twi_inv': 0.10,
    'stormwater_inv': 0.08,
    'wind_santa_ana_inv': 0.10,
    'wind_sea_breeze': 0.04,
    'slope': 0.12,
    'landform': 0.06,
}
assert abs(sum(WEIGHTS_BUILDABLE.values()) - 1.0) < 1e-9

# Gathering: shade under canopy earns points (esp. with December sun)
WEIGHTS_GATHERING = {
    'sun_hours_annual': 0.12,
    'sun_hours_dec': 0.10,
    'cold_air_inv': 0.10,
    'thermal_belt': 0.06,
    'twi_inv': 0.08,
    'stormwater_inv': 0.06,
    'wind_santa_ana_inv': 0.08,
    'wind_sea_breeze': 0.04,
    'slope': 0.10,
    'landform': 0.06,
    'shade': 0.20,
}
assert abs(sum(WEIGHTS_GATHERING.values()) - 1.0) < 1e-9

NODATA = 65535
CREEK_BUFFER_M = 15.0
BOUNDARY_BUFFER_M = 5.0
TREE_EXTRA_M = 3.0
TRUNK_R_M = 1.5
CORRIDOR_TOP_DECILE = 0.9
MIN_POLY_M2 = 100.0
BAND_BEST = 0.67
BAND_GOOD = 0.33
WORKABLE_THR = 0.05  # on rescaled 0–1 survivors
M2_PER_ACRE = 4046.8564224


def load_grid(name: str):
    z = np.load(GRID_DIR / f'{name}.npz')
    return np.asarray(z['data'], dtype=np.float64), np.asarray(z['es']), np.asarray(z['ns'])


def norm01(a: np.ndarray, invert=False):
    out = np.full_like(a, np.nan, dtype=np.float64)
    m = np.isfinite(a)
    if not m.any():
        return out
    lo, hi = float(np.nanmin(a[m])), float(np.nanmax(a[m]))
    if hi <= lo:
        out[m] = 0.5
    else:
        out[m] = (a[m] - lo) / (hi - lo)
    if invert:
        out[m] = 1.0 - out[m]
    return out


def slope_score(Z: np.ndarray, step: float = 1.0):
    gy, gx = np.gradient(Z, step)
    deg = np.degrees(np.arctan(np.hypot(gx, gy)))
    s = np.zeros_like(deg)
    s[deg <= 8] = 1.0
    mid = (deg > 8) & (deg <= 20)
    s[mid] = 1.0 - (deg[mid] - 8.0) / 12.0
    s[deg > 20] = 0.0
    s[~np.isfinite(Z)] = np.nan
    return s, deg


def landform_score(lf: np.ndarray):
    score_map = {1: 0.55, 2: 0.7, 3: 0.85, 4: 1.0, 5: 0.45, 6: 0.15}
    out = np.full_like(lf, np.nan, dtype=np.float64)
    m = np.isfinite(lf)
    for k, v in score_map.items():
        out[m & (np.round(lf) == k)] = v
    return out


def thermal_belt_mask(es, ns, shape_hw):
    path = ROOT / 'thermal-belt.geojson'
    mask = np.zeros(shape_hw, dtype=bool)
    if not path.exists():
        return mask
    doc = json.loads(path.read_text(encoding='utf-8'))
    rows, cols = shape_hw
    for f in doc.get('features') or []:
        g = f.get('geometry') or {}
        if g.get('type') == 'MultiPoint':
            for lng, lat in g['coordinates']:
                e, n = lnglat_to_en(lng, lat)
                j = int(round((e - es[0]) / 1.0))
                i = int(round((n - ns[0]) / 1.0))
                if 0 <= i < rows and 0 <= j < cols:
                    mask[i, j] = True
    if mask.any():
        mask = ndimage.binary_dilation(mask, iterations=8)
    return mask


def tree_masks(es, ns, rows, cols):
    """crown+3m (buildable excl), trunk 1.5 m, and shade under crown (no extra buffer)."""
    crown = np.zeros((rows, cols), dtype=bool)
    trunk = np.zeros((rows, cols), dtype=bool)
    shade = np.zeros((rows, cols), dtype=bool)
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            e = float(row['x_east_dm']) / 10.0
            n = float(row['y_north_dm']) / 10.0
            if e < es[0] - 20 or e > es[-1] + 20 or n < ns[0] - 20 or n > ns[-1] + 20:
                continue
            r_crown = float(row.get('crown_radius_dm') or 30) / 10.0
            r_build = r_crown + TREE_EXTRA_M
            for mask, r in ((trunk, TRUNK_R_M), (shade, r_crown), (crown, r_build)):
                j0 = max(0, int((e - r - es[0])))
                j1 = min(cols - 1, int((e + r - es[0])) + 1)
                i0 = max(0, int((n - r - ns[0])))
                i1 = min(rows - 1, int((n + r - ns[0])) + 1)
                if j1 < j0 or i1 < i0:
                    continue
                jj = np.arange(j0, j1 + 1)
                ii = np.arange(i0, i1 + 1)
                if jj.size == 0 or ii.size == 0:
                    continue
                J, I = np.meshgrid(jj, ii)
                hit = (es[J] - e) ** 2 + (ns[I] - n) ** 2 <= r * r
                mask[i0:i1 + 1, j0:j1 + 1] |= hit
    return crown, trunk, shade


def shared_exclusions(es, ns, Z, storm, corridor, slope_deg):
    """Creek, easement, boundary, corridor, footprints, flood, steep — no trees."""
    rows, cols = Z.shape
    excl = np.zeros((rows, cols), dtype=bool)
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    boundary = shape(survey['features'][0]['geometry'])

    def ll_poly(g):
        if g.geom_type == 'Polygon':
            return Polygon([lnglat_to_en(x, y) for x, y in g.exterior.coords])
        if g.geom_type == 'MultiPolygon':
            return unary_union([ll_poly(p) for p in g.geoms])
        return g

    b_en = ll_poly(boundary)
    inner = b_en.buffer(-BOUNDARY_BUFFER_M)
    easements = []
    for f in survey['features']:
        name = ((f.get('properties') or {}).get('name') or '').lower()
        if 'easement' in name:
            easements.append(shape(f['geometry']))
    easement_en = unary_union([ll_poly(e).buffer(2.5) for e in easements]) if easements else None

    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    creek = next(m for m in man['models'] if m['id'] == 'creek')
    creek_poly = Polygon([lnglat_to_en(a, b) for a, b in creek['footprint']]).buffer(CREEK_BUFFER_M)
    model_polys = []
    for m in man['models']:
        if m['id'] == 'site-grounds' or not m.get('footprint'):
            continue
        try:
            model_polys.append(Polygon([lnglat_to_en(a, b) for a, b in m['footprint']]))
        except Exception:
            pass
    models_u = unary_union(model_polys) if model_polys else None

    from shapely import vectorized
    EE, NN = np.meshgrid(es, ns)
    excl |= ~vectorized.contains(b_en, EE, NN)
    if inner is not None and not inner.is_empty:
        excl |= ~vectorized.contains(inner, EE, NN)
    if easement_en is not None and not easement_en.is_empty:
        excl |= vectorized.contains(easement_en, EE, NN)
    excl |= vectorized.contains(creek_poly, EE, NN)
    if models_u is not None and not models_u.is_empty:
        excl |= vectorized.contains(models_u, EE, NN)

    cfin = corridor[np.isfinite(corridor)]
    c_thr = float(np.quantile(cfin, CORRIDOR_TOP_DECILE)) if cfin.size else np.inf
    excl |= np.isfinite(corridor) & (corridor >= c_thr)

    sfin = storm[np.isfinite(storm) & (storm > 0)]
    s_thr = max(0.02, float(np.quantile(sfin, 0.85))) if sfin.size else 0.02
    excl |= np.isfinite(storm) & (storm >= s_thr)
    excl |= np.isfinite(slope_deg) & (slope_deg > 20)

    return excl, b_en, {
        'creek_buffer_m': CREEK_BUFFER_M,
        'boundary_buffer_m': BOUNDARY_BUFFER_M,
        'corridor_quantile': CORRIDOR_TOP_DECILE,
        'stormwater_flood_m': s_thr,
    }


def export_raster(name, data, es, ns, units, extra):
    write_grid(name, data, es, ns, extra)
    meta = json.loads((GRID_DIR / f'{name}.json').read_text(encoding='utf-8'))
    cell = float(meta['cell_m'])
    e_w, e_e = float(es[0] - cell / 2), float(es[-1] + cell / 2)
    n_s, n_n = float(ns[0] - cell / 2), float(ns[-1] + cell / 2)
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    fr = pack['frame']
    wlng, slat = en_to_lnglat(e_w, n_s)
    elng, nlat = en_to_lnglat(e_e, n_n)
    meta.update({
        'frame_origin_lng': fr['origin_lng'],
        'frame_origin_lat': fr['origin_lat'],
        'metres_per_deg_lng': fr['metres_per_deg_lng'],
        'metres_per_deg_lat': fr['metres_per_deg_lat'],
        'units': units,
        'encoding': 'uint16_greyscale',
        'nodata': NODATA,
        'row_order': 'north_to_south',
        'col_order': 'west_to_east',
        'bounds_en_m': [e_w, n_s, e_e, n_n],
        'bounds_lnglat': [round(wlng, 7), round(slat, 7), round(elng, 7), round(nlat, 7)],
        'raster': f'analysis/grids/{name}.png',
        **extra,
    })
    finite = np.isfinite(data)
    vmin = float(np.nanmin(data[finite])) if finite.any() else 0.0
    vmax = float(np.nanmax(data[finite])) if finite.any() else 1.0
    if vmax <= vmin:
        vmax = vmin + 1e-9
    meta['value_min'] = vmin
    meta['value_max'] = vmax
    meta['decode'] = (
        f'if pixel == {NODATA}: nodata; else '
        f'value = value_min + (pixel / 65534) * (value_max - value_min)'
    )
    scaled = np.full(data.shape, NODATA, dtype=np.uint16)
    scaled[finite] = np.clip(
        np.round((data[finite] - vmin) / (vmax - vmin) * 65534.0), 0, 65534,
    ).astype(np.uint16)
    Image.fromarray(np.flipud(scaled), mode='I;16').save(GRID_DIR / f'{name}.png')
    (GRID_DIR / f'{name}.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    return meta


REASON_WORDS = {
    'sun_hours_annual': 'sunny through the year',
    'sun_hours_dec': 'holds December sun',
    'cold_air_inv': 'out of the frost pools',
    'thermal_belt': 'on the warm mid-slope belt',
    'twi_inv': 'dry underfoot',
    'stormwater_inv': 'sheds stormwater',
    'wind_santa_ana_inv': 'sheltered from Santa Anas',
    'wind_sea_breeze': 'catches a light sea breeze',
    'slope': 'gentle ground',
    'landform': 'a buildable landform',
    'shade': 'under the oaks with summer shade',
}


def reasons_for_cell(parts: dict, i, j):
    ranked = sorted(
        ((k, float(v[i, j])) for k, v in parts.items() if np.isfinite(v[i, j])),
        key=lambda t: -t[1],
    )[:3]
    return [REASON_WORDS.get(k, k) for k, _ in ranked]


def band_name(score: float) -> str:
    if score >= BAND_BEST:
        return 'best'
    if score >= BAND_GOOD:
        return 'good'
    return 'workable'


def polygons_banded(score, usable, es, ns, parts, b_en):
    """Contiguous regions per band above WORKABLE_THR on rescaled score."""
    features = []
    half = 0.5
    for band, lo, hi in (
        ('best', BAND_BEST, 1.01),
        ('good', BAND_GOOD, BAND_BEST),
        ('workable', WORKABLE_THR, BAND_GOOD),
    ):
        mask = usable & (score >= lo) & (score < hi)
        closed = ndimage.binary_closing(mask, structure=np.ones((3, 3))) & usable
        labeled, nlab = ndimage.label(closed)
        buckets = []
        for lab in range(1, nlab + 1):
            cells = labeled == lab
            area = float(cells.sum())
            if area < MIN_POLY_M2:
                continue
            core = cells & mask
            mean_s = float(np.nanmean(score[core])) if core.any() else float(np.nanmean(score[cells]))
            ys, xs = np.where(cells)
            geom = unary_union([
                Polygon([
                    (float(es[j]) - half, float(ns[i]) - half),
                    (float(es[j]) + half, float(ns[i]) - half),
                    (float(es[j]) + half, float(ns[i]) + half),
                    (float(es[j]) - half, float(ns[i]) + half),
                ])
                for i, j in zip(ys, xs)
            ])
            if geom.is_empty:
                continue
            if geom.geom_type == 'MultiPolygon':
                geom = max(geom.geoms, key=lambda g: g.area)
            geom = geom.buffer(0)
            if not b_en.contains(geom.centroid):
                continue
            c = geom.centroid
            j = int(np.clip(round((c.x - es[0])), 0, len(es) - 1))
            i = int(np.clip(round((c.y - ns[0])), 0, len(ns) - 1))
            buckets.append((mean_s, area, geom, reasons_for_cell(parts, i, j), band))
        buckets.sort(key=lambda t: (-t[0], -t[1]))
        features.extend(buckets)

    # global rank by score then area
    features.sort(key=lambda t: (-t[0], -t[1]))
    out = []
    for rank, (mean_s, area, geom, reasons, band) in enumerate(features, start=1):
        if geom.geom_type == 'Polygon':
            geometry = {
                'type': 'Polygon',
                'coordinates': [[list(en_to_lnglat(x, y)) for x, y in geom.exterior.coords]],
            }
        else:
            geometry = {
                'type': 'MultiPolygon',
                'coordinates': [
                    [[list(en_to_lnglat(x, y)) for x, y in p.exterior.coords]] for p in geom.geoms
                ],
            }
        out.append({
            'type': 'Feature',
            'properties': {
                'rank': rank,
                'band': band,
                'score': round(mean_s, 4),
                'area_m2': round(area, 1),
                'reasons': reasons,
            },
            'geometry': geometry,
        })
    return out


def rescale_survivors(raw, usable):
    """Map usable raw scores onto full 0–1; excluded stay 0 / nan."""
    out = np.zeros_like(raw, dtype=np.float64)
    out[~np.isfinite(raw)] = np.nan
    if not usable.any():
        return out
    lo = float(np.nanmin(raw[usable]))
    hi = float(np.nanmax(raw[usable]))
    if hi <= lo:
        out[usable] = 0.5
    else:
        out[usable] = (raw[usable] - lo) / (hi - lo)
    out[~usable & np.isfinite(raw)] = 0.0
    return out


def score_parts_buildable(sun_a, sun_d, cold, belt, twi, storm, w_sa, w_sb, slope_s, lf):
    return {
        'sun_hours_annual': norm01(sun_a) * WEIGHTS_BUILDABLE['sun_hours_annual'],
        'sun_hours_dec': norm01(sun_d) * WEIGHTS_BUILDABLE['sun_hours_dec'],
        'cold_air_inv': norm01(cold, invert=True) * WEIGHTS_BUILDABLE['cold_air_inv'],
        'thermal_belt': belt.astype(float) * WEIGHTS_BUILDABLE['thermal_belt'],
        'twi_inv': norm01(twi, invert=True) * WEIGHTS_BUILDABLE['twi_inv'],
        'stormwater_inv': norm01(storm, invert=True) * WEIGHTS_BUILDABLE['stormwater_inv'],
        'wind_santa_ana_inv': norm01(w_sa, invert=True) * WEIGHTS_BUILDABLE['wind_santa_ana_inv'],
        'wind_sea_breeze': norm01(w_sb) * WEIGHTS_BUILDABLE['wind_sea_breeze'],
        'slope': slope_s * WEIGHTS_BUILDABLE['slope'],
        'landform': landform_score(lf) * WEIGHTS_BUILDABLE['landform'],
    }


def score_parts_gathering(sun_a, sun_d, cold, belt, twi, storm, w_sa, w_sb, slope_s, lf, shade_mask):
    # shade: under crown, boosted where December sun still reaches
    dec = norm01(sun_d)
    shade = np.zeros_like(sun_a, dtype=np.float64)
    shade[shade_mask] = 0.45 + 0.55 * np.nan_to_num(dec[shade_mask], nan=0.0)
    return {
        'sun_hours_annual': norm01(sun_a) * WEIGHTS_GATHERING['sun_hours_annual'],
        'sun_hours_dec': norm01(sun_d) * WEIGHTS_GATHERING['sun_hours_dec'],
        'cold_air_inv': norm01(cold, invert=True) * WEIGHTS_GATHERING['cold_air_inv'],
        'thermal_belt': belt.astype(float) * WEIGHTS_GATHERING['thermal_belt'],
        'twi_inv': norm01(twi, invert=True) * WEIGHTS_GATHERING['twi_inv'],
        'stormwater_inv': norm01(storm, invert=True) * WEIGHTS_GATHERING['stormwater_inv'],
        'wind_santa_ana_inv': norm01(w_sa, invert=True) * WEIGHTS_GATHERING['wind_santa_ana_inv'],
        'wind_sea_breeze': norm01(w_sb) * WEIGHTS_GATHERING['wind_sea_breeze'],
        'slope': slope_s * WEIGHTS_GATHERING['slope'],
        'landform': landform_score(lf) * WEIGHTS_GATHERING['landform'],
        'shade': shade * WEIGHTS_GATHERING['shade'],
    }


def combine(parts):
    score = np.zeros(next(iter(parts.values())).shape, dtype=np.float64)
    for v in parts.values():
        score = np.nansum(np.dstack([score, np.nan_to_num(v, nan=0.0)]), axis=2)
    return score


def band_areas(score, usable):
    areas = {}
    for band, lo, hi in (
        ('best', BAND_BEST, 1.01),
        ('good', BAND_GOOD, BAND_BEST),
        ('workable', WORKABLE_THR, BAND_GOOD),
    ):
        m = usable & (score >= lo) & (score < hi)
        areas[band] = int(m.sum())
    areas['total_above_workable'] = sum(areas.values())
    return areas


def write_geojson(name, features, weights, extra_props=None):
    geo = {
        'type': 'FeatureCollection',
        'properties': {
            'authority': 'derived',
            'evidence': 'modelled',
            'weights': weights,
            'bands': {'best': f'>={BAND_BEST}', 'good': f'>={BAND_GOOD}', 'workable': f'>={WORKABLE_THR}'},
            'generator': 'scripts/surfaces.py',
            **(extra_props or {}),
        },
        'features': features,
    }
    (ROOT / f'{name}.geojson').write_text(json.dumps(geo, indent=2) + '\n', encoding='utf-8')


def figure_surface(name, score, usable, Z, es, ns, b_en, features, title):
    fig, ax = plt.subplots(figsize=(10, 8))
    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.hillshade(np.nan_to_num(Z, nan=np.nanmean(Z)), vert_exag=2, dx=1, dy=1)
    ax.imshow(rgb, origin='lower', extent=[es[0], es[-1], ns[0], ns[-1]], cmap='gray')
    sc = np.ma.array(score, mask=~usable)
    im = ax.imshow(sc, origin='lower', extent=[es[0], es[-1], ns[0], ns[-1]],
                   cmap='YlGn', alpha=0.55, vmin=0, vmax=1)
    bx, by = b_en.exterior.xy
    ax.plot(bx, by, color='black', lw=1.2)
    colors = {'best': '#1b5e20', 'good': '#558b2f', 'workable': '#9e9d24'}
    for f in features[:40]:
        g = shape(f['geometry'])
        band = f['properties']['band']
        if g.geom_type != 'Polygon':
            continue
        xs, ys = zip(*[lnglat_to_en(a, b) for a, b in g.exterior.coords])
        ax.plot(xs, ys, color=colors.get(band, '#b71c1c'), lw=1.0)
    fig.colorbar(im, ax=ax, shrink=0.7, label=f'{name} score (rescaled)')
    ax.set_aspect('equal')
    ax.set_title(title)
    ax.set_xlabel('east m')
    ax.set_ylabel('north m')
    fig.tight_layout()
    fig.savefig(ROOT / 'analysis' / f'{name}-figure.png', dpi=150)
    plt.close(fig)


def main():
    for n in ('twi', 'stormwater_depth', 'sun_hours_annual', 'sun_hours_dec',
              'cold_air', 'wind_santa_ana', 'wind_sea_breeze', 'corridors', 'landforms'):
        if not (GRID_DIR / f'{n}.npz').exists():
            raise SystemExit(f'missing {n}.npz')

    twi, es, ns = load_grid('twi')
    storm, _, _ = load_grid('stormwater_depth')
    sun_a, _, _ = load_grid('sun_hours_annual')
    sun_d, _, _ = load_grid('sun_hours_dec')
    cold, _, _ = load_grid('cold_air')
    w_sa, _, _ = load_grid('wind_santa_ana')
    w_sb, _, _ = load_grid('wind_sea_breeze')
    corr, _, _ = load_grid('corridors')
    lf, _, _ = load_grid('landforms')

    _, e0, n0, e1, n1 = parcel_window(30)
    _, _, Z = sample_dem(e0, n0, e1, n1)
    if Z.shape != twi.shape:
        raise SystemExit(f'DEM shape {Z.shape} != grid {twi.shape}')

    slope_s, slope_deg = slope_score(Z)
    belt = thermal_belt_mask(es, ns, twi.shape)
    rows, cols = twi.shape
    crown_excl, trunk_excl, shade_mask = tree_masks(es, ns, rows, cols)
    shared, b_en, excl_meta = shared_exclusions(es, ns, Z, storm, corr, slope_deg)

    from shapely import vectorized
    EE, NN = np.meshgrid(es, ns)
    in_parcel = vectorized.contains(b_en, EE, NN)

    # --- buildable (C19 gathers) ---
    excl_b = shared | crown_excl
    parts_b = score_parts_buildable(sun_a, sun_d, cold, belt, twi, storm, w_sa, w_sb, slope_s, lf)
    raw_b = combine(parts_b)
    raw_b[excl_b] = 0.0
    raw_b[~np.isfinite(twi)] = np.nan
    survivors_b = (~excl_b) & np.isfinite(raw_b) & (raw_b > 0)
    score_b = rescale_survivors(raw_b, survivors_b)
    usable_b = (~excl_b) & np.isfinite(score_b) & (score_b >= WORKABLE_THR)

    meta_b = export_raster(
        'buildable', score_b, es, ns, 'score 0-1',
        {
            'evidence': 'modelled', 'authority': 'derived',
            'method': 'C19 weighted overlay; canopy+3m excluded (foundations)',
            'weights': WEIGHTS_BUILDABLE, 'weights_sum': sum(WEIGHTS_BUILDABLE.values()),
            'exclusions': {**excl_meta, 'tree_extra_m': TREE_EXTRA_M, 'canopy': True},
            'bands': {'best': BAND_BEST, 'good': BAND_GOOD, 'workable': WORKABLE_THR},
            'what': 'where a structure could stand',
            'alias_of': None,
        },
    )
    # gathers alias — identical bytes/meta note
    export_raster(
        'gathers', score_b, es, ns, 'score 0-1',
        {
            'evidence': 'modelled', 'authority': 'derived',
            'method': 'alias of buildable for one phase (C20)',
            'weights': WEIGHTS_BUILDABLE, 'weights_sum': sum(WEIGHTS_BUILDABLE.values()),
            'exclusions': {**excl_meta, 'tree_extra_m': TREE_EXTRA_M, 'canopy': True},
            'bands': {'best': BAND_BEST, 'good': BAND_GOOD, 'workable': WORKABLE_THR},
            'what': 'alias of buildable — where a structure could stand',
            'alias_of': 'buildable',
        },
    )

    feats_b = polygons_banded(score_b, usable_b, es, ns, parts_b, b_en)
    write_geojson('buildable', feats_b, WEIGHTS_BUILDABLE)
    # gathers.geojson alias
    write_geojson('gathers', feats_b, WEIGHTS_BUILDABLE, {'alias_of': 'buildable'})
    figure_surface('buildable', score_b, usable_b, Z, es, ns, b_en, feats_b,
                   'Buildable (C20) — canopy excluded')
    # gathers figure alias
    import shutil
    shutil.copy(
        ROOT / 'analysis' / 'buildable-figure.png',
        ROOT / 'analysis' / 'gathers-figure.png',
    )

    # --- gathering ---
    excl_g = shared | trunk_excl
    parts_g = score_parts_gathering(
        sun_a, sun_d, cold, belt, twi, storm, w_sa, w_sb, slope_s, lf, shade_mask,
    )
    raw_g = combine(parts_g)
    raw_g[excl_g] = 0.0
    raw_g[~np.isfinite(twi)] = np.nan
    survivors_g = (~excl_g) & np.isfinite(raw_g) & (raw_g > 0)
    score_g = rescale_survivors(raw_g, survivors_g)
    usable_g = (~excl_g) & np.isfinite(score_g) & (score_g >= WORKABLE_THR)

    export_raster(
        'gathering', score_g, es, ns, 'score 0-1',
        {
            'evidence': 'modelled', 'authority': 'derived',
            'method': 'weighted overlay; canopy earns shade; trunks exclude 1.5 m',
            'weights': WEIGHTS_GATHERING, 'weights_sum': sum(WEIGHTS_GATHERING.values()),
            'exclusions': {**excl_meta, 'trunk_radius_m': TRUNK_R_M, 'canopy': False},
            'bands': {'best': BAND_BEST, 'good': BAND_GOOD, 'workable': WORKABLE_THR},
            'what': 'where people would want to gather (oaks welcome)',
        },
    )
    feats_g = polygons_banded(score_g, usable_g, es, ns, parts_g, b_en)
    write_geojson('gathering', feats_g, WEIGHTS_GATHERING)
    figure_surface('gathering', score_g, usable_g, Z, es, ns, b_en, feats_g,
                   'Gathering (C20) — shade under oaks earns points')

    # open-ground headline for buildable
    open_cells = int((in_parcel & usable_b).sum()) if usable_b.any() else int((~excl_b & in_parcel).sum())
    # "open ground" = in parcel and not excluded by buildable mask (surviving population before band cut)
    open_ground = int((in_parcel & ~excl_b & np.isfinite(twi)).sum())
    parcel_cells = int(in_parcel.sum())
    areas_b = band_areas(score_b, usable_b & in_parcel)
    areas_g = band_areas(score_g, usable_g & in_parcel)

    # proof cell under large oak crown, away from trunk
    under = shade_mask & ~trunk_excl & in_parcel & crown_excl  # in canopy+3m = buildable zero
    # prefer large shade with high gathering score
    cand = under & np.isfinite(score_g)
    proof = None
    if cand.any():
        # pick high gathering among under-crown
        ys, xs = np.where(cand)
        best = int(np.argmax(score_g[ys, xs]))
        i, j = int(ys[best]), int(xs[best])
        proof = {
            'e': float(es[j]), 'n': float(ns[i]), 'i': i, 'j': j,
            'buildable': float(score_b[i, j]),
            'gathering': float(score_g[i, j]),
            'excl_buildable': bool(excl_b[i, j]),
            'excl_gathering': bool(excl_g[i, j]),
            'under_crown': True, 'near_trunk': bool(trunk_excl[i, j]),
        }
    # trunk-near cell
    near_trunk = None
    if trunk_excl.any():
        ys, xs = np.where(trunk_excl & in_parcel)
        if ys.size:
            i, j = int(ys[0]), int(xs[0])
            near_trunk = {
                'e': float(es[j]), 'n': float(ns[i]),
                'buildable': float(score_b[i, j]) if np.isfinite(score_b[i, j]) else 0.0,
                'gathering': float(score_g[i, j]) if np.isfinite(score_g[i, j]) else 0.0,
            }

    summary = {
        'parcel_cells': parcel_cells,
        'parcel_acres': round(parcel_cells / M2_PER_ACRE, 2),
        'open_ground_buildable_cells': open_ground,
        'open_ground_buildable_acres': round(open_ground / M2_PER_ACRE, 2),
        'buildable_band_m2': areas_b,
        'gathering_band_m2': areas_g,
        'buildable_range': {
            'min': float(np.nanmin(score_b[survivors_b])) if survivors_b.any() else None,
            'max': float(np.nanmax(score_b[survivors_b])) if survivors_b.any() else None,
        },
        'gathering_range': {
            'min': float(np.nanmin(score_g[survivors_g])) if survivors_g.any() else None,
            'max': float(np.nanmax(score_g[survivors_g])) if survivors_g.any() else None,
        },
        'proof_oak_cell': proof,
        'proof_trunk_cell': near_trunk,
        'weights_buildable': WEIGHTS_BUILDABLE,
        'weights_gathering': WEIGHTS_GATHERING,
    }
    (ROOT / 'analysis' / 'surfaces-summary.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8',
    )
    print(
        f'OK surfaces: open_buildable={open_ground} m2 '
        f'({open_ground / M2_PER_ACRE:.2f} ac of {parcel_cells / M2_PER_ACRE:.2f}); '
        f'buildable bands={areas_b}; gathering bands={areas_g}'
    )
    if proof:
        print(
            f"  oak proof EN ({proof['e']:.0f},{proof['n']:.0f}): "
            f"buildable={proof['buildable']:.3f} gathering={proof['gathering']:.3f}"
        )


if __name__ == '__main__':
    main()
