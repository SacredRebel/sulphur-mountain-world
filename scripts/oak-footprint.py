"""
Emit Oak Leaf models.json footprint from SOLIDS — built ground only.

  Exception list (deliberately uncleared — oaks survive):
    - oak lounge fire
    - oak lounge seat
    - standing stone

  Every other solid must sit inside the footprint.

    python scripts/oak-footprint.py
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull

ROOT = Path(__file__).resolve().parents[1]
PACK = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
MX = float(PACK['frame']['metres_per_deg_lng'])
MY = float(PACK['frame']['metres_per_deg_lat'])
ORIGIN = [-119.155333, 34.433118]

# Exactly these three — a decision, documented in C10-done.md.
EXCLUDE_SOLID_NAMES = (
    'oak lounge fire',
    'oak lounge seat',
    'standing stone',
)
PAD_M = 0.35


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


def excluded(name: str) -> bool:
    return any(name == p or name.startswith(p + ' ') for p in EXCLUDE_SOLID_NAMES)


def point_in_ring(e, n, ring):
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        ei, ni = ring[i]
        ej, nj = ring[j]
        if ((ni > n) != (nj > n)) and (e < (ej - ei) * (n - ni) / ((nj - ni) or 1e-12) + ei):
            inside = not inside
        j = i
    return inside


def dist_to_ring(e, n, ring):
    best = None
    for i in range(len(ring)):
        e0, n0 = ring[i]
        e1, n1 = ring[(i + 1) % len(ring)]
        vx, vy = e1 - e0, n1 - n0
        wx, wy = e - e0, n - n0
        c1 = vx * wx + vy * wy
        if c1 <= 0:
            d = math.hypot(e - e0, n - n0)
        else:
            c2 = vx * vx + vy * vy
            if c2 <= c1:
                d = math.hypot(e - e1, n - n1)
            else:
                t = c1 / c2
                d = math.hypot(e - (e0 + t * vx), n - (n0 + t * vy))
        if best is None or d < best:
            best = d
    return float(best or 0.0)


def solid_clearance(ring_en, footprint):
    """Metres outside: 0 if every vertex is inside or on the boundary."""
    worst = 0.0
    for e, n in ring_en:
        if point_in_ring(e, n, footprint):
            continue
        d = dist_to_ring(e, n, footprint)
        if d > worst:
            worst = d
    return worst


def densify(ring, target=56):
    if len(ring) >= target:
        return list(ring)
    out = []
    per = max(1, (target + len(ring) - 1) // len(ring))
    for i in range(len(ring)):
        a = np.asarray(ring[i], float)
        b = np.asarray(ring[(i + 1) % len(ring)], float)
        out.append(tuple(a))
        for k in range(1, per):
            t = k / per
            out.append(tuple(a * (1 - t) + b * t))
    return out[:target]


def main():
    walk = read_walk(ROOT / 'models' / 'oak-leaf-massing.glb')
    included, excluded_names = [], []
    pts = []
    for s in walk['solids']:
        name = s.get('name') or ''
        ring = xz_to_en(s['ring'])
        if excluded(name):
            excluded_names.append(name)
            continue
        included.append((name, ring))
        pts.extend(ring)

    arr = np.asarray(pts, float)
    hull = ConvexHull(arr)
    hull_ring = [tuple(arr[i]) for i in hull.vertices]
    # True-ish buffer: circle samples around each hull vertex, then re-hull
    buf = list(hull_ring)
    for e, n in hull_ring:
        for k in range(12):
            a = 2 * math.pi * k / 12
            buf.append((e + PAD_M * math.cos(a), n + PAD_M * math.sin(a)))
    barr = np.asarray(buf, float)
    bh = ConvexHull(barr)
    padded = [tuple(barr[i]) for i in bh.vertices]

    simplified = densify(padded, 56)
    area = ring_area(simplified)

    outside = []
    for name, ring in included:
        d = solid_clearance(ring, simplified)
        if d > 0.05:
            outside.append((name, round(d, 2)))
    outside.sort(key=lambda x: -x[1])

    excl_out = []
    for s in walk['solids']:
        name = s.get('name') or ''
        if not excluded(name):
            continue
        d = solid_clearance(xz_to_en(s['ring']), simplified)
        excl_out.append((name, round(d, 2)))

    footprint_ll = [en_to_ll(e, n) for e, n in simplified]
    report = {
        'n_points': len(footprint_ll),
        'area_m2': round(area, 1),
        'exception_list': list(EXCLUDE_SOLID_NAMES),
        'excluded_solid_instances': sorted(set(excluded_names)),
        'included_solids_outside': outside,
        'n_included_outside': len(outside),
        'excluded_min_distance_m': round(min((d for _, d in excl_out), default=0), 2),
    }
    print(json.dumps(report, indent=2))
    if outside:
        raise SystemExit(f'{len(outside)} included solids still outside the footprint')

    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    for m in man['models']:
        if m['id'] == 'oak-leaf-massing':
            m['footprint'] = footprint_ll
            m['note'] = (
                'Five-leaf house; chimney origin. Footprint from solids '
                f'({len(footprint_ll)} pts, {area:.0f} m²); exceptions: oak lounge fire/seat, '
                'standing stone (C10).'
            )
            break
    (ROOT / 'models.json').write_text(json.dumps(man, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('models.json updated')


if __name__ == '__main__':
    main()
