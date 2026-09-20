"""
Beekeeping & Honey — tool shed beside the apiary.

  WORK: store hive tools and extract honey next to the yards.
  Plan follows from that: a small enclosed tool shed (not a hall), one person door,
  work bench along the north wall. Hive pads sit outside the footprint so the
  yard stays vegetated.

  Origin: centre of the shed door threshold.

    python scripts/beekeeping.py models/beekeeping-program.glb
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, surface  # noqa: E402

BOARD = surface('board_and_batten')
STONE = surface('stone')
TIMBER = surface('timber')
METAL = surface('standing_seam_metal')


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
    m = Model('Beekeeping — tool shed by the apiary')
    # 4 × 3.5 m tool shed — honey house scale, not a barn
    x0, x1, n0, n1 = -2.0, 2.0, 0.0, 3.5
    door_w, t, h = 0.9, 0.15, 2.4

    pad = [(x0 - 0.15, n0 - 0.15), (x1 + 0.15, n0 - 0.15), (x1 + 0.15, n1 + 0.15), (x0 - 0.15, n1 + 0.15)]
    m.extrude(STONE, ring_xz(pad), -0.08, 0.0)
    floor = open_ring(ring_xz([(x0, n0), (x1, n0), (x1, n1), (x0, n1)]))
    m.extrude(STONE, floor, -0.02, 0.0)
    m.floor(floor, 0.0, 'shed floor')

    dw = door_w / 2
    thresh = open_ring(ring_xz([(-dw - 0.15, -0.8), (dw + 0.15, -0.8), (dw + 0.15, 0.0), (-dw - 0.15, 0.0)]))
    m.extrude(STONE, thresh, -0.03, 0.0)
    m.floor(thresh, 0.0, 'shed threshold')

    for label, ring in (
        ('door W', [(x0, n0), (-dw, n0), (-dw, n0 + t), (x0, n0 + t)]),
        ('door E', [(dw, n0), (x1, n0), (x1, n0 + t), (dw, n0 + t)]),
        ('east', [(x1 - t, n0), (x1, n0), (x1, n1), (x1 - t, n1)]),
        ('west', [(x0, n0), (x0 + t, n0), (x0 + t, n1), (x0, n1)]),
        ('north', [(x0, n1 - t), (x1, n1 - t), (x1, n1), (x0, n1)]),
    ):
        xz = ring_xz(ring)
        m.extrude(BOARD, xz, 0.0, h)
        m.solid(xz, 0.0, h, label)

    # Work bench along north — solid, not a second room
    bench = [(x0 + 0.25, n1 - 0.7), (x1 - 0.25, n1 - 0.7), (x1 - 0.25, n1 - 0.25), (x0 + 0.25, n1 - 0.25)]
    xz = ring_xz(bench)
    m.extrude(TIMBER, xz, 0.0, 0.9)
    m.solid(xz, 0.0, 0.9, 'work bench')

    m.quad(METAL,
           P(x0 - 0.2, n0 - 0.2, h - 0.15), P(x1 + 0.2, n0 - 0.2, h - 0.15),
           P(x1 + 0.2, n1 + 0.2, h + 0.35), P(x0 - 0.2, n1 + 0.2, h + 0.35))

    # Built footprint = shed only (hive yard outside)
    fp = [(-2.3, -0.8), (2.3, -0.8), (2.3, 3.7), (-2.3, 3.7)]
    return m, fp


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/beekeeping-program.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, fp = build()
    info = m.write(out, extras={
        'zone': 'beekeeping-program',
        'work': 'store hive tools and extract honey next to the yards',
        'origin_note': 'shed door threshold centre',
        'authority': 'proposed',
        'footprint_en_m': [[round(e, 2), round(n, 2)] for e, n in fp],
    })
    print(json.dumps({
        'bytes': info['bytes'], 'triangles': info['triangles'],
        'floors': len(m.walk['floors']), 'solids': len(m.walk['solids']),
    }))
