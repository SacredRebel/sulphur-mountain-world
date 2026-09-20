"""
Farmstead Produce Stand — roadside sales, no interior.

  WORK: sell produce at the road edge; customers stay outside.
  Plan follows from that: a counter under a canopy, open on the road (south) side,
  back and side screens only. There is nowhere to stand indoors — no enclosed room,
  no enterable interior. The walk floor is the serving apron in front of the counter.

  Origin: centre of the apron edge facing the road.

    python scripts/produce-stand.py models/farmstead-produce-stand.glb
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
    m = Model('Farmstead Produce Stand — open to the road')
    # Counter 5 m wide; canopy 6 × 3.5; open south to the road
    # Staff side is north of the counter — not an enclosed room
    cx0, cx1 = -2.5, 2.5
    counter_n, counter_d = 1.2, 0.55
    canopy_n0, canopy_n1 = 0.0, 3.2
    h_counter, h_canopy = 1.05, 2.6

    # Serving apron — the only walk floor (customers stand here, outdoors)
    apron = open_ring(ring_xz([
        (cx0 - 0.5, -1.8), (cx1 + 0.5, -1.8),
        (cx1 + 0.5, counter_n), (cx0 - 0.5, counter_n),
    ]))
    m.extrude(STONE, apron, -0.06, 0.02)
    m.floor(apron, 0.02, 'serving apron')

    # Counter — solid barrier; you buy across it, you do not walk through it
    counter = open_ring(ring_xz([
        (cx0, counter_n), (cx1, counter_n),
        (cx1, counter_n + counter_d), (cx0, counter_n + counter_d),
    ]))
    m.extrude(TIMBER, counter, 0.0, h_counter)
    m.solid(counter, 0.0, h_counter, 'counter')

    # Back screen and side screens (wind / display) — open south, no door, no room
    t = 0.12
    for label, ring in (
        ('back screen', [(cx0 - 0.3, canopy_n1 - t), (cx1 + 0.3, canopy_n1 - t),
                         (cx1 + 0.3, canopy_n1), (cx0 - 0.3, canopy_n1)]),
        ('west screen', [(cx0 - 0.3, counter_n + counter_d), (cx0 - 0.3 + t, counter_n + counter_d),
                         (cx0 - 0.3 + t, canopy_n1), (cx0 - 0.3, canopy_n1)]),
        ('east screen', [(cx1 + 0.3 - t, counter_n + counter_d), (cx1 + 0.3, counter_n + counter_d),
                         (cx1 + 0.3, canopy_n1), (cx1 + 0.3 - t, canopy_n1)]),
    ):
        xz = ring_xz(ring)
        m.extrude(BOARD, xz, 0.0, 1.8)
        m.solid(xz, 0.0, 1.8, label)

    # Display shelves behind counter (solids) — still not a room
    shelf = open_ring(ring_xz([
        (cx0 + 0.2, canopy_n1 - 0.9), (cx1 - 0.2, canopy_n1 - 0.9),
        (cx1 - 0.2, canopy_n1 - 0.35), (cx0 + 0.2, canopy_n1 - 0.35),
    ]))
    m.extrude(TIMBER, shelf, 0.0, 1.5)
    m.solid(shelf, 0.0, 1.5, 'display shelf')

    # Posts + canopy — open air under the roof
    for i, e in enumerate((cx0 - 0.2, cx1 + 0.2)):
        for j, n in enumerate((0.15, canopy_n1 - 0.15)):
            post = [(e - 0.1, n - 0.1), (e + 0.1, n - 0.1), (e + 0.1, n + 0.1), (e - 0.1, n + 0.1)]
            xz = ring_xz(post)
            m.extrude(TIMBER, xz, 0.0, h_canopy)
            m.solid(xz, 0.0, h_canopy, f'post {i}{j}')

    m.quad(METAL,
           P(cx0 - 0.6, canopy_n0 - 0.3, h_canopy), P(cx1 + 0.6, canopy_n0 - 0.3, h_canopy),
           P(cx1 + 0.6, canopy_n1 + 0.4, h_canopy + 0.25), P(cx0 - 0.6, canopy_n1 + 0.4, h_canopy + 0.25))

    # No enclosed floor north of the counter — staff stand on the same open pad if needed
    # (a thin gravel strip, still outdoors — not an interior)
    staff = open_ring(ring_xz([
        (cx0 - 0.3, counter_n + counter_d), (cx1 + 0.3, counter_n + counter_d),
        (cx1 + 0.3, canopy_n1 - 0.1), (cx0 - 0.3, canopy_n1 - 0.1),
    ]))
    m.extrude(STONE, staff, -0.04, 0.0)
    m.floor(staff, 0.0, 'staff apron')  # outdoors under canopy — not an enterable room

    fp = [(cx0 - 0.6, -1.8), (cx1 + 0.6, -1.8), (cx1 + 0.6, canopy_n1 + 0.2), (cx0 - 0.6, canopy_n1 + 0.2)]
    return m, fp


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/farmstead-produce-stand.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, fp = build()
    info = m.write(out, extras={
        'zone': 'farmstead-produce-stand',
        'work': 'sell produce at the road edge; customers stay outside',
        'enterable_interior': False,
        'origin_note': 'apron edge facing the road',
        'authority': 'proposed',
        'footprint_en_m': [[round(e, 2), round(n, 2)] for e, n in fp],
    })
    print(json.dumps({
        'bytes': info['bytes'], 'triangles': info['triangles'],
        'floors': len(m.walk['floors']), 'solids': len(m.walk['solids']),
        'enterable_interior': False,
    }))
