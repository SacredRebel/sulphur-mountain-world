"""
C13.2 — drainage from the pack 1 m DEM.

  Fill sinks, D8 flow direction, flow accumulation. Trace channels where
  contributing area ≥ 2000 m²; simplify ~1 m. Strahler order on the network.

    python scripts/drainage.py
"""
from __future__ import annotations

import heapq
import json
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from shapely.geometry import LineString, Point, shape
from shapely.ops import linemerge, unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from creek import FORD_EN  # noqa: E402
from terrain import elevation_en, en_to_lnglat, lnglat_to_en  # noqa: E402

OUT_GEO = ROOT / 'drainage.geojson'
OUT_PNG = ROOT / 'analysis' / 'drainage.png'
ACCUM_THRESH_M2 = 2000.0
STEP_M = 1.0
SIMPLIFY_M = 1.0
FORD_MAX_M = 8.0

# D8: E, SE, S, SW, W, NW, N, NE — (di, dj) in (row=north↓? we use row=i north index ascending)
# Grid: rows increase north, cols increase east. Neighbor offsets (drow, dcol):
D8 = (
    (0, 1),    # E
    (-1, 1),   # SE  (south = -row)
    (-1, 0),   # S
    (-1, -1),  # SW
    (0, -1),   # W
    (1, -1),   # NW
    (1, 0),    # N
    (1, 1),    # NE
)
D8_DIST = tuple(STEP_M * (math.sqrt(2) if abs(dr) + abs(dc) == 2 else 1.0) for dr, dc in D8)


def load_parcel_en():
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    poly = shape(survey['features'][0]['geometry'])
    # pad ~20 m so channels can exit
    minx, miny, maxx, maxy = poly.bounds
    e0, n0 = lnglat_to_en(minx, miny)
    e1, n1 = lnglat_to_en(maxx, maxy)
    pad = 30.0
    return poly, e0 - pad, n0 - pad, e1 + pad, n1 + pad


def sample_dem(e0, n0, e1, n1):
    cols = int(round((e1 - e0) / STEP_M)) + 1
    rows = int(round((n1 - n0) / STEP_M)) + 1
    es = e0 + np.arange(cols) * STEP_M
    ns = n0 + np.arange(rows) * STEP_M
    Z = np.empty((rows, cols), dtype=np.float64)
    for i, n in enumerate(ns):
        for j, e in enumerate(es):
            try:
                Z[i, j] = elevation_en(float(e), float(n))
            except FileNotFoundError:
                Z[i, j] = np.nan
    return es, ns, Z


def fill_sinks(Z: np.ndarray) -> np.ndarray:
    """Priority-Flood depression fill (Barnes et al.). NaNs treated as nodata barriers."""
    rows, cols = Z.shape
    filled = Z.copy()
    nodata = ~np.isfinite(filled)
    pit = np.full_like(filled, np.inf, dtype=np.float64)
    pit[nodata] = -np.inf

    heap: list[tuple[float, int, int]] = []
    closed = np.zeros_like(filled, dtype=bool)

    for i in range(rows):
        for j in range(cols):
            if nodata[i, j]:
                closed[i, j] = True
                continue
            if i == 0 or j == 0 or i == rows - 1 or j == cols - 1:
                pit[i, j] = filled[i, j]
                heapq.heappush(heap, (pit[i, j], i, j))
                closed[i, j] = True

    while heap:
        elev, i, j = heapq.heappop(heap)
        for dr, dc in D8:
            ni, nj = i + dr, j + dc
            if ni < 0 or nj < 0 or ni >= rows or nj >= cols:
                continue
            if closed[ni, nj] or nodata[ni, nj]:
                continue
            closed[ni, nj] = True
            pit[ni, nj] = max(elev, filled[ni, nj])
            heapq.heappush(heap, (pit[ni, nj], ni, nj))

    out = filled.copy()
    mask = np.isfinite(pit) & ~nodata
    out[mask] = pit[mask]
    return out


