"""
Ceremonial Infrastructure — stone/earth kiva with sacred fire circle.

  Zone: natural stone and earthen kiva with sacred fire circle, in front of
  McQueen's Garage, for live events, ceremonies, and retreat programming.
  C0 sketch: stone/earth circle ~12–14 m Ø; fire ring centre; minimal built ground.

  This is outdoor ceremonial ground — a floor you stand on, not a room you enter.
  Low ring wall at 0.45 m (steppable — clear of the engine's 0.55 m step-up limit).
  Owner decision 2026-09-21: **open-air**. Complete as built — no enclosure.

  Programme massing, not engineered construction.

    python scripts/ceremonial.py models/ceremonial-infrastructure.glb
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, surface  # noqa: E402

STONE = surface('stone')
DARK = surface('dark_stone')
DIRT = surface('dirt')
RIVER = surface('river_stone')


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


def circle_en(ce, cn, r, n=28):
    return [
        (ce + r * math.cos(2 * math.pi * i / n), cn + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def build():
    m = Model('Ceremonial — kiva and fire circle')
    # 13 m diameter kiva (mid of C0 12–14 m). Origin at fire ring centre.
    R = 6.5
    wall_t, wall_h = 0.45, 0.45  # steppable — not the engine's 0.55 m knife edge
    fire_r, fire_h = 1.1, 0.4

    # Earthen kiva floor — walkable, outdoor, not an enterable interior
    floor = open_ring(ring_xz(circle_en(0.0, 0.0, R - wall_t, n=28)))
    m.extrude(DIRT, floor, -0.08, 0.0)
    m.cap(STONE, ring_xz(circle_en(0.0, 0.0, R - wall_t, n=28)), 0.0, up=True)
    m.floor(floor, 0.0, 'kiva floor')

    # Low stone/earth ring wall — gap on the south for entry (not a door into a room)
    gap = 2.2  # metres of arc chord approx via angle
    gap_ang = gap / R
    n_seg = 28
    # Build wall as arc segments excluding south gap (±gap_ang/2 around -π/2 = south in EN? 
    # In EN: n south is negative. South entry at angle -π/2 if cos/sin standard (e east, n north):
    # angle 0 = east, π/2 = north, π = west, -π/2 = south.
    a0 = -math.pi / 2 - gap_ang / 2
    a1 = -math.pi / 2 + gap_ang / 2
    # Wall outer/inner as many short solid segments
    for i in range(n_seg):
        t0 = 2 * math.pi * i / n_seg
        t1 = 2 * math.pi * (i + 1) / n_seg
        mid = 0.5 * (t0 + t1)
        # skip if mid is inside the south gap (normalize to [-π, π])
        def in_gap(a):
            # gap spans a0..a1 crossing possibly
            aa = (a + math.pi) % (2 * math.pi) - math.pi
            lo, hi = a0, a1
            return lo <= aa <= hi
        if in_gap(mid):
            continue
        outer = [
            (R * math.cos(t0), R * math.sin(t0)),
            (R * math.cos(t1), R * math.sin(t1)),
            ((R - wall_t) * math.cos(t1), (R - wall_t) * math.sin(t1)),
            ((R - wall_t) * math.cos(t0), (R - wall_t) * math.sin(t0)),
        ]
        xz = open_ring(ring_xz(outer))
        m.extrude(RIVER, xz, 0.0, wall_h)
        m.solid(xz, 0.0, wall_h, f'kiva wall {i}')

    # Sacred fire ring — solid hearth at centre
    fire = open_ring(ring_xz(circle_en(0.0, 0.0, fire_r, n=16)))
    m.extrude(DARK, fire, 0.0, fire_h)
    m.solid(fire, 0.0, fire_h, 'sacred fire')

    # Built footprint = kiva circle only (minimal)
    fp = [(-R, -R), (R, -R), (R, R), (-R, R)]
    return m, fp


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/ceremonial-infrastructure.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, fp = build()
    info = m.write(out, extras={
        'zone': 'ceremonial-infrastructure',
        'work': 'gather around a sacred fire in a stone and earthen kiva',
        'enterable_interior': False,
        'open_air': True,
        'massing_not_engineering': True,
        'origin_note': 'centre of the sacred fire ring',
        'authority': 'proposed',
        'footprint_en_m': [[round(e, 2), round(n, 2)] for e, n in fp],
        'kiva_diameter_m': 13.0,
    })
    print(json.dumps({
        'bytes': info['bytes'], 'triangles': info['triangles'],
        'floors': len(m.walk['floors']), 'solids': len(m.walk['solids']),
        'enterable_interior': False,
    }))
