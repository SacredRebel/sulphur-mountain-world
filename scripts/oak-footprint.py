"""
Emit Oak Leaf models.json footprint — built ground only.

  Excludes oak lounge and garden stones so recorded oaks there survive.
  Raster-unions built floors; exterior is the angle-sorted boundary-cell ring,
  then RDP-simplified toward ~56 vertices.

    python scripts/oak-footprint.py
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PACK = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
MX = float(PACK['frame']['metres_per_deg_lng'])
MY = float(PACK['frame']['metres_per_deg_lat'])
ORIGIN = [-119.155333, 34.433118]
EXCLUDE_PREFIXES = ('oak lounge', 'garden stone')


def read_walk(path: Path):
    data = path.read_bytes()
    off, doc = 12, None
    while off + 8 <= len(data):
        clen, ctype = struct.unpack_from('<II', data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk)
    for n in doc['nodes']:
        if 'walk' in n.get('extras', {}):
            return n['extras']['walk']
    raise SystemExit('no walk')


def ring_area(ring):
    s = 0.0
    for i in range(len(ring)):
        e0, n0 = ring[i]
        e1, n1 = ring[(i + 1) % len(ring)]
        s += e0 * n1 - e1 * n0
    return abs(s) * 0.5


def xz_to_en(ring_xz):
    return [(float(x), float(-z)) for x, z in ring_xz]


def en_to_ll(e, n):
    return [round(ORIGIN[0] + e / MX, 7), round(ORIGIN[1] + n / MY, 7)]


def point_in_ring(e, n, ring):
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        ei, ni = ring[i]
        ej, nj = ring[j]
        if ((ni > n) != (nj > n)) and (e < (ej - ei) * (n - ni) / ((nj - ni) or 1e-12) + ei):
            inside = not inside
        j = i
    return inside


def fill_rings(rings, cell=0.5):
    xs = [e for r in rings for e, _ in r]
    ns = [n for r in rings for _, n in r]
    e0, e1 = min(xs) - cell, max(xs) + cell
    n0, n1 = min(ns) - cell, max(ns) + cell
    w = int(math.ceil((e1 - e0) / cell)) + 1
    h = int(math.ceil((n1 - n0) / cell)) + 1
    grid = np.zeros((h, w), dtype=np.uint8)
    bbs = []
    for ring in rings:
        re = [p[0] for p in ring]
        rn = [p[1] for p in ring]
        bbs.append((min(re), max(re), min(rn), max(rn)))
    for iy in range(h):
        n = n0 + (iy + 0.5) * cell
        for ix in range(w):
            e = e0 + (ix + 0.5) * cell
            for ring, (emin, emax, nmin, nmax) in zip(rings, bbs):
                if e < emin or e > emax or n < nmin or n > nmax:
                    continue
                if point_in_ring(e, n, ring):
                    grid[iy, ix] = 1
                    break
    return grid, e0, n0, cell


def boundary_ring(grid, e0, n0, cell):
    """Boundary cells ordered by angle around centroid — open ring."""
    h, w = grid.shape

    def empty(y, x):
        return y < 0 or x < 0 or y >= h or x >= w or grid[y, x] == 0

    pts = []
    for iy in range(h):
        for ix in range(w):
            if grid[iy, ix] == 0:
                continue
            if empty(iy - 1, ix) or empty(iy + 1, ix) or empty(iy, ix - 1) or empty(iy, ix + 1):
                pts.append((e0 + (ix + 0.5) * cell, n0 + (iy + 0.5) * cell))
    if len(pts) < 8:
        return pts
    ce = sum(p[0] for p in pts) / len(pts)
    cn = sum(p[1] for p in pts) / len(pts)
    pts.sort(key=lambda p: math.atan2(p[1] - cn, p[0] - ce))
    return pts


def rdp(points, eps):
    if len(points) < 3:
        return points

    def _rdp(pts):
        if len(pts) < 3:
            return pts
        a = np.asarray(pts[0], float)
        b = np.asarray(pts[-1], float)
        ab = b - a
        lab = float(np.linalg.norm(ab)) or 1.0
        dmax, idx = 0.0, 0
        for i in range(1, len(pts) - 1):
            p = np.asarray(pts[i], float)
            d = abs(ab[0] * (a[1] - p[1]) - ab[1] * (a[0] - p[0])) / lab
            if d > dmax:
                dmax, idx = float(d), i
        if dmax > eps:
            return _rdp(pts[: idx + 1])[:-1] + _rdp(pts[idx:])
        return [pts[0], pts[-1]]

    return _rdp(points)


def main():
    walk = read_walk(ROOT / 'models' / 'oak-leaf-massing.glb')
    rings, skipped = [], []
    for f in walk['floors']:
        name = f.get('name') or ''
        if any(name == p or name.startswith(p + ' ') or name.startswith(p + ' step') for p in EXCLUDE_PREFIXES):
            skipped.append(name)
            continue
        if ' step ' in name or name.startswith('pool rim') or name.startswith('hot tub rim'):
            continue
        rings.append(xz_to_en(f['ring']))

    grid, e0, n0, cell = fill_rings(rings, cell=0.5)
    outline = boundary_ring(grid, e0, n0, cell)
    if len(outline) < 8:
        raise SystemExit(f'outline too short: {len(outline)}')

    # angle-sorted boundary → ~56 pts (concave-ish). Prefer under-clearing to the old AABB.
    stride = max(1, len(outline) // 56)
    simplified = outline[::stride]
    for eps in (0.3, 0.45, 0.6, 0.75, 0.9):
        cand = rdp(outline + [outline[0]], eps)[:-1]
        if len(cand) < 45:
            break
        simplified = cand
        if 50 <= len(cand) <= 60:
            break
    raster_area = float(grid.sum()) * cell * cell
    hull_ring = simplified  # report field

    area = ring_area(simplified)
    old_ll = [
        [-119.1556053, 34.43289], [-119.1550014, 34.43289],
        [-119.1550014, 34.4333414], [-119.1556053, 34.4333414],
    ]
    old_en = [((ll[0] - ORIGIN[0]) * MX, (ll[1] - ORIGIN[1]) * MY) for ll in old_ll]
    footprint_ll = [en_to_ll(e, n) for e, n in simplified]

    report = {
        'n_points': len(footprint_ll),
        'area_m2': round(area, 1),
        'raster_built_m2': round(raster_area, 1),
        'old_aabb_area_m2': round(ring_area(old_en), 1),
        'excluded_floor_names': sorted(set(skipped)),
        'filled_cells': int(grid.sum()),
        'boundary_cells': len(outline),
        'hull_vertices': len(simplified),
    }
    print(json.dumps(report, indent=2))
    if area < 500 or area > 2000:
        raise SystemExit(f'area {area} out of expected range')

    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    for m in man['models']:
        if m['id'] == 'oak-leaf-massing':
            m['footprint'] = footprint_ll
            m['note'] = (
                'Five-leaf house; chimney origin. Footprint is built ground only '
                f'({len(footprint_ll)} pts, {area:.0f} m²) — oak lounge and garden stones outside '
                'so recorded oaks survive. C8 water contract on pool/fire.'
            )
            break
    (ROOT / 'models.json').write_text(json.dumps(man, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('models.json updated')


if __name__ == '__main__':
    main()