def d8_flow(Z: np.ndarray):
    """Return flow direction index 0..7 (-1 = nodata/outlet) and slope (rise/run).

    After sink-fill, flats get a resolved direction toward a lower neighbour
    (breadth-first from cells that already drain).
    """
    rows, cols = Z.shape
    fdir = np.full((rows, cols), -1, dtype=np.int8)
    slope = np.zeros((rows, cols), dtype=np.float64)
    for i in range(rows):
        for j in range(cols):
            z0 = Z[i, j]
            if not np.isfinite(z0):
                continue
            best_s, best_k = 0.0, -1
            for k, (dr, dc) in enumerate(D8):
                ni, nj = i + dr, j + dc
                if ni < 0 or nj < 0 or ni >= rows or nj >= cols:
                    continue
                z1 = Z[ni, nj]
                if not np.isfinite(z1):
                    continue
                drop = z0 - z1
                if drop <= 0:
                    continue
                s = drop / D8_DIST[k]
                if s > best_s:
                    best_s, best_k = s, k
            fdir[i, j] = best_k
            slope[i, j] = best_s

    # Resolve flats: cells with no downhill neighbour borrow a neighbour's drain.
    from collections import deque
    q = deque()
    for i in range(rows):
        for j in range(cols):
            if fdir[i, j] >= 0:
                q.append((i, j))
    while q:
        i, j = q.popleft()
        for k, (dr, dc) in enumerate(D8):
            ni, nj = i - dr, j - dc  # upstream neighbour that would flow here
            if ni < 0 or nj < 0 or ni >= rows or nj >= cols:
                continue
            if not np.isfinite(Z[ni, nj]):
                continue
            if fdir[ni, nj] >= 0:
                continue
            # flat or pit rim: point toward the resolved cell
            # find D8 index from (ni,nj) -> (i,j)
            ddr, ddc = i - ni, j - nj
            try:
                kk = D8.index((ddr, ddc))
            except ValueError:
                continue
            fdir[ni, nj] = kk
            slope[ni, nj] = 1e-6
            q.append((ni, nj))
    return fdir, slope


def flow_accum(fdir: np.ndarray) -> np.ndarray:
    rows, cols = fdir.shape
    cell_area = STEP_M * STEP_M
    accum = np.full((rows, cols), cell_area, dtype=np.float64)
    # indegree + topological drain
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
    return accum


def extract_channel_cells(accum: np.ndarray, fdir: np.ndarray, thresh: float):
    rows, cols = accum.shape
    channel = accum >= thresh
    # Build arcs along channel following flow
    segments = []  # list of list[(i,j)]
    visited_edge = set()

    def downstream(i, j):
        k = int(fdir[i, j])
        if k < 0:
            return None
        ni, nj = i + D8[k][0], j + D8[k][1]
        if 0 <= ni < rows and 0 <= nj < cols and channel[ni, nj]:
            return ni, nj
        return None

    # heads: channel cells with no channel upstream neighbour flowing in
    ups = [[]]
    ups = [[[] for _ in range(cols)] for _ in range(rows)]
    for i in range(rows):
        for j in range(cols):
            if not channel[i, j]:
                continue
            ds = downstream(i, j)
            if ds:
                ups[ds[0]][ds[1]].append((i, j))

    heads = [
        (i, j) for i in range(rows) for j in range(cols)
        if channel[i, j] and len(ups[i][j]) == 0
    ]

    for h in heads:
        path = [h]
        cur = h
        while True:
            nxt = downstream(*cur)
            if nxt is None:
                break
            edge = (cur, nxt)
            if edge in visited_edge:
                path.append(nxt)
                break
            visited_edge.add(edge)
            path.append(nxt)
            cur = nxt
            # stop at confluence (more than one upstream) after recording
            if len(ups[cur[0]][cur[1]]) > 1 and cur != h:
                # continue through confluence along main path once
                pass
        if len(path) >= 2:
            segments.append(path)

    return segments, ups, channel


def strahler_orders(ups, channel, fdir, rows, cols):
    order = np.zeros((rows, cols), dtype=np.int16)

    def downstream(i, j):
        k = int(fdir[i, j])
        if k < 0:
            return None
        ni, nj = i + D8[k][0], j + D8[k][1]
        if 0 <= ni < rows and 0 <= nj < cols and channel[ni, nj]:
            return ni, nj
        return None

    # process heads → outlets repeatedly until stable
    changed = True
    guard = 0
    while changed and guard < rows * cols:
        guard += 1
        changed = False
        for i in range(rows):
            for j in range(cols):
                if not channel[i, j]:
                    continue
                parents = ups[i][j]
                if not parents:
                    if order[i, j] < 1:
                        order[i, j] = 1
                        changed = True
                    continue
                po = [int(order[pi][pj]) for pi, pj in parents]
                if any(o == 0 for o in po):
                    continue
                mx = max(po)
                if po.count(mx) >= 2:
                    neo = mx + 1
                else:
                    neo = mx
                if order[i, j] != neo:
                    order[i, j] = neo
                    changed = True
    return order


def path_to_line(path, es, ns, accum, slope, order):
    coords_ll = []
    accs, slopes, ords = [], [], []
    for i, j in path:
        lng, lat = en_to_lnglat(float(es[j]), float(ns[i]))
        coords_ll.append([round(lng, 7), round(lat, 7)])
        accs.append(float(accum[i, j]))
        slopes.append(float(slope[i, j]) * 100.0)  # fraction → %
        ords.append(int(order[i, j]))
    line = LineString([(es[j], ns[i]) for i, j in path])
    simple = line.simplify(SIMPLIFY_M, preserve_topology=True)
    # map simplified EN → lng/lat
    ll = [[round(en_to_lnglat(x, y)[0], 7), round(en_to_lnglat(x, y)[1], 7)] for x, y in simple.coords]
    return {
        'type': 'Feature',
        'properties': {
            'accum_m2': round(max(accs), 1),
            'slope_pct': round(float(np.mean(slopes)), 2),
            'order': int(max(ords) if ords else 1),
        },
        'geometry': {'type': 'LineString', 'coordinates': ll},
    }, simple


