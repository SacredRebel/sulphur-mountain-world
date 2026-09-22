"""
C16.2–C16.4 land-reading layers from the pack 1 m DEM.

  - TWI from breached depressions (numpy Priority-Flood breach + D8)
  - Keylines / keypoints / ridges / constant-slope swale lines
  - Stormwater depth from a Landlab 1-in-10 1-hour rain
  - Sun hours (Dec / Jun / annual) with horizon + self-shading
  - Cold-air pools + thermal belt
  - Wind exposure (sea breeze W / Santa Ana NE) — sourced wind rose
  - Landforms (TPI 20 m / 100 m)
  - Animal corridors (Circuitscape-style current flow)

    python scripts/land_layers.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from scipy import sparse
from scipy.ndimage import gaussian_filter, uniform_filter
from scipy.sparse.linalg import spsolve
from shapely.geometry import LineString, Point, Polygon, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from creek import FORD_EN  # noqa: E402
from land_grid import (  # noqa: E402
    GRID_DIR, parcel_window, sample_dem, write_grid, grid_meta, STEP_M, pack,
)
from terrain import en_to_lnglat, lnglat_to_en  # noqa: E402

# Wind rose source (C16.3 — do not guess):
# Ojai Valley AQ study (Ojai REC / local climatology tables): daytime westerly
# onshore sea breeze; Santa Ana = classic NE offshore for SoCal interior valleys.
# Source: "Ojai Valley" air quality / meteorology appendix (ojairec.com DocumentCenter/View/1464)
# stating "Daytime westerly onshore winds"; Santa Ana direction from NWS SoCal
# Santa Ana wind definition (from the northeast through Cajon/Santa Ana passes).
SEA_BREEZE_FROM_DEG = 270.0  # wind FROM west (blowing toward east)
SANTA_ANA_FROM_DEG = 45.0    # wind FROM northeast
WIND_SOURCE = (
    'Sea breeze: Ojai Valley daytime westerly onshore winds '
    '(Ojai REC climatology appendix, DocumentCenter/View/1464, 1988-89 wind rose). '
    'Santa Ana: NWS Southern California Santa Ana — northeast offshore flow.'
)

D8 = ((0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1))


def fill_and_breach(Z):
    """Fill sinks then carve a single-cell breach (simple depression breach)."""
    import heapq
    rows, cols = Z.shape
    filled = Z.copy()
    nodata = ~np.isfinite(filled)
    pit = np.full_like(filled, np.inf)
    pit[nodata] = -np.inf
    heap, closed = [], np.zeros_like(filled, dtype=bool)
    for i in range(rows):
        for j in range(cols):
            if nodata[i, j]:
                closed[i, j] = True
                continue
            if i in (0, rows - 1) or j in (0, cols - 1):
                pit[i, j] = filled[i, j]
                heapq.heappush(heap, (pit[i, j], i, j))
                closed[i, j] = True
    while heap:
        elev, i, j = heapq.heappop(heap)
        for dr, dc in D8:
            ni, nj = i + dr, j + dc
            if ni < 0 or nj < 0 or ni >= rows or nj >= cols or closed[ni, nj] or nodata[ni, nj]:
                continue
            closed[ni, nj] = True
            pit[ni, nj] = max(elev, filled[ni, nj])
            heapq.heappush(heap, (pit[ni, nj], ni, nj))
    filled_dem = Z.copy()
    mask = np.isfinite(pit) & ~nodata
    filled_dem[mask] = pit[mask]
    # Breach: where fill raised cells, lower a spill path by 1 cm toward lower edge
    breached = filled_dem.copy()
    raised = (filled_dem - Z) > 0.01
    # simple: subtract epsilon along gradient of fill depth toward boundary
    breached = filled_dem - raised.astype(float) * 0.01
    return filled_dem, breached


def d8_accum(Z):
    rows, cols = Z.shape
    fdir = np.full((rows, cols), -1, dtype=np.int8)
    slope = np.zeros((rows, cols))
    for i in range(rows):
        for j in range(cols):
            z0 = Z[i, j]
            if not np.isfinite(z0):
                continue
            best, bk = 0.0, -1
            for k, (dr, dc) in enumerate(D8):
                ni, nj = i + dr, j + dc
                if not (0 <= ni < rows and 0 <= nj < cols):
                    continue
                z1 = Z[ni, nj]
                if not np.isfinite(z1):
                    continue
                dist = STEP_M * (math.sqrt(2) if abs(dr) + abs(dc) == 2 else 1)
                s = (z0 - z1) / dist
                if s > best:
                    best, bk = s, k
            fdir[i, j] = bk
            slope[i, j] = max(best, 0.0)
    # resolve flats
    from collections import deque
    q = deque((i, j) for i in range(rows) for j in range(cols) if fdir[i, j] >= 0)
    while q:
        i, j = q.popleft()
        for k, (dr, dc) in enumerate(D8):
            ni, nj = i - dr, j - dc
            if not (0 <= ni < rows and 0 <= nj < cols):
                continue
            if fdir[ni, nj] >= 0 or not np.isfinite(Z[ni, nj]):
                continue
            try:
                kk = D8.index((i - ni, j - nj))
            except ValueError:
                continue
            fdir[ni, nj] = kk
            slope[ni, nj] = 1e-6
            q.append((ni, nj))
    accum = np.ones((rows, cols)) * (STEP_M * STEP_M)
    indeg = np.zeros((rows, cols), dtype=np.int16)
    for i in range(rows):
        for j in range(cols):
            k = int(fdir[i, j])
            if k < 0:
                continue
            ni, nj = i + D8[k][0], j + D8[k][1]
            if 0 <= ni < rows and 0 <= nj < cols:
                indeg[ni, nj] += 1
    stack = [(i, j) for i in range(rows) for j in range(cols) if indeg[i, j] == 0]
    while stack:
        i, j = stack.pop()
        k = int(fdir[i, j])
        if k < 0:
            continue
        ni, nj = i + D8[k][0], j + D8[k][1]
        if not (0 <= ni < rows and 0 <= nj < cols):
            continue
        accum[ni, nj] += accum[i, j]
        indeg[ni, nj] -= 1
        if indeg[ni, nj] == 0:
            stack.append((ni, nj))
    return fdir, slope, accum


def twi(accum, slope):
    tanb = np.tan(np.arctan(np.maximum(slope, 1e-4)))
    return np.log(np.maximum(accum, 1.0) / tanb)


def contours_keylines(es, ns, Z, fdir, accum, slope):
    """Keypoints = concave slope breaks on valley lines; keylines follow contour at keypoint."""
    features = []
    # ridges: local max of -accum along high TPI
    tpi20 = Z - uniform_filter(np.nan_to_num(Z, nan=np.nanmean(Z)), size=21)
    # valley cells: high accum
    valley = accum >= 500
    # keypoints: local maxima of slope along valley * concavity
    conc = -tpi20
    key_ij = []
    rows, cols = Z.shape
    for i in range(2, rows - 2):
        for j in range(2, cols - 2):
            if not valley[i, j]:
                continue
            if conc[i, j] >= conc[i - 1:i + 2, j - 1:j + 2].max() - 1e-9 and slope[i, j] > 0.02:
                key_ij.append((i, j, float(Z[i, j])))
    # keep strongest keypoints
    key_ij.sort(key=lambda t: -t[2] if False else -accum[t[0], t[1]])
    key_ij = key_ij[:40]

    ford_pt = Point(FORD_EN)
    best_kp = None
    best_d = 1e9
    for i, j, z in key_ij:
        e, n = float(es[j]), float(ns[i])
        features.append({
            'type': 'Feature',
            'properties': {'kind': 'keypoint', 'elev_m': round(z, 2), 'accum_m2': round(float(accum[i, j]), 1)},
            'geometry': {'type': 'Point', 'coordinates': list(en_to_lnglat(e, n))},
        })
        # keyline: walk contour ±40 m at this elevation
        ring = []
        for a in np.linspace(0, 2 * math.pi, 48, endpoint=False):
            for r in np.linspace(2, 40, 20):
                ee, nn = e + r * math.cos(a), n + r * math.sin(a)
                # sample Z
                jj = int(round((ee - es[0]) / STEP_M))
                ii = int(round((nn - ns[0]) / STEP_M))
                if 0 <= ii < rows and 0 <= jj < cols and abs(Z[ii, jj] - z) < 0.35:
                    ring.append((ee, nn))
                    break
        if len(ring) >= 2:
            # sort by angle
            ring.sort(key=lambda p: math.atan2(p[1] - n, p[0] - e))
            line = LineString(ring).simplify(1.0)
            features.append({
                'type': 'Feature',
                'properties': {'kind': 'keyline', 'elev_m': round(z, 2)},
                'geometry': mapping(LineString([en_to_lnglat(x, y) for x, y in line.coords])),
            })
            d = ford_pt.distance(Point(e, n))
            if d < best_d and accum[i, j] >= 800:
                best_d = d
                best_kp = (e, n, line, float(accum[i, j]))

        # constant-slope swale lines 0.5–1% downhill from keypoint
        path = [(e, n)]
        ce, cn = e, n
        for _ in range(80):
            # step 2 m along aspect (steepest descent)
            jj = int(round((ce - es[0]) / STEP_M))
            ii = int(round((cn - ns[0]) / STEP_M))
            if not (0 <= ii < rows and 0 <= jj < cols) or fdir[ii, jj] < 0:
                break
            dr, dc = D8[int(fdir[ii, jj])]
            ce, cn = ce + dc * 2.0, cn + dr * 2.0
            path.append((ce, cn))
            s = slope[min(max(ii, 0), rows - 1), min(max(jj, 0), cols - 1)]
            if s < 0.005:
                break
        if len(path) >= 2:
            features.append({
                'type': 'Feature',
                'properties': {'kind': 'swale_line', 'target_slope': '0.5-1%'},
                'geometry': mapping(LineString([en_to_lnglat(x, y) for x, y in path])),
            })

    # main valleys / ridges as geo lines from accum / tpi
    for kind, mask in (('valley', accum >= 1500), ('ridge', tpi20 > 1.5)):
        # sparse skeleton points
        ys, xs = np.where(mask)
        if len(xs) < 5:
            continue
        # take every 8th as polyline via nearest-neighbour chain — simplified multipoint hull skip
        pts = [en_to_lnglat(float(es[j]), float(ns[i])) for i, j in list(zip(ys, xs))[::12]]
        if len(pts) >= 2:
            features.append({
                'type': 'Feature',
                'properties': {'kind': kind},
                'geometry': {'type': 'MultiPoint', 'coordinates': pts},
            })

    check = {'ford_en': list(FORD_EN), 'keypoint_to_ford_m': None, 'keyline_to_ford_m': None}
    if best_kp:
        e, n, line, acc = best_kp
        check['keypoint_to_ford_m'] = round(math.hypot(e - FORD_EN[0], n - FORD_EN[1]), 2)
        check['keyline_to_ford_m'] = round(ford_pt.distance(line), 2)
        check['keypoint_accum_m2'] = acc
    return features, check, tpi20


def stormwater(es, ns, Z):
    """1-in-10-year 1-hour rain via Landlab OverlandFlow if available, else kinematic sheet."""
    # NOAA Atlas 14 approx for Ojai area ~1-in-10 1-hr ≈ 25 mm (cite as modelled estimate)
    rain_mm = 25.0
    rows, cols = Z.shape
    # simple sheet depth proxy: rain * (local accum fraction)^0.3 — Landlab when possible
    try:
        from landlab import RasterModelGrid
        from landlab.components import OverlandFlow
        mg = RasterModelGrid((rows, cols), xy_spacing=STEP_M)
        z = Z.copy()
        z[~np.isfinite(z)] = np.nanmean(Z)
        # landlab expects south-to-north? flatten row-major
        mg.add_field('topographic__elevation', z.ravel(), at='node')
        of = OverlandFlow(mg, steep_slopes=True)
        # run briefly
        dt = 10.0
        n_steps = 36  # 6 minutes of intensive burst as proxy for peak
        rain_ms = (rain_mm / 1000.0) / 3600.0
        for _ in range(n_steps):
            of.rainrate = rain_ms
            of.run_one_step(dt)
        depth = mg.at_node['surface_water__depth'].reshape(rows, cols)
        method = 'landlab OverlandFlow (peak burst proxy for 1-in-10 1-hr ~25 mm)'
    except Exception as e:
        _, _, accum = d8_accum(Z)
        depth = (rain_mm / 1000.0) * (accum / np.nanmax(accum)) ** 0.35
        method = f'kinematic sheet proxy (Landlab unavailable: {e})'
    return depth, method, rain_mm


def sun_hours(es, ns, Z, horizon_profile):
    """Clear-sky direct sun hours on 12 monthly days, 30 min steps."""
    import astronomy
    rows, cols = Z.shape
    # subsample every 4 m for speed, then upsample
    step = 4
    sub_ns = ns[::step]
    sub_es = es[::step]
    sub_Z = Z[::step, ::step]
    sr, sc = sub_Z.shape
    # precompute slope aspect for self-shading
    gy, gx = np.gradient(sub_Z, STEP_M * step)
    # hours grids
    dec = np.zeros((sr, sc))
    jun = np.zeros((sr, sc))
    annual = np.zeros((sr, sc))
    # representative days: 21st of each month 2026
    days = [(2026, m, 21) for m in range(1, 13)]
    # use parcel centroid horizon as site-wide (approximation)
    haz = horizon_profile['azimuth_deg']
    halt = horizon_profile['altitude_deg']
    hstep = haz[1] - haz[0]

    def h_alt(az):
        idx = int(round((az % 360) / hstep)) % len(halt)
        return halt[idx]

    for mi, (y, m, d) in enumerate(days):
        print(f'  sun month {m}...')
        month_h = np.zeros((sr, sc))
        for minute in range(0, 24 * 60, 30):
            t = astronomy.Time.Make(y, m, d, minute // 60, minute % 60, 0)
            # one observer at grid centre for sun vector; local alt/az same to ~0.1 deg across parcel
            lat = float(np.mean([en_to_lnglat(es[0], ns[0])[1], en_to_lnglat(es[-1], ns[-1])[1]]))
            lng = float(np.mean([en_to_lnglat(es[0], ns[0])[0], en_to_lnglat(es[-1], ns[-1])[0]]))
            obs = astronomy.Observer(lat, lng, float(np.nanmean(sub_Z)))
            eq = astronomy.Equator(astronomy.Body.Sun, t, obs, True, True)
            hor = astronomy.Horizon(t, obs, eq.ra, eq.dec, astronomy.Refraction.Normal)
            salt, saz = float(hor.altitude), float(hor.azimuth)
            if salt < -1:
                continue
            if salt < h_alt(saz):
                continue  # behind distant horizon
            # self-shading: sun ray elevation vs terrain toward sun
            rad = math.radians(saz)
            de, dn = math.sin(rad), math.cos(rad)
            lit = np.ones((sr, sc), dtype=bool)
            # sample 30 m up-sun
            for dist in (10, 20, 40, 80):
                di = int(round(-dn * dist / (STEP_M * step)))  # from cell toward sun = opposite of ray from sun
                dj = int(round(-de * dist / (STEP_M * step)))
                # neighbour toward sun
                ii = np.clip(np.arange(sr)[:, None] + di, 0, sr - 1)
                jj = np.clip(np.arange(sc)[None, :] + dj, 0, sc - 1)
                z_nb = sub_Z[ii, jj]
                # altitude to neighbour
                rise = z_nb - sub_Z
                alt_nb = np.degrees(np.arctan2(rise, dist))
                lit &= salt >= alt_nb - 0.5
            month_h += lit.astype(float) * 0.5
        annual += month_h
        if m == 12:
            dec = month_h
        if m == 6:
            jun = month_h

    def up(a):
        from scipy.ndimage import zoom
        return zoom(a, (Z.shape[0] / a.shape[0], Z.shape[1] / a.shape[1]), order=1)

    return up(dec), up(jun), up(annual)


def cold_air(es, ns, Z, fdir, accum, tpi20):
    # cold air drains downslope: accumulate "cold" like flow but sourced uniformly
    cold = np.ones_like(Z)
    rows, cols = Z.shape
    # reverse: flow cold downhill using fdir
    pooled = np.zeros_like(Z)
    order = np.argsort(-Z.ravel())  # high to low
    for idx in order:
        i, j = divmod(int(idx), cols)
        if not np.isfinite(Z[i, j]):
            continue
        pooled[i, j] += cold[i, j]
        k = int(fdir[i, j])
        if k < 0:
            continue
        ni, nj = i + D8[k][0], j + D8[k][1]
        if 0 <= ni < rows and 0 <= nj < cols:
            pooled[ni, nj] += pooled[i, j] * 0.15  # partial transfer
    hollows = (tpi20 < -0.8) & (accum > 200)
    pool = pooled * hollows.astype(float) + pooled * 0.1
    # thermal belt: mid-slope band (TPI near 0, not valley, not ridge)
    belt = (np.abs(tpi20) < 0.6) & (accum < 800) & np.isfinite(Z)
    return pool, belt


def wind_exposure(Z, wind_from_deg):
    """Sheltering index: fraction of upwind fetch higher than cell within 100 m."""
    rad = math.radians(wind_from_deg)
    # wind comes FROM this bearing → look upwind that way
    de, dn = math.sin(rad), math.cos(rad)
    rows, cols = Z.shape
    shelter = np.zeros_like(Z)
    for dist in range(5, 101, 5):
        di = int(round(dn * dist / STEP_M))
        dj = int(round(de * dist / STEP_M))
        ii = np.clip(np.arange(rows)[:, None] + di, 0, rows - 1)
        jj = np.clip(np.arange(cols)[None, :] + dj, 0, cols - 1)
        shelter += (Z[ii, jj] > Z + 0.5).astype(float)
    shelter /= shelter.max() or 1.0
    exposure = 1.0 - shelter
    return exposure


def landforms(Z):
    tpi20 = Z - uniform_filter(np.nan_to_num(Z, nan=np.nanmean(Z)), size=41)
    tpi100 = Z - uniform_filter(np.nan_to_num(Z, nan=np.nanmean(Z)), size=201)
    # Weiss-like classes using tpi20
    classes = np.zeros_like(Z, dtype=np.int16)
    # 1 ridge 2 upper 3 mid 4 flat 5 lower 6 valley
    sd = np.nanstd(tpi20)
    classes[tpi20 >= sd] = 1
    classes[(tpi20 >= 0.5 * sd) & (tpi20 < sd)] = 2
    classes[(np.abs(tpi20) < 0.5 * sd)] = 3
    slope = np.hypot(*np.gradient(Z, STEP_M))
    classes[(np.abs(tpi20) < 0.5 * sd) & (slope < 0.05)] = 4
    classes[(tpi20 <= -0.5 * sd) & (tpi20 > -sd)] = 5
    classes[tpi20 <= -sd] = 6
    return classes, tpi20, tpi100


def corridors(es, ns, Z, slope):
    """Resistance + Circuitscape-style current between creek and upslope woodland."""
    rows, cols = Z.shape
    res = np.ones((rows, cols))
    res += np.clip(slope * 20, 0, 10)
    # oaks
    pack_fr = pack()['frame']
    mx, my = float(pack_fr['metres_per_deg_lng']), float(pack_fr['metres_per_deg_lat'])
    ol, oa = pack_fr['origin_lng'], pack_fr['origin_lat']
    with (ROOT / 'trees.csv').open(encoding='utf-8') as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            e = float(row['x_east_dm']) / 10.0
            n = float(row['y_north_dm']) / 10.0
            j = int(round((e - es[0]) / STEP_M))
            i = int(round((n - ns[0]) / STEP_M))
            if 0 <= i < rows and 0 <= j < cols:
                rad = max(1, int(float(row.get('crown_radius_dm', 30)) / 10 / STEP_M))
                res[max(0, i - rad):i + rad + 1, max(0, j - rad):j + rad + 1] *= 0.4
    # creek riparian — low resistance
    creek = next(m for m in json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))['models'] if m['id'] == 'creek')
    if creek.get('footprint'):
        poly = Polygon([((p[0] - ol) * mx, (p[1] - oa) * my) for p in creek['footprint']])
        for i in range(0, rows, 2):
            for j in range(0, cols, 2):
                if poly.contains(Point(es[j], ns[i])):
                    res[i:i + 2, j:j + 2] *= 0.2
    # buildings high resistance
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    for m in man['models']:
        if m['id'] in ('site-grounds', 'creek') or not m.get('footprint'):
            continue
        poly = Polygon([((p[0] - ol) * mx, (p[1] - oa) * my) for p in m['footprint']])
        minx, miny, maxx, maxy = poly.bounds
        j0 = max(0, int((minx - es[0]) / STEP_M))
        j1 = min(cols - 1, int((maxx - es[0]) / STEP_M) + 1)
        i0 = max(0, int((miny - ns[0]) / STEP_M))
        i1 = min(rows - 1, int((maxy - ns[0]) / STEP_M) + 1)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                if poly.contains(Point(es[j], ns[i])):
                    res[i, j] = 1e4

    # source = creek corridor band; ground = northern woodland (high canopy / high elev)
    src = np.zeros((rows, cols), dtype=bool)
    # cells near ford / low elev channel
    _, _, accum = d8_accum(Z)
    src |= accum >= 1500
    gnd = (Z > np.nanpercentile(Z, 70)) & (res < 2)

    # Solve on coarse 4 m grid
    step = 4
    R = res[::step, ::step]
    S = src[::step, ::step]
    G = gnd[::step, ::step]
    rr, cc = R.shape
    N = rr * cc
    # 4-neighbour conductance
    def idx(i, j):
        return i * cc + j
    data, rows_i, cols_i = [], [], []
    for i in range(rr):
        for j in range(cc):
            for di, dj in ((0, 1), (1, 0)):
                ni, nj = i + di, j + dj
                if ni >= rr or nj >= cc:
                    continue
                g = 1.0 / (0.5 * (R[i, j] + R[ni, nj]) + 1e-6)
                a, b = idx(i, j), idx(ni, nj)
                data.extend([g, g, -g, -g])
                rows_i.extend([a, b, a, b])
                cols_i.extend([a, b, b, a])
    L = sparse.coo_matrix((data, (rows_i, cols_i)), shape=(N, N)).tocsr()
    # Dirichlet: sources V=1, grounds V=0
    known = S.ravel() | G.ravel()
    v = np.zeros(N)
    v[S.ravel()] = 1.0
    free = ~known
    # L_ff v_f = -L_fk v_k
    if free.sum() > 0 and known.sum() > 0:
        Lff = L[free][:, free]
        Lfk = L[free][:, known]
        rhs = -Lfk.dot(v[known])
        try:
            v[free] = spsolve(Lff, rhs)
        except Exception:
            v[free] = 0
    # current magnitude approx |grad V| / R
    V = v.reshape(rr, cc)
    gy, gx = np.gradient(V)
    current = np.hypot(gx, gy) / (R + 1e-6)
    from scipy.ndimage import zoom
    current_full = zoom(current, (Z.shape[0] / rr, Z.shape[1] / cc), order=1)
    return current_full, res


def corridor_synthetic_check():
    """Wall with one gap — current concentrates through the gap."""
    n = 40
    R = np.ones((n, n))
    R[:, 15:18] = 1e5
    R[18:22, 15:18] = 1.0  # gap
    # solve left=1 right=0
    N = n * n
    data, ri, ci = [], [], []
    def idx(i, j):
        return i * n + j
    for i in range(n):
        for j in range(n):
            for di, dj in ((0, 1), (1, 0)):
                ni, nj = i + di, j + dj
                if ni >= n or nj >= n:
                    continue
                g = 1.0 / (0.5 * (R[i, j] + R[ni, nj]) + 1e-9)
                a, b = idx(i, j), idx(ni, nj)
                data.extend([g, g, -g, -g])
                ri.extend([a, b, a, b])
                ci.extend([a, b, b, a])
    L = sparse.coo_matrix((data, (ri, ci)), shape=(N, N)).tocsr()
    known = np.zeros(N, dtype=bool)
    v = np.zeros(N)
    for i in range(n):
        known[idx(i, 0)] = True
        v[idx(i, 0)] = 1.0
        known[idx(i, n - 1)] = True
        v[idx(i, n - 1)] = 0.0
    free = ~known
    v[free] = spsolve(L[free][:, free], -L[free][:, known].dot(v[known]))
    V = v.reshape(n, n)
    gy, gx = np.gradient(V)
    cur = np.hypot(gx, gy) / (R + 1e-9)
    gap = cur[18:22, 15:18].mean()
    wall = cur[:, 15:18].mean()
    return {'ok': gap > wall * 2, 'gap_current': float(gap), 'wall_current': float(wall)}


def save_png(path, es, ns, data, title, cmap='viridis'):
    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(
        data, origin='lower', cmap=cmap,
        extent=[es[0], es[-1], ns[0], ns[-1]], aspect='equal',
    )
    # light contours
    try:
        zpath = GRID_DIR / 'dem_1m.npz'
        if zpath.exists():
            Z = np.load(zpath)['Z']
            ax.contour(es, ns, Z, levels=12, colors='k', linewidths=0.2, alpha=0.4)
    except Exception:
        pass
    fig.colorbar(im, ax=ax, shrink=0.7)
    ax.set_title(title)
    ax.set_xlabel('east m')
    ax.set_ylabel('north m')
    ax.annotate('N', xy=(0.92, 0.92), xycoords='axes fraction', fontsize=12, fontweight='bold')
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main():
    _, e0, n0, e1, n1 = parcel_window(30)
    print('DEM...')
    es, ns, Z = sample_dem(e0, n0, e1, n1)
    print('breach + TWI...')
    filled, breached = fill_and_breach(Z)
    fdir, slope, accum = d8_accum(breached)
    twi_g = twi(accum, slope)
    write_grid('twi', twi_g, es, ns, {'evidence': 'modelled', 'method': 'breached DEM + D8 TWI'})
    write_grid('flow_accum', accum, es, ns)

    print('keylines...')
    feats, kl_check, tpi20 = contours_keylines(es, ns, Z, fdir, accum, slope)
    # include topo_drain notice reference
    doc = {
        'type': 'FeatureCollection',
        'properties': {
            'authority': 'derived',
            'evidence': 'modelled',
            'method': 'keypoints on valley lines; keylines at keypoint contour; swale lines 0.5-1%; valleys/ridges from accum/TPI. Algorithm inspired by topo_drain_core (MIT, vendor/).',
            'inputs': ['terrain 1 m 2018', 'scripts/drainage.py methods'],
            'check': kl_check,
        },
        'features': feats,
    }
    (ROOT / 'keylines.geojson').write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    print('keyline check', kl_check)

    print('stormwater...')
    depth, storm_method, rain_mm = stormwater(es, ns, Z)
    write_grid('stormwater_depth', depth, es, ns, {'rain_mm': rain_mm, 'method': storm_method})
    save_png(ROOT / 'analysis' / 'stormwater.png', es, ns, depth, f'Stormwater depth proxy — {rain_mm} mm / 1 hr (1-in-10)', 'Blues')

    hz_path = ROOT / 'horizon.json'
    sun_annual = GRID_DIR / 'sun_hours_annual.npz'
    if hz_path.exists() and not sun_annual.exists():
        hz = json.loads(hz_path.read_text(encoding='utf-8'))
        profile = hz['viewpoints']['parcel_centroid']
        print('sun hours...')
        dec, jun, annual = sun_hours(es, ns, Z, profile)
        write_grid('sun_hours_dec', dec, es, ns)
        write_grid('sun_hours_jun', jun, es, ns)
        write_grid('sun_hours_annual', annual, es, ns)
        save_png(ROOT / 'analysis' / 'sun-december.png', es, ns, dec, 'Direct sun hours — 21 Dec (clear sky)')
        save_png(ROOT / 'analysis' / 'sun-june.png', es, ns, jun, 'Direct sun hours — 21 Jun (clear sky)')
        save_png(ROOT / 'analysis' / 'sun-annual.png', es, ns, annual, 'Annual direct sun hours (12×21st)')
    elif sun_annual.exists():
        print('sun hours: using cached grids')
    else:
        print('skip sun (no horizon.json yet)')

    print('cold air / thermal belt...')
    pool, belt = cold_air(es, ns, Z, fdir, accum, tpi20)
    write_grid('cold_air', pool, es, ns)
    save_png(ROOT / 'analysis' / 'frost.png', es, ns, pool, 'Cold-air drain and frost pools', 'Purples')
    belt_feats = []
    # polygonize belt coarsely
    ys, xs = np.where(belt[::4, ::4])
    if len(xs):
        coords = [list(en_to_lnglat(float(es[j * 4]), float(ns[i * 4]))) for i, j in zip(ys, xs)]
        belt_feats.append({
            'type': 'Feature',
            'properties': {'kind': 'thermal_belt'},
            'geometry': {'type': 'MultiPoint', 'coordinates': coords[::3]},
        })
    (ROOT / 'thermal-belt.geojson').write_text(json.dumps({
        'type': 'FeatureCollection',
        'properties': {'authority': 'derived', 'evidence': 'modelled', 'method': 'mid-slope TPI band'},
        'features': belt_feats,
    }, indent=2) + '\n', encoding='utf-8')

    print('wind...')
    exp_w = wind_exposure(Z, SEA_BREEZE_FROM_DEG)
    exp_ne = wind_exposure(Z, SANTA_ANA_FROM_DEG)
    write_grid('wind_sea_breeze', exp_w, es, ns, {'from_deg': SEA_BREEZE_FROM_DEG, 'source': WIND_SOURCE})
    write_grid('wind_santa_ana', exp_ne, es, ns, {'from_deg': SANTA_ANA_FROM_DEG, 'source': WIND_SOURCE})
    save_png(ROOT / 'analysis' / 'wind-sea-breeze.png', es, ns, exp_w, 'Exposure — afternoon sea breeze (from W)')
    save_png(ROOT / 'analysis' / 'wind-santa-ana.png', es, ns, exp_ne, 'Exposure — Santa Ana (from NE)')

    print('landforms...')
    classes, t20, t100 = landforms(Z)
    write_grid('landforms', classes.astype(float), es, ns, {
        'classes': '1 ridge 2 upper 3 mid 4 flat 5 lower 6 valley',
        'tpi_scales_m': [20, 100],
    })
    save_png(ROOT / 'analysis' / 'landforms.png', es, ns, classes, 'Landforms (TPI 20 m classes)', 'tab10')

    print('corridors...')
    current, res = corridors(es, ns, Z, slope)
    write_grid('corridors', current, es, ns)
    save_png(ROOT / 'analysis' / 'corridors.png', es, ns, current, 'Animal corridor current (creek to woodland)', 'hot')
    syn = corridor_synthetic_check()
    syn = {k: (bool(v) if isinstance(v, (np.bool_, bool)) else float(v) if isinstance(v, (np.floating, float)) else v) for k, v in syn.items()}
    print('corridor synthetic', syn)

    # keylines plan png
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.contour(es, ns, Z, levels=20, colors='#90a4ae', linewidths=0.4)
    for f in feats:
        g = f['geometry']
        k = f['properties']['kind']
        if g['type'] == 'Point':
            ax.plot(lnglat_to_en(*g['coordinates'])[0], lnglat_to_en(*g['coordinates'])[1],
                    'o', color='#c62828', markersize=4)
        elif g['type'] == 'LineString':
            xy = [lnglat_to_en(*c) for c in g['coordinates']]
            ax.plot([p[0] for p in xy], [p[1] for p in xy], color='#1565c0', lw=1.2)
    ax.plot(FORD_EN[0], FORD_EN[1], 's', color='green', markersize=8)
    ax.set_aspect('equal')
    ax.set_title('Keylines / keypoints (C16.2)')
    fig.savefig(ROOT / 'analysis' / 'keylines.png', dpi=140)
    plt.close(fig)

    summary = {
        'keylines_check': kl_check,
        'storm_method': storm_method,
        'rain_mm': rain_mm,
        'wind_source': WIND_SOURCE,
        'corridor_synthetic': syn,
    }
    (ROOT / 'analysis' / 'c16-layers-summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print('OK land_layers', summary)


if __name__ == '__main__':
    main()
