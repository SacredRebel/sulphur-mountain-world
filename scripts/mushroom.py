"""
Mushroom Cultivation — dark sealed grow room.

  WORK: grow mushrooms in controlled dark climate.
  Plan follows from that: a small opaque box, almost no glass, a single personnel
  door, low eaves, sealed walls. Not a shed with windows — light is the enemy.

  Origin: centre of the personnel-door threshold.

    python scripts/mushroom.py models/mushroom-cultivation.glb
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, surface  # noqa: E402

BOARD = surface('board_and_batten')
STONE = surface('stone')
METAL = surface('standing_seam_metal')
CONCRETE = surface('concrete')


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
    m = Model('Mushroom Cultivation — dark sealed grow room')
    # Compact 8 × 6 m sealed volume — commercial climate box, not a barn
    x0, x1, n0, n1 = -4.0, 4.0, 0.0, 6.0
    door_w, t, h = 0.95, 0.2, 2.5  # low eaves, person door only

    pad = [(x0 - 0.15, n0 - 0.15), (x1 + 0.15, n0 - 0.15), (x1 + 0.15, n1 + 0.15), (x0 - 0.15, n1 + 0.15)]
    m.extrude(CONCRETE, ring_xz(pad), -0.1, 0.0)
    floor = open_ring(ring_xz([(x0, n0), (x1, n0), (x1, n1), (x0, n1)]))
    m.extrude(STONE, floor, -0.02, 0.0)
    m.floor(floor, 0.0, 'grow floor')

    dw = door_w / 2
    thresh = open_ring(ring_xz([(-dw - 0.2, -1.0), (dw + 0.2, -1.0), (dw + 0.2, 0.0), (-dw - 0.2, 0.0)]))
    m.extrude(CONCRETE, thresh, -0.04, 0.0)
    m.floor(thresh, 0.0, 'personnel threshold')

    # Continuous opaque walls — door is a gap; no windows
    for label, ring in (
        ('door W', [(x0, n0), (-dw, n0), (-dw, n0 + t), (x0, n0 + t)]),
        ('door E', [(dw, n0), (x1, n0), (x1, n0 + t), (dw, n0 + t)]),
        ('east wall', [(x1 - t, n0), (x1, n0), (x1, n1), (x1 - t, n1)]),
        ('west wall', [(x0, n0), (x0 + t, n0), (x0 + t, n1), (x0, n1)]),
        ('north wall', [(x0, n1 - t), (x1, n1 - t), (x1, n1), (x0, n1)]),
    ):
        xz = ring_xz(ring)
        m.extrude(BOARD, xz, 0.0, h)
        m.solid(xz, 0.0, h, label)

    # Flat metal roof — sealed box, low
    m.quad(METAL,
           P(x0 - 0.25, n0 - 0.25, h), P(x1 + 0.25, n0 - 0.25, h),
           P(x1 + 0.25, n1 + 0.25, h + 0.15), P(x0 - 0.25, n1 + 0.25, h + 0.15))

    # Internal rack stubs (solids) — grow shelves, not walkable rooms
    for i, n in enumerate((1.5, 3.0, 4.5)):
        rack = [(x0 + 0.4, n - 0.15), (x1 - 0.4, n - 0.15), (x1 - 0.4, n + 0.15), (x0 + 0.4, n + 0.15)]
        xz = ring_xz(rack)
        m.extrude(BOARD, xz, 0.4, 2.1)
        m.solid(xz, 0.4, 2.1, f'rack {i}')

    fp = [(-4.3, -1.0), (4.3, -1.0), (4.3, 6.3), (-4.3, 6.3)]
    return m, fp


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/mushroom-cultivation.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, fp = build()
    info = m.write(out, extras={
        'zone': 'mushroom-cultivation',
        'work': 'grow mushrooms in controlled dark climate',
        'origin_note': 'personnel-door threshold centre',
        'authority': 'proposed',
        'footprint_en_m': [[round(e, 2), round(n, 2)] for e, n in fp],
    })
    print(json.dumps({
        'bytes': info['bytes'], 'triangles': info['triangles'],
        'floors': len(m.walk['floors']), 'solids': len(m.walk['solids']),
    }))
