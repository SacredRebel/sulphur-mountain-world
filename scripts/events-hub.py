"""
Events & Gatherings Hub — one clear volume with the structure overhead.

  Nothing in the middle. Timber ribs span the hall; standing-seam gable. Two exits
  (south main, north secondary), doors sized from seated occupancy.

  Occupancy (derived): seated at tables @ 1.4 m²/person over the clear floor.

  Origin: centre of the south door threshold.

    python scripts/events-hub.py models/events-gatherings-hub.glb
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model  # noqa: E402
from gathering import (  # noqa: E402
    GLASS, METAL, P, SEATED, STONE, STUCCO, TIMBER,
    capacity, door_width_m, floor_rect, needs_second_exit, open_ring, ring_xz,
    solid_wall, wall_gap,
)


def build():
    m = Model('Events & Gatherings Hub — clear-span hall')
    # Clear interior 16 × 11 m — one room, no partitions
    w, d = 16.0, 11.0
    x0, x1, n0, n1 = -w / 2, w / 2, 0.0, d
    t, h = 0.28, 5.0
    ridge = 2.4

    clear_m2 = floor_rect(m, STONE, 'hall floor', x0, n0, x1, n1)
    design = capacity(clear_m2, SEATED)  # seated at tables
    assert needs_second_exit(design)
    door_s = door_width_m(design, n_exits=2)
    door_n = door_width_m(design, n_exits=2)

    pad = [(x0 - 0.5, n0 - 0.5), (x1 + 0.5, n0 - 0.5), (x1 + 0.5, n1 + 0.5), (x0 - 0.5, n1 + 0.5)]
    m.extrude(STONE, ring_xz(pad), -0.18, 0.0)

    dw = door_s / 2
    thresh = open_ring(ring_xz([(-dw - 0.4, -1.6), (dw + 0.4, -1.6), (dw + 0.4, 0.0), (-dw - 0.4, 0.0)]))
    m.extrude(STONE, thresh, -0.05, 0.0)
    m.floor(thresh, 0.0, 'south threshold')

    # South — main exit
    wall_gap(m, STUCCO, 'south door W', 'south door E', x0, x1, n0, t, h, door_s)
    # North — second exit
    wall_gap(m, STUCCO, 'north door W', 'north door E', x0, x1, n1 - t, t, h, door_n)
    # East / west continuous
    solid_wall(m, STUCCO, 'east wall', [(x1 - t, n0), (x1, n0), (x1, n1), (x1 - t, n1)], h)
    solid_wall(m, STUCCO, 'west wall', [(x0, n0), (x0 + t, n0), (x0 + t, n1), (x0, n1)], h)

    nd = door_n / 2
    nth = open_ring(ring_xz([(-nd - 0.4, n1), (nd + 0.4, n1), (nd + 0.4, n1 + 1.6), (-nd - 0.4, n1 + 1.6)]))
    m.extrude(STONE, nth, -0.05, 0.0)
    m.floor(nth, 0.0, 'north threshold')

    # High glass on long walls (structure still readable)
    for na, nb in ((2.0, 4.5), (6.5, 9.0)):
        m.grid(GLASS, [[P(x1, na, 1.2), P(x1, nb, 1.2)], [P(x1, na, h - 0.8), P(x1, nb, h - 0.8)]], up=True)
        m.grid(GLASS, [[P(x0, nb, 1.2), P(x0, na, 1.2)], [P(x0, nb, h - 0.8), P(x0, na, h - 0.8)]], up=True)

    # Gable roof
    m.quad(METAL, P(x0 - 0.4, n0 - 0.4, h), P(x0 - 0.4, n1 + 0.4, h),
           P(0.0, n1 + 0.4, h + ridge), P(0.0, n0 - 0.4, h + ridge))
    m.quad(METAL, P(0.0, n0 - 0.4, h + ridge), P(0.0, n1 + 0.4, h + ridge),
           P(x1 + 0.4, n1 + 0.4, h), P(x1 + 0.4, n0 - 0.4, h))

    # Overhead timber ribs — clear span, nothing on the floor in the middle
    for i, n in enumerate((2.0, 4.0, 6.0, 8.0, 10.0)):
        # Tie beam across
        path = [P(x0 + 0.4, n, h - 0.35), P(x1 - 0.4, n, h - 0.35)]
        m.sweep(TIMBER, path, 0.22, 0.35)
        # Two rafters to ridge
        m.sweep(TIMBER, [P(x0 + 0.4, n, h - 0.2), P(0.0, n, h + ridge - 0.15)], 0.18, 0.28)
        m.sweep(TIMBER, [P(x1 - 0.4, n, h - 0.2), P(0.0, n, h + ridge - 0.15)], 0.18, 0.28)

    meta = {
        'use': {
            'hall': {
                'area_m2': round(clear_m2, 1),
                'factor_m2_per_person': SEATED,
                'factor_name': 'seated at tables',
                'occupancy': design,
            },
        },
        'clear_floor_m2': round(clear_m2, 1),
        'design_occupancy': design,
        'main_door_w_m': door_s,
        'second_exit': True,
        'second_door_w_m': door_n,
        'egress_mm_per_person': 28,
        'egress_note': 'total clear width 28 mm/person across two exits (~3.5 m total at this occupancy)',
        'plan': 'single clear volume, no partitions',
        'roof': 'gable with five overhead timber ribs',
        'structure': 'exposed tie beams + rafters — nothing in the middle of the floor',
    }
    return m, meta


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/events-gatherings-hub.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, meta = build()
    info = m.write(out, extras={
        'authority': 'proposed',
        'origin_note': 'south door threshold centre',
        'gathering': meta,
        'footprint_en_m': [[-8.5, -1.6], [8.5, -1.6], [8.5, 12.6], [-8.5, 12.6]],
    })
    print(json.dumps({
        'bytes': info['bytes'], 'triangles': info['triangles'],
        'floors': len(m.walk['floors']), 'solids': len(m.walk['solids']),
        'design_occupancy': meta['design_occupancy'],
        'clear_floor_m2': meta['clear_floor_m2'],
        'main_door_w_m': meta['main_door_w_m'],
        'second_door_w_m': meta['second_door_w_m'],
        'use': meta['use'],
    }))
