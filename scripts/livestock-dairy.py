"""
Livestock & Dairy — milking and wash-down.

  WORK: milk animals and hose the floor clean afterward.
  Plan follows from that: a wide cow door, an open south bay, a sealed wash-down
  concrete floor with a drain channel, and a small enclosed milk room on the east.
  Pasture rails stay outside the footprint.

  Origin: centre of the cow-door threshold.

    python scripts/livestock-dairy.py models/livestock-dairy.glb
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, surface  # noqa: E402

BOARD = surface('board_and_batten')
STONE = surface('stone')
CONCRETE = surface('concrete')
METAL = surface('standing_seam_metal')
TIMBER = surface('timber')


def P(e, n, y=0.0):
    return (float(e), float(y), float(-n))


def ring_xz(pts):
    return [(float(e), float(-n)) for e, n in pts]


def open_ring(pts):
    if len(pts) < 3:
        return [tuple(p) for p in pts]
    a, b = pts[0], pts[-1]
    if abs(float(a[0]) - float(b[0])) < 1e-6 and abs(float(a[1]) - float(b[1])) < 1e-6:
        return [tuple(p) for p in pts[:-1]]
    return [tuple(p) for p in pts]


def build():
    m = Model('Livestock & Dairy — cow door and wash-down')
    # Milking bay 14 × 10 m; cow door 3.0 m (an animal fits)
    x0, x1, n0, n1 = -7.0, 7.0, 0.0, 10.0
    cow_door, t, h = 3.0, 0.22, 3.4

    pad = [(x0 - 0.3, n0 - 0.3), (x1 + 0.3, n0 - 0.3), (x1 + 0.3, n1 + 0.3), (x0 - 0.3, n1 + 0.3)]
    m.extrude(CONCRETE, ring_xz(pad), -0.12, 0.0)
    # wash-down floor — sealed concrete, named for the work
    floor = open_ring(ring_xz([(x0, n0), (x1, n0), (x1, n1), (x0, n1)]))
    m.extrude(CONCRETE, floor, -0.02, 0.02)
    m.floor(floor, 0.02, 'wash-down floor')

    # drain channel down the centre (visual + low solid lip)
    drain = open_ring(ring_xz([(-0.2, n0 + 0.5), (0.2, n0 + 0.5), (0.2, n1 - 0.5), (-0.2, n1 - 0.5)]))
    m.extrude(STONE, drain, -0.08, 0.0)
    m.solid(drain, -0.08, 0.05, 'drain channel')

    dw = cow_door / 2
    thresh = open_ring(ring_xz([(-dw - 0.4, -1.5), (dw + 0.4, -1.5), (dw + 0.4, 0.0), (-dw - 0.4, 0.0)]))
    m.extrude(CONCRETE, thresh, -0.05, 0.02)
    m.floor(thresh, 0.02, 'cow threshold')

    # South — open bay with cow door gap (no full wall; posts + returns)
    for label, ring in (
        ('cow door W', [(x0, n0), (-dw, n0), (-dw, n0 + t), (x0, n0 + t)]),
        ('cow door E', [(dw, n0), (x1, n0), (x1, n0 + t), (dw, n0 + t)]),
        ('bay west', [(x0, n0), (x0 + t, n0), (x0 + t, n1), (x0, n1)]),
        ('bay east', [(x1 - t, n0), (x1, n0), (x1, n1), (x1 - t, n1)]),
        ('bay north', [(x0, n1 - t), (x1, n1 - t), (x1, n1), (x0, n1)]),
    ):
        xz = ring_xz(ring)
        m.extrude(BOARD, xz, 0.0, h)
        m.solid(xz, 0.0, h, label)

    # Posts at the open south corners
    for i, (e, n) in enumerate(((-dw - 0.15, 0.15), (dw + 0.15, 0.15))):
        post = [(e - 0.12, n - 0.12), (e + 0.12, n - 0.12), (e + 0.12, n + 0.12), (e - 0.12, n + 0.12)]
        xz = ring_xz(post)
        m.extrude(TIMBER, xz, 0.0, h)
        m.solid(xz, 0.0, h, f'bay post {i}')

    # Enclosed milk room on the east — wash-separated
    mx0, mx1, mn0, mn1 = 7.2, 11.5, 1.0, 6.0
    mh, md, mt = 2.6, 1.0, 0.15
    m.extrude(CONCRETE, ring_xz([
        (mx0 - 0.1, mn0 - 0.1), (mx1 + 0.1, mn0 - 0.1),
        (mx1 + 0.1, mn1 + 0.1), (mx0 - 0.1, mn1 + 0.1),
    ]), -0.1, 0.0)
    m.floor(ring_xz([(mx0, mn0), (mx1, mn0), (mx1, mn1), (mx0, mn1)]), 0.0, 'milk room')
    mid = 0.5 * (mx0 + mx1)
    for label, ring in (
        ('milk door W', [(mx0, mn0), (mid - md / 2, mn0), (mid - md / 2, mn0 + mt), (mx0, mn0 + mt)]),
        ('milk door E', [(mid + md / 2, mn0), (mx1, mn0), (mx1, mn0 + mt), (mid + md / 2, mn0 + mt)]),
        ('milk east', [(mx1 - mt, mn0), (mx1, mn0), (mx1, mn1), (mx1 - mt, mn1)]),
        ('milk west', [(mx0, mn0), (mx0 + mt, mn0), (mx0 + mt, mn1), (mx0, mn1)]),
        ('milk north', [(mx0, mn1 - mt), (mx1, mn1 - mt), (mx1, mn1), (mx0, mn1)]),
    ):
        xz = ring_xz(ring)
        m.extrude(BOARD, xz, 0.0, mh)
        m.solid(xz, 0.0, mh, label)
    m.quad(METAL,
           P(mx0 - 0.2, mn0 - 0.2, mh), P(mx1 + 0.2, mn0 - 0.2, mh),
           P(mx1 + 0.2, mn1 + 0.2, mh + 0.3), P(mx0 - 0.2, mn1 + 0.2, mh + 0.3))

    # Shed roof over bay
    m.quad(METAL,
           P(x0 - 0.4, n0 - 0.3, h - 0.3), P(x1 + 0.4, n0 - 0.3, h - 0.3),
           P(x1 + 0.4, n1 + 0.4, h + 0.5), P(x0 - 0.4, n1 + 0.4, h + 0.5))

    fp = [(-7.4, -1.5), (11.7, -1.5), (11.7, 10.4), (-7.4, 10.4)]
    return m, fp


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/livestock-dairy.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, fp = build()
    info = m.write(out, extras={
        'zone': 'livestock-dairy',
        'work': 'milk animals and hose the floor clean afterward',
        'origin_note': 'cow-door threshold centre',
        'authority': 'proposed',
        'footprint_en_m': [[round(e, 2), round(n, 2)] for e, n in fp],
    })
    print(json.dumps({
        'bytes': info['bytes'], 'triangles': info['triangles'],
        'floors': len(m.walk['floors']), 'solids': len(m.walk['solids']),
    }))
