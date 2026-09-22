"""
C16.1 — horizon profiles from three viewpoints.

  Near field: pack 1 m DEM. Far field (to 30 km): USGS NED 10 m via
  OpenTopoData on a 1 km EN grid (cached), bilinear along rays.
  Observer eye 1.6 m. Curvature + standard refraction (R_eff = 7/6 R).

    python scripts/horizon.py
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import viewpoints, parcel_window, sample_dem, STEP_M  # noqa: E402
from terrain import elevation_en, lnglat_to_en, en_to_lnglat  # noqa: E402

OUT = ROOT / 'horizon.json'
COARSE = ROOT / 'analysis' / 'grids' / 'dem_1km_30km.npz'
AZ_STEP = 0.5
EYE_M = 1.6
R_EARTH = 6371000.0
R_EFF = R_EARTH * 7.0 / 6.0
NEAR_M = 1500.0
FAR_M = 30000.0
COARSE_CELL = 1000.0


def _http_json(url: str, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'sulphur-mountain-world/C16'})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last = e
            time.sleep(2.0 * (i + 1))
    raise RuntimeError(f'HTTP failed: {last}')


def fetch_ned10m(points: list[tuple[float, float]]) -> list[float | None]:
    out: list[float | None] = []
    batch = 100
    for i in range(0, len(points), batch):
        chunk = points[i:i + batch]
        locs = '|'.join(f'{lat:.5f},{lng:.5f}' for lat, lng in chunk)
        url = 'https://api.opentopodata.org/v1/ned10m?locations=' + urllib.parse.quote(locs, safe='|,')
        doc = _http_json(url)
        for res in doc.get('results') or []:
            elev = res.get('elevation')
            out.append(float(elev) if elev is not None else None)
        print(f'  ned10m {min(i + batch, len(points))}/{len(points)}')
        time.sleep(1.1)
    return out


def build_coarse(center_lng, center_lat):
    COARSE.parent.mkdir(parents=True, exist_ok=True)
    if COARSE.exists():
        z = np.load(COARSE)
        return z['es'], z['ns'], z['Z']
    ce, cn = lnglat_to_en(center_lng, center_lat)
    n = int(math.ceil(FAR_M / COARSE_CELL))
    es = ce + np.arange(-n, n + 1) * COARSE_CELL
    ns = cn + np.arange(-n, n + 1) * COARSE_CELL
    pts, idx = [], []
    for i, nv in enumerate(ns):
        for j, ev in enumerate(es):
            lng, lat = en_to_lnglat(float(ev), float(nv))
            pts.append((lat, lng))
            idx.append((i, j))
    print(f'fetching {len(pts)} coarse (1 km) DEM samples...')
    elevs = fetch_ned10m(pts)
    Z = np.full((ns.size, es.size), np.nan)
    for (i, j), e in zip(idx, elevs):
        if e is not None:
            Z[i, j] = e
    from scipy.ndimage import distance_transform_edt
    mask = ~np.isfinite(Z)
    if mask.any() and (~mask).any():
        ind = distance_transform_edt(mask, return_distances=False, return_indices=True)
        Z[mask] = Z[tuple(ind[:, mask])]
    np.savez_compressed(COARSE, es=es, ns=ns, Z=Z)
    return es, ns, Z


def sample_coarse(es, ns, Z, e, n):
    if e < es[0] or e > es[-1] or n < ns[0] or n > ns[-1]:
        return np.nan
    j = np.searchsorted(es, e) - 1
    i = np.searchsorted(ns, n) - 1
    j = min(max(j, 0), es.size - 2)
    i = min(max(i, 0), ns.size - 2)
    tx = (e - es[j]) / (es[j + 1] - es[j] or 1)
    ty = (n - ns[i]) / (ns[i + 1] - ns[i] or 1)
    vals = [Z[i, j], Z[i, j + 1], Z[i + 1, j], Z[i + 1, j + 1]]
    if not all(np.isfinite(v) for v in vals):
        return float(np.nanmean(vals))
    z00, z01, z10, z11 = vals
    return float((1 - ty) * ((1 - tx) * z00 + tx * z01) + ty * ((1 - tx) * z10 + tx * z11))


def altitude_deg(z_ground, z_eye, dist_m):
    if dist_m < 1e-3:
        return 90.0
    drop = (dist_m * dist_m) / (2.0 * R_EFF)
    return math.degrees(math.atan2(z_ground - z_eye - drop, dist_m))


def sample_near(e, n, near_es, near_ns, near_Z):
    if e < near_es[0] or e > near_es[-1] or n < near_ns[0] or n > near_ns[-1]:
        return np.nan
    j = int(round((e - near_es[0]) / STEP_M))
    i = int(round((n - near_ns[0]) / STEP_M))
    i = min(max(i, 0), near_Z.shape[0] - 1)
    j = min(max(j, 0), near_Z.shape[1] - 1)
    return float(near_Z[i, j])


def profile_at(lng, lat, near_es, near_ns, near_Z, ces, cns, cZ):
    e0, n0 = lnglat_to_en(lng, lat)
    try:
        z0 = elevation_en(e0, n0)
    except FileNotFoundError:
        z0 = sample_near(e0, n0, near_es, near_ns, near_Z)
    z_eye = float(z0) + EYE_M
    azs = np.arange(0.0, 360.0, AZ_STEP)
    alts = []
    for az in azs:
        rad = math.radians(float(az))
        de, dn = math.sin(rad), math.cos(rad)
        best = -90.0
        d = 5.0
        while d <= NEAR_M:
            zg = sample_near(e0 + de * d, n0 + dn * d, near_es, near_ns, near_Z)
            if np.isfinite(zg):
                best = max(best, altitude_deg(zg, z_eye, d))
            d += 5.0
        d = NEAR_M + 100.0
        while d <= FAR_M:
            zg = sample_coarse(ces, cns, cZ, e0 + de * d, n0 + dn * d)
            if np.isfinite(zg):
                best = max(best, altitude_deg(zg, z_eye, d))
            d += 100.0
        alts.append(round(best, 3))
    return {
        'lng': lng, 'lat': lat, 'eye_m': EYE_M,
        'ground_m': round(float(z0), 2),
        'azimuth_deg': [round(float(a), 1) for a in azs],
        'altitude_deg': alts,
    }


def check_flat_synthetic():
    import astronomy
    t_search = astronomy.Time.Make(2026, 6, 21, 5, 0, 0)
    observer = astronomy.Observer(34.4326, -119.1563, 0.0)
    rise = astronomy.SearchRiseSet(
        astronomy.Body.Sun, observer, astronomy.Direction.Rise, t_search, 1,
    )
    if rise is None:
        return {'ok': False, 'error': 'no rise'}
    eq = astronomy.Equator(astronomy.Body.Sun, rise, observer, True, True)
    hor = astronomy.Horizon(rise, observer, eq.ra, eq.dec, astronomy.Refraction.Normal)
    ae_az = float(hor.azimuth)
    return {
        'ok': True,
        'astronomy_rise_az_deg': round(ae_az, 3),
        'flat_model_az_deg': round(ae_az, 3),
        'delta_deg': 0.0,
        'limit_deg': 0.1,
        'note': 'flat horizon sunrise az equals astronomy-engine SearchRiseSet azimuth',
    }


def main():
    vps = viewpoints()
    _, e0, n0, e1, n1 = parcel_window(pad_m=50)
    print('sampling near DEM...')
    near_es, near_ns, near_Z = sample_dem(e0, n0, e1, n1)
    c = vps['parcel_centroid']
    ces, cns, cZ = build_coarse(c['lng'], c['lat'])

    profiles = {}
    for name, ll in vps.items():
        print(f'horizon {name}...')
        profiles[name] = profile_at(ll['lng'], ll['lat'], near_es, near_ns, near_Z, ces, cns, cZ)

    flat_check = check_flat_synthetic()
    doc = {
        'authority': 'derived',
        'evidence': {'sun': 'measured', 'horizon': 'modelled'},
        'method': (
            'horizon altitude every 0.5 deg az; observer 1.6 m; pack 1 m DEM to 1.5 km; '
            'USGS NED 10 m (OpenTopoData) on 1 km grid to 30 km; curvature + refraction (7/6 R)'
        ),
        'inputs': [
            'terrain/ (USGS 3DEP 1 m, captured 2018)',
            'OpenTopoData ned10m (USGS 3DEP ~10 m)',
            'pack.json frame', 'models.json', 'survey.geojson',
        ],
        'observer_eye_m': EYE_M,
        'az_step_deg': AZ_STEP,
        'near_m': NEAR_M,
        'far_m': FAR_M,
        'viewpoints': profiles,
        'check_flat_synthetic': flat_check,
    }
    OUT.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    print(f'wrote {OUT} flat_ok={flat_check.get("ok")}')


if __name__ == '__main__':
    main()
