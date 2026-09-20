"""
Community Hub — everyday divisible gathering place.

  Not one hall: a foyer with two side rooms (west lounge, east meeting) so several
  things can happen at once. Crossed shed roofs, board-and-batten. Two exits.

  Occupancy (derived):
    foyer  — standing/reception @ 0.5 m²/person
    rooms  — seated at tables @ 1.4 m²/person
    design = foyer standing + rooms seated

  Origin: centre of the south foyer door threshold.

    python scripts/community-hub.py models/community-hub.glb
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
    capacity, door_width_m, floor_rect, needs_second_exit, open_ring, ring_xz,
    solid_wall, wall_gap,
)


def build():
    m = Model('Community Hub — divisible everyday rooms')
    t, h = 0.22, 3.2

    # Foyer (south centre): 6 × 5 m
    fx0, fx1, fn0, fn1 = -3.0, 3.0, 0.0, 5.0
    # West lounge: 5 × 6 m
    wx0, wx1, wn0, wn1 = -8.0, -3.0, 0.0, 6.0
    # East meeting: 5 × 6 m
    ex0, ex1, en0, en1 = 3.0, 8.0, 0.0, 6.0

    foyer_m2 = floor_rect(m, STONE, 'foyer', fx0, fn0, fx1, fn1)
    west_m2 = floor_rect(m, TIMBER, 'west lounge', wx0, wn0, wx1, wn1)
    east_m2 = floor_rect(m, TIMBER, 'east meeting', ex0, en0, ex1, en1)
    clear_m2 = foyer_m2 + west_m2 + east_m2

    foyer_standing = capacity(foyer_m2, STANDING)
    west_seated = capacity(west_m2, SEATED)
    east_seated = capacity(east_m2, SEATED)
    design = foyer_standing + west_seated + east_seated

    half_cap = int(math.ceil(design / 2))
    n_exits = 2 if needs_second_exit(design) else 1
    main_door = door_width_m(design, n_exits=n_exits)
    side_door = door_width_m(design, n_exits=n_exits) if n_exits > 1 else 1.0

    pad = [(-8.4, -0.4), (9.8, -0.4), (9.8, 6.4), (-8.4, 6.4)]
    m.extrude(STONE, ring_xz(pad), -0.15, 0.0)

    dw = main_door / 2
    thresh = open_ring(ring_xz([(-dw - 0.3, -1.4), (dw + 0.3, -1.4), (dw + 0.3, 0.0), (-dw - 0.3, 0.0)]))
    m.extrude(STONE, thresh, -0.05, 0.0)
    m.floor(thresh, 0.0, 'foyer threshold')

    # Foyer south — main door
    wall_gap(m, BOARD, 'foyer door W', 'foyer door E', fx0, fx1, fn0, t, h, main_door)
    solid_wall(m, BOARD, 'foyer west', [(fx0, fn0), (fx0 + t, fn0), (fx0 + t, fn1), (fx0, fn1)], h)
    solid_wall(m, BOARD, 'foyer east', [(fx1 - t, fn0), (fx1, fn0), (fx1, fn1), (fx1 - t, fn1)], h)
    solid_wall(m, BOARD, 'foyer north', [(fx0, fn1 - t), (fx1, fn1 - t), (fx1, fn1), (fx0, fn1)], h)

    # West lounge — closed box with opening to foyer (gap on east face, south half open)
    solid_wall(m, BOARD, 'lounge south', [(wx0, wn0), (wx1, wn0), (wx1, wn0 + t), (wx0, wn0 + t)], h)
    solid_wall(m, BOARD, 'lounge west', [(wx0, wn0), (wx0 + t, wn0), (wx0 + t, wn1), (wx0, wn1)], h)
    solid_wall(m, BOARD, 'lounge north', [(wx0, wn1 - t), (wx1, wn1 - t), (wx1, wn1), (wx0, wn1)], h)
    # East of lounge: only north half solid — south half is the opening into the foyer
    solid_wall(m, BOARD, 'lounge east return', [(wx1 - t, 2.5), (wx1, 2.5), (wx1, wn1), (wx1 - t, wn1)], h)

    # East meeting — mirror; second exit punched in the east wall
    solid_wall(m, BOARD, 'meeting south', [(ex0, en0), (ex1, en0), (ex1, en0 + t), (ex0, en0 + t)], h)
    solid_wall(m, BOARD, 'meeting north', [(ex0, en1 - t), (ex1, en1 - t), (ex1, en1), (ex0, en1)], h)
    solid_wall(m, BOARD, 'meeting west return', [(ex0, 2.5), (ex0 + t, 2.5), (ex0 + t, en1), (ex0, en1)], h)
    # East wall with second exit gap
    mid_n = 0.5 * (en0 + en1)
    sd = side_door / 2
    solid_wall(m, BOARD, 'meeting exit N',
               [(ex1 - t, mid_n + sd), (ex1, mid_n + sd), (ex1, en1), (ex1 - t, en1)], h)
    solid_wall(m, BOARD, 'meeting exit S',
               [(ex1 - t, en0), (ex1, en0), (ex1, mid_n - sd), (ex1 - t, mid_n - sd)], h)

    eth = open_ring(ring_xz([
        (ex1, mid_n - sd - 0.2), (ex1 + 1.2, mid_n - sd - 0.2),
        (ex1 + 1.2, mid_n + sd + 0.2), (ex1, mid_n + sd + 0.2),
    ]))
    m.extrude(STONE, eth, -0.05, 0.0)
    m.floor(eth, 0.0, 'east exit threshold')

    # Dividers between foyer and wings (partial — rooms stay distinct)
    solid_wall(m, TIMBER, 'west divider', [(-3.0 - t, 2.5), (-3.0, 2.5), (-3.0, fn1), (-3.0 - t, fn1)], h)
    solid_wall(m, TIMBER, 'east divider', [(3.0, 2.5), (3.0 + t, 2.5), (3.0 + t, fn1), (3.0, fn1)], h)

    m.grid(GLASS, [[P(wx0, 1.5, 0.9), P(wx0, 4.0, 0.9)], [P(wx0, 1.5, 2.4), P(wx0, 4.0, 2.4)]], up=True)
    m.grid(GLASS, [[P(ex1, 5.0, 0.9), P(ex1, 5.5, 0.9)], [P(ex1, 5.0, 2.4), P(ex1, 5.5, 2.4)]], up=True)

    # Crossed shed roofs
    m.quad(METAL, P(fx0 - 0.2, fn0 - 0.2, h), P(fx1 + 0.2, fn0 - 0.2, h),
           P(fx1 + 0.2, fn1 + 0.2, h + 0.6), P(fx0 - 0.2, fn1 + 0.2, h + 0.6))
    m.quad(METAL, P(wx1 + 0.1, wn0 - 0.2, h + 0.3), P(wx1 + 0.1, wn1 + 0.2, h + 0.3),
           P(wx0 - 0.3, wn1 + 0.2, h + 1.1), P(wx0 - 0.3, wn0 - 0.2, h + 1.1))
    m.quad(METAL, P(ex0 - 0.1, en0 - 0.2, h + 0.3), P(ex0 - 0.1, en1 + 0.2, h + 0.3),
           P(ex1 + 0.3, en1 + 0.2, h + 1.1), P(ex1 + 0.3, en0 - 0.2, h + 1.1))

    meta = {
        'use': {
            'foyer': {
                'area_m2': round(foyer_m2, 1), 'factor_m2_per_person': STANDING,
                'factor_name': 'standing/reception', 'occupancy': foyer_standing,
            },
            'west_lounge': {
                'area_m2': round(west_m2, 1), 'factor_m2_per_person': SEATED,
                'factor_name': 'seated at tables', 'occupancy': west_seated,
            },
            'east_meeting': {
                'area_m2': round(east_m2, 1), 'factor_m2_per_person': SEATED,
                'factor_name': 'seated at tables', 'occupancy': east_seated,
            },
        },
        'clear_floor_m2': round(clear_m2, 1),
        'design_occupancy': design,
        'main_door_w_m': main_door,
        'second_exit': True,
        'second_door_w_m': side_door,
        'egress_mm_per_person': 28,
        'egress_note': 'total clear width 28 mm/person across all exits; two exits share it',
        'plan': 'foyer + west lounge + east meeting',
        'roof': 'crossed sheds',
    }
    return m, meta


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/community-hub.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, meta = build()
    info = m.write(out, extras={
        'authority': 'proposed',
        'origin_note': 'south foyer door threshold centre',
        'gathering': meta,
        'footprint_en_m': [[-8.4, -1.4], [9.8, -1.4], [9.8, 6.4], [-8.4, 6.4]],
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