def draw_plan(es, ns, Z, lines_en, ford_en, ford_dist):
    fig, ax = plt.subplots(figsize=(10, 8))
    # contours
    levels = np.arange(np.nanmin(Z) // 2 * 2, np.nanmax(Z) + 2, 2.0)
    EE, NN = np.meshgrid(es, ns)
    ax.contour(EE, NN, Z, levels=levels, colors='#90a4ae', linewidths=0.4)
    colors = {1: '#81d4fa', 2: '#29b6f6', 3: '#0288d1', 4: '#01579b', 5: '#002f6c'}
    for feat, geom in lines_en:
        o = feat['properties']['order']
        xs, ys = geom.xy
        ax.plot(xs, ys, color=colors.get(o, '#002f6c'), lw=0.8 + 0.5 * o, zorder=3)
    ax.plot(ford_en[0], ford_en[1], 'o', color='#c62828', markersize=8, zorder=5)
    ax.annotate('ford', xy=ford_en, xytext=(ford_en[0] + 8, ford_en[1] + 8),
                fontsize=8, color='#c62828')
    ax.set_aspect('equal')
    ax.set_xlabel('east (m, pack frame)')
    ax.set_ylabel('north (m, pack frame)')
    ax.set_title(
        f'Drainage (C13) - D8 channels >= {ACCUM_THRESH_M2:.0f} m2\n'
        f'ford distance to main channel: {ford_dist:.2f} m (limit {FORD_MAX_M:.0f} m)',
        fontsize=11,
    )
    legend = [
        Line2D([0], [0], color='#90a4ae', lw=0.8, label='2 m contours'),
        Line2D([0], [0], color='#0288d1', lw=2, label='channel (by Strahler)'),
        Line2D([0], [0], marker='o', color='#c62828', lw=0, label='creek ford'),
    ]
    ax.legend(handles=legend, loc='lower right', fontsize=8)
    fig.text(
        0.5, 0.01,
        'DEM: USGS 3DEP 1 m terrarium; sink-filled; D8; accum >= 2000 m2; simplify 1 m',
        ha='center', fontsize=7,
    )
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)


def main():
    parcel, e0, n0, e1, n1 = load_parcel_en()
    print(f'window EN ({e0:.0f},{n0:.0f})-({e1:.0f},{n1:.0f})')
    es, ns, Zraw = sample_dem(e0, n0, e1, n1)
    print(f'grid {Zraw.shape[1]}x{Zraw.shape[0]}  nan={int(np.isnan(Zraw).sum())}')
    Z = fill_sinks(Zraw)
    fdir, slope = d8_flow(Z)
    accum = flow_accum(fdir)
    print(f'accum max {float(np.nanmax(accum)):.0f} m2')
    segments, ups, channel = extract_channel_cells(accum, fdir, ACCUM_THRESH_M2)
    rows, cols = Z.shape
    order = strahler_orders(ups, channel, fdir, rows, cols)

    features = []
    lines_en = []
    for path in segments:
        feat, geom = path_to_line(path, es, ns, accum, slope, order)
        features.append(feat)
        lines_en.append((feat, geom))

    # Main creek line = channel nearest the ford (the valley that feeds the crossing).
    if not lines_en:
        raise SystemExit('no channels extracted')
    ford = Point(FORD_EN)
    main_feat, main_geom = min(lines_en, key=lambda t: ford.distance(t[1]))
    ford_dist = ford.distance(main_geom)
    print(f'main accum {main_feat["properties"]["accum_m2"]} m2  order {main_feat["properties"]["order"]}')
    print(f'ford to main channel: {ford_dist:.2f} m')
    # mark main for the plan
    main_feat['properties']['role'] = 'main_creek'

    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    captured = '2018'  # same lidar epoch as terrain source
    doc = {
        'type': 'FeatureCollection',
        'name': 'drainage',
        'properties': {
            'authority': 'derived',
            'captured': captured,
            'method': 'sink-fill + D8 + flow accumulation; channels >= 2000 m2; simplify 1 m; Strahler',
            'accum_thresh_m2': ACCUM_THRESH_M2,
            'ford_en_m': list(FORD_EN),
            'ford_to_main_m': round(ford_dist, 2),
            'generator': 'scripts/drainage.py',
        },
        'features': features,
    }
    OUT_GEO.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    draw_plan(es, ns, Z, lines_en, FORD_EN, ford_dist)

    if ford_dist > FORD_MAX_M:
        raise SystemExit(f'FAIL ford distance {ford_dist:.2f} m > {FORD_MAX_M} m')
    print(f'wrote {OUT_GEO} ({len(features)} lines) and {OUT_PNG}')
    print('OK')


if __name__ == '__main__':
    main()
