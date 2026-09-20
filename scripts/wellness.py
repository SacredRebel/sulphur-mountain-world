"""
Wellness Facilities — small enclosed quiet rooms.

  The opposite of a hall: a short corridor with three treatment rooms on the east and one
  on the west, each enclosed. Low shed roof, timber. Intimate, not one gatherable volume.

  Occupancy (derived):
    rooms — seated / quiet class @ 1.4 m²/person
    corridor — standing/reception @ 0.5 m²/person

  Origin: centre of the south corridor door threshold.

    python scripts/wellness.py models/wellness-facilities.glb
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model  # noqa: E402
from gathering import (  # noqa: E402
    BOARD, GLASS, METAL, P, SEATED, STANDING, STONE, TIMBER,
    capacity, door_width_m, floor_rect, open_ring, ring_xz, solid_wall, wall_gap,
)


def build():
    m = Model('Wellness Facilities — quiet rooms')
    t, h = 0.2, 2.8

    # Corridor: 2.2 × 12 m
    cx0, cx1, cn0, cn1 = -1.1, 1.1, 0.0, 12.0
    east_rooms = [
        ('room south', 1.1, 5.1, 0.5, 4.0),
        ('room mid', 1.1, 5.1, 4.5, 8.0),
        ('room north', 1.1, 5.1, 8.5, 12.0),
    ]
    wx0, wx1, wn0, wn1 = -5.1, -1.1, 4.0, 9.0

    corr_m2 = floor_rect(m, STONE, 'corridor', cx0, cn0, cx1, cn1)
    areas = {}
    for name, x0, x1, n0, n1 in east_rooms:
        areas[name] = floor_rect(m, TIMBER, name, x0, n0, x1, n1)
    areas['room west'] = floor_rect(m, TIMBER, 'room west', wx0, wn0, wx1, wn1)

    clear_m2 = corr_m2 + sum(areas.values())
    corr_stand = capacity(corr_m2, STANDING)
    room_caps = {n: capacity(a, SEATED) for n, a in areas.items()}
    design = corr_stand + sum(room_caps.values())

    door_s = door_width_m(design, n_exits=2)
    door_n = door_width_m(design, n_exits=2)

    pad = [(-5.5, -0.4), (5.5, -0.4), (5.5, 12.4), (-5.5, 12.4)]
    m.extrude(STONE, ring_xz(pad), -0.12, 0.0)

    dw = door_s / 2
    thresh = open_ring(ring_xz([(-dw - 0.2, -1.2), (dw + 0.2, -1.2), (dw + 0.2, 0.0), (-dw - 0.2, 0.0)]))
    m.extrude(STONE, thresh, -0.05, 0.0)
    m.floor(thresh, 0.0, 'entry threshold')

    wall_gap(m, BOARD, 'entry door W', 'entry door E', cx0, cx1, cn0, t, h, door_s)
    wall_gap(m, BOARD, 'garden door W', 'garden door E', cx0, cx1, cn1 - t, t, h, door_n)

    nd = door_n / 2
    nth = open_ring(ring_xz([(-nd - 0.2, cn1), (nd + 0.2, cn1), (nd + 0.2, cn1 + 1.2), (-nd - 0.2, cn1 + 1.2)]))
    m.extrude(STONE, nth, -0.05, 0.0)
    m.floor(nth, 0.0, 'garden threshold')

    # Corridor long walls with openings into rooms
    solid_wall(m, BOARD, 'corridor west S', [(cx0, cn0), (cx0 + t, cn0), (cx0 + t, wn0), (cx0, wn0)], h)
    solid_wall(m, BOARD, 'corridor west N', [(cx0, wn1), (cx0 + t, wn1), (cx0 + t, cn1), (cx0, cn1)], h)
    # East corridor: solid between room door gaps
    solid_wall(m, BOARD, 'corridor east S', [(cx1 - t, cn0), (cx1, cn0), (cx1, 0.5), (cx1 - t, 0.5)], h)
    solid_wall(m, BOARD, 'corridor east ab', [(cx1 - t, 4.0), (cx1, 4.0), (cx1, 4.5), (cx1 - t, 4.5)], h)
    solid_wall(m, BOARD, 'corridor east bc', [(cx1 - t, 8.0), (cx1, 8.0), (cx1, 8.5), (cx1 - t, 8.5)], h)

    for name, x0, x1, n0, n1 in east_rooms:
        solid_wall(m, TIMBER, f'{name} east', [(x1 - t, n0), (x1, n0), (x1, n1), (x1 - t, n1)], h)
        solid_wall(m, TIMBER, f'{name} south', [(x0, n0), (x1, n0), (x1, n0 + t), (x0, n0 + t)], h)
        solid_wall(m, TIMBER, f'{name} north', [(x0, n1 - t), (x1, n1 - t), (x1, n1), (x0, n1)], h)
        m.grid(GLASS, [
            [P(x1, n0 + 0.7, 0.8), P(x1, n1 - 0.7, 0.8)],
            [P(x1, n0 + 0.7, 2.1), P(x1, n1 - 0.7, 2.1)],
        ], up=True)

    solid_wall(m, TIMBER, 'room west west', [(wx0, wn0), (wx0 + t, wn0), (wx0 + t, wn1), (wx0, wn1)], h)
    solid_wall(m, TIMBER, 'room west south', [(wx0, wn0), (wx1, wn0), (wx1, wn0 + t), (wx0, wn0 + t)], h)
    solid_wall(m, TIMBER, 'room west north', [(wx0, wn1 - t), (wx1, wn1 - t), (wx1, wn1), (wx0, wn1)], h)
    m.grid(GLASS, [
        [P(wx0, wn0 + 0.7, 0.8), P(wx0, wn1 - 0.7, 0.8)],
        [P(wx0, wn0 + 0.7, 2.1), P(wx0, wn1 - 0.7, 2.1)],
    ], up=True)

    m.quad(METAL, P(-5.4, -0.3, h + 0.9), P(-5.4, 12.3, h + 0.9),
           P(5.4, 12.3, h + 0.2), P(5.4, -0.3, h + 0.2))

    use = {
        'corridor': {
            'area_m2': round(corr_m2, 1), 'factor_m2_per_person': STANDING,
            'factor_name': 'standing/reception', 'occupancy': corr_stand,
        },
    }
    for n, a in areas.items():
        use[n] = {
            'area_m2': round(a, 1), 'factor_m2_per_person': SEATED,
            'factor_name': 'seated at tables', 'occupancy': room_caps[n],
        }

    meta = {
        'use': use,
        'clear_floor_m2': round(clear_m2, 1),
        'design_occupancy': design,
        'main_door_w_m': door_s,
        'second_exit': True,
        'second_door_w_m': door_n,
        'egress_mm_per_person': 28,
        'egress_note': 'total clear width 28 mm/person across two exits',
        'plan': 'corridor + three east rooms + one west room',
        'roof': 'low shed sloping east',
    }
    return m, meta


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/wellness-facilities.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, meta = build()
    info = m.write(out, extras={
        'authority': 'proposed',
        'origin_note': 'south corridor door threshold centre',
        'gathering': meta,
        'footprint_en_m': [[-5.5, -1.2], [5.5, -1.2], [5.5, 13.2], [-5.5, 13.2]],
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
