"""
C19.2 — where the land gathers (weighted overlay on the pack 1 m grid).

    python scripts/gathers.py
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
from shapely.geometry import MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import GRID_DIR, sample_dem, parcel_window, write_grid  # noqa: E402
from terrain import en_to_lnglat, lnglat_to_en  # noqa: E402

# Weights — must sum to 1.0 (recorded in gathers.json and C19-done.md)
WEIGHTS = {
    'sun_hours_annual': 0.18,
    'sun_hours_dec': 0.12,
    'cold_air_inv': 0.12,       # frost pooling loses
    'thermal_belt': 0.08,
    'twi_inv': 0.10,            # dry underfoot
    'stormwater_inv': 0.08,
    'wind_santa_ana_inv': 0.10, # Santa Ana exposure loses
    'wind_sea_breeze': 0.04,
    'slope': 0.12,
    'landform': 0.06,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

NODATA = 65535
CREEK_BUFFER_M = 15.0
BOUNDARY_BUFFER_M = 5.0
TREE_EXTRA_M = 3.0
CORRIDOR_TOP_DECILE = 0.9
MIN_POLY_M2 = 100.0
PCTILE = 85.0


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
    # 1 ridge 2 upper 3 mid 4 flat 5 lower 6 valley
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
        elif g.get('type') == 'Polygon':
            poly = shape(g)
            minx, miny, maxx, maxy = poly.bounds
            j0 = max(0, int((lnglat_to_en(minx, miny)[0] - es[0])))
            # slow path — use points already
            pass
    # dilate sparse multipoint into a band
    if mask.any():
        mask = ndimage.binary_dilation(mask, iterations=8)
    return mask


def hard_exclusions(es, ns, Z, storm, corridor, slope_deg):
    rows, cols = Z.shape
    excl = np.zeros((rows, cols), dtype=bool)

    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    boundary = shape(survey['features'][0]['geometry'])
    easements = []
    for f in survey['features']:
        props = f.get('properties') or {}
        name = (props.get('name') or '').lower()
        if 'easement' in name:
            easements.append(shape(f['geometry']))

    def ll_poly(g):
        if g.geom_type == 'Polygon':
            return Polygon([lnglat_to_en(x, y) for x, y in g.exterior.coords])
        if g.geom_type == 'MultiPolygon':
            return unary_union([ll_poly(p) for p in g.geoms])
        return g

    b_en = ll_poly(boundary)
    inner = b_en.buffer(-BOUNDARY_BUFFER_M)
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

    # Rasterize polygons onto the grid (centres)
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

    tree_mask = np.zeros((rows, cols), dtype=bool)
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            e = float(row['x_east_dm']) / 10.0
            n = float(row['y_north_dm']) / 10.0
            if e < es[0] - 20 or e > es[-1] + 20 or n < ns[0] - 20 or n > ns[-1] + 20:
                continue
            r = float(row.get('crown_radius_dm') or 30) / 10.0 + TREE_EXTRA_M
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
            tree_mask[i0:i1 + 1, j0:j1 + 1] |= hit
    excl |= tree_mask

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
        'tree_extra_m': TREE_EXTRA_M,
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
        'bounds_lnglat': [
            round(wlng, 7), round(slat, 7), round(elng, 7), round(nlat, 7),
        ],
        'raster': f'analysis/grids/{name}.png',
        **extra,
    })
    finite = np.isfinite(data)
    vmin, vmax = float(np.nanmin(data[finite])), float(np.nanmax(data[finite]))
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


def reasons_for_cell(parts: dict, i, j):
    # three strongest positive contributions
    ranked = sorted(
        ((k, float(v[i, j])) for k, v in parts.items() if np.isfinite(v[i, j])),
        key=lambda t: -t[1],
    )[:3]
    words = {
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
    }
    return [words.get(k, k) for k, _ in ranked]


def polygons_from_mask(mask, es, ns, score, parts, keep):
    """Contiguous top-percentile cells → ranked polygons.

    One-cell gaps are closed morphologically so fragmented benches become
    real areas; closing never expands into excluded / non-usable cells.
    """
    closed = ndimage.binary_closing(mask, structure=np.ones((3, 3)))
    closed &= keep
    labeled, nlab = ndimage.label(closed)
    ranks = []
    half = 0.5
    for lab in range(1, nlab + 1):
        cells = labeled == lab
        area = float(cells.sum())  # 1 m cells
        if area < MIN_POLY_M2:
            continue
        # score from original high cells only (ignore gap-fill)
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
        c = geom.centroid
        j = int(np.clip(round((c.x - es[0])), 0, len(es) - 1))
        i = int(np.clip(round((c.y - ns[0])), 0, len(ns) - 1))
        ranks.append((mean_s, area, geom, reasons_for_cell(parts, i, j)))

    ranks.sort(key=lambda t: (-t[0], -t[1]))
    features = []
    for rank, (mean_s, area, geom, reasons) in enumerate(ranks, start=1):
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
        features.append({
            'type': 'Feature',
            'properties': {
                'rank': rank,
                'score': round(mean_s, 4),
                'area_m2': round(area, 1),
                'reasons': reasons,
            },
            'geometry': geometry,
        })
    return features


def main():
    # ensure inputs exist
    for n in ('twi', 'stormwater_depth', 'sun_hours_annual', 'sun_hours_dec',
              'cold_air', 'wind_santa_ana', 'wind_sea_breeze', 'corridors', 'landforms'):
        if not (GRID_DIR / f'{n}.npz').exists():
            raise SystemExit(f'missing {n}.npz — run land_layers / export first')

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
    # align if shapes differ
    if Z.shape != twi.shape:
        raise SystemExit(f'DEM shape {Z.shape} != grid {twi.shape}')

    slope_s, slope_deg = slope_score(Z)
    belt = thermal_belt_mask(es, ns, twi.shape)

    parts = {
        'sun_hours_annual': norm01(sun_a) * WEIGHTS['sun_hours_annual'],
        'sun_hours_dec': norm01(sun_d) * WEIGHTS['sun_hours_dec'],
        'cold_air_inv': norm01(cold, invert=True) * WEIGHTS['cold_air_inv'],
        'thermal_belt': belt.astype(float) * WEIGHTS['thermal_belt'],
        'twi_inv': norm01(twi, invert=True) * WEIGHTS['twi_inv'],
        'stormwater_inv': norm01(storm, invert=True) * WEIGHTS['stormwater_inv'],
        'wind_santa_ana_inv': norm01(w_sa, invert=True) * WEIGHTS['wind_santa_ana_inv'],
        'wind_sea_breeze': norm01(w_sb) * WEIGHTS['wind_sea_breeze'],
        'slope': slope_s * WEIGHTS['slope'],
        'landform': landform_score(lf) * WEIGHTS['landform'],
    }
    score = np.zeros_like(twi, dtype=np.float64)
    for v in parts.values():
        score = np.nansum(np.dstack([score, np.nan_to_num(v, nan=0.0)]), axis=2)

    excl, b_en, excl_meta = hard_exclusions(es, ns, Z, storm, corr, slope_deg)
    score[excl] = 0.0
    score[~np.isfinite(twi)] = np.nan

    # ranked mask: above 85th percentile among non-excluded positive cells
    usable = (~excl) & np.isfinite(score) & (score > 0)
    thr = float(np.percentile(score[usable], PCTILE)) if usable.any() else 1.0
    gather_mask = usable & (score >= thr)

    meta = export_raster(
        'gathers', score, es, ns, 'score 0-1',
        {
            'evidence': 'modelled',
            'authority': 'derived',
            'method': 'weighted overlay of C16 land-reading layers with hard exclusions',
            'weights': WEIGHTS,
            'weights_sum': sum(WEIGHTS.values()),
            'percentile_threshold': PCTILE,
            'score_threshold': thr,
            'exclusions': excl_meta,
            'what': 'where the land gathers — ranked suitability',
            'closing': '3x3 binary_closing on 85th-percentile mask, clipped to usable cells',
        },
    )

    features = polygons_from_mask(gather_mask, es, ns, score, parts, usable)

    # filter: inside boundary, >= 100 m2
    kept = []
    for f in features:
        g = shape(f['geometry'])
        # convert to EN for containment
        if g.geom_type == 'Polygon':
            gen = Polygon([lnglat_to_en(x, y) for x, y in g.exterior.coords])
        else:
            gen = unary_union([
                Polygon([lnglat_to_en(x, y) for x, y in p.exterior.coords]) for p in g.geoms
            ])
        if f['properties']['area_m2'] < MIN_POLY_M2:
            continue
        if not b_en.contains(gen.centroid):
            continue
        kept.append(f)
    for i, f in enumerate(kept, start=1):
        f['properties']['rank'] = i

    geo = {
        'type': 'FeatureCollection',
        'properties': {
            'authority': 'derived',
            'evidence': 'modelled',
            'weights': WEIGHTS,
            'score_threshold': thr,
            'generator': 'scripts/gathers.py',
        },
        'features': kept,
    }
    (ROOT / 'gathers.geojson').write_text(json.dumps(geo, indent=2) + '\n', encoding='utf-8')

    # report figure
    fig, ax = plt.subplots(figsize=(10, 8))
    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.hillshade(np.nan_to_num(Z, nan=np.nanmean(Z)), vert_exag=2, dx=1, dy=1)
    ax.imshow(rgb, origin='lower', extent=[es[0], es[-1], ns[0], ns[-1]], cmap='gray')
    sc = np.ma.array(score, mask=~usable)
    im = ax.imshow(
        sc, origin='lower', extent=[es[0], es[-1], ns[0], ns[-1]],
        cmap='YlGn', alpha=0.55, vmin=0, vmax=max(thr * 1.2, float(np.nanmax(score[usable]) if usable.any() else 1)),
    )
    # boundary + easement
    bx, by = b_en.exterior.xy
    ax.plot(bx, by, color='black', lw=1.2)
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    for f in survey['features']:
        props = f.get('properties') or {}
        if 'easement' not in (props.get('name') or '').lower():
            continue
        eg = shape(f['geometry'])
        if eg.geom_type == 'Polygon':
            xs, ys = zip(*[lnglat_to_en(a, b) for a, b in eg.exterior.coords])
            ax.plot(xs, ys, color='#5d4037', lw=1.0, ls='--')
        elif eg.geom_type == 'MultiPolygon':
            for p in eg.geoms:
                xs, ys = zip(*[lnglat_to_en(a, b) for a, b in p.exterior.coords])
                ax.plot(xs, ys, color='#5d4037', lw=1.0, ls='--')
        elif eg.geom_type == 'LineString':
            xs, ys = zip(*[lnglat_to_en(a, b) for a, b in eg.coords])
            ax.plot(xs, ys, color='#5d4037', lw=1.5, ls='--')
        elif eg.geom_type == 'MultiLineString':
            for line in eg.geoms:
                xs, ys = zip(*[lnglat_to_en(a, b) for a, b in line.coords])
                ax.plot(xs, ys, color='#5d4037', lw=1.5, ls='--')
    for f in kept[:12]:
        g = shape(f['geometry'])
        if g.geom_type == 'Polygon':
            xs, ys = zip(*[lnglat_to_en(a, b) for a, b in g.exterior.coords])
            ax.plot(xs, ys, color='#b71c1c', lw=1.5)
            c = g.centroid
            ce, cn = lnglat_to_en(c.x, c.y)
            ax.text(ce, cn, str(f['properties']['rank']), color='white',
                    fontsize=9, ha='center', va='center',
                    bbox=dict(boxstyle='circle', fc='#b71c1c', ec='none', pad=0.2))
    fig.colorbar(im, ax=ax, shrink=0.7, label='gather score')
    ax.set_aspect('equal')
    ax.set_title('Where the land gathers (C19) — modelled overlay')
    ax.set_xlabel('east m')
    ax.set_ylabel('north m')
    fig.tight_layout()
    fig.savefig(ROOT / 'analysis' / 'gathers-figure.png', dpi=150)
    plt.close(fig)

    # proof cells for check script
    proof = {
        'weights': WEIGHTS,
        'threshold': thr,
        'n_polygons': len(kept),
        'exclusions': excl_meta,
    }
    (ROOT / 'analysis' / 'gathers-summary.json').write_text(
        json.dumps(proof, indent=2) + '\n', encoding='utf-8',
    )
    print(f'OK gathers: thr={thr:.4f} polys={len(kept)} excl={int(excl.sum())} cells')


if __name__ == '__main__':
    main()
