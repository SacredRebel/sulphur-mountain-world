"""
Gathering hall — shared massing for rooms meant for ~30 people, not cabins scaled up.

  Clear floor ~1.5–2 m² per standing person. Crowd door = wide GAP in the south solid run.
  Origin: centre of the south door threshold.

  Used by community-hub, events-gatherings-hub, wellness-facilities.
"""
from __future__ import annotations

import math

from glb import Model, surface

BOARD = surface('board_and_batten')
TIMBER = surface('timber')
STONE = surface('stone')
METAL = surface('standing_seam_metal')
GLASS = surface('glass')
STUCCO = surface('stucco')


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


def build_hall(
    title: str,
    *,
    width_m: float,
    depth_m: float,
    wall_h: float = 3.6,
    door_w: float = 3.0,
    capacity: int = 30,
    seated: bool = False,
    cladding=None,
    porch_m: float = 0.0,
    ridge_rise: float = 1.8,
):
    """
    Rectangular hall. Clear floor = width × depth (interior), walls outside that.
    Door gap on south face, centred on origin. Floor ring meets walls (no 10 cm shortfall).
    """
    cladding = cladding or BOARD
    # Interior clear: from wall inside faces
    t = 0.25  # wall thickness
    x0, x1 = -width_m / 2, width_m / 2
    n0, n1 = 0.0, depth_m
    clear_m2 = width_m * depth_m
    # standing capacity at 2 m²/person; seated note if requested
    standing_cap = int(clear_m2 / 2.0)
    seated_cap = int(clear_m2 / 3.5) if seated else None

    m = Model(title)

    # Pad slightly larger than footprint
    pad = [(x0 - 0.4, n0 - 0.4 - porch_m), (x1 + 0.4, n0 - 0.4 - porch_m),
           (x1 + 0.4, n1 + 0.4), (x0 - 0.4, n1 + 0.4)]
    m.extrude(STONE, ring_xz(pad), -0.15, 0.0)

    # Main floor — exact clear rectangle, flush to inside of walls
    floor = open_ring(ring_xz([(x0, n0), (x1, n0), (x1, n1), (x0, n1)]))
    m.extrude(STONE, floor, -0.05, 0.0)
    m.floor(floor, 0.0, 'hall floor')

    if porch_m > 0.1:
        porch = open_ring(ring_xz([(x0, n0 - porch_m), (x1, n0 - porch_m), (x1, n0), (x0, n0)]))
        m.extrude(TIMBER, porch, -0.05, 0.0)
        m.floor(porch, 0.0, 'porch')

    # South wall — crowd door gap (door_w), solids flush to floor ring
    dw = door_w / 2
    south_parts = [
        ('door W', [(x0, n0), (-dw, n0), (-dw, n0 + t), (x0, n0 + t)]),
        ('door E', [(dw, n0), (x1, n0), (x1, n0 + t), (dw, n0 + t)]),
    ]
    for label, ring in south_parts:
        xz = ring_xz(ring)
        m.extrude(cladding, xz, 0.0, wall_h)
        m.solid(xz, 0.0, wall_h, label)

    # East, west, north — continuous, flush to floor extents
    for label, ring in (
        ('east wall', [(x1 - t, n0), (x1, n0), (x1, n1), (x1 - t, n1)]),
        ('west wall', [(x0, n0), (x0 + t, n0), (x0 + t, n1), (x0, n1)]),
        ('north wall', [(x0, n1 - t), (x1, n1 - t), (x1, n1), (x0, n1)]),
    ):
        xz = ring_xz(ring)
        m.extrude(cladding, xz, 0.0, wall_h)
        m.solid(xz, 0.0, wall_h, label)

    # Glass bays on long sides (not solids — walls already solid behind)
    bay = min(2.5, depth_m * 0.25)
    for n_a in (depth_m * 0.25, depth_m * 0.55):
        n_b = n_a + bay
        if n_b > depth_m - 0.5:
            continue
        m.grid(GLASS, [
            [P(x1, n_a, 0.9), P(x1, n_b, 0.9)],
            [P(x1, n_a, wall_h - 0.4), P(x1, n_b, wall_h - 0.4)],
        ], up=True)
        m.grid(GLASS, [
            [P(x0, n_b, 0.9), P(x0, n_a, 0.9)],
            [P(x0, n_b, wall_h - 0.4), P(x0, n_a, wall_h - 0.4)],
        ], up=True)

    # Gable roof — ridge along depth at e=0
    m.quad(METAL, P(x0 - 0.3, n0 - 0.3 - porch_m, wall_h), P(x0 - 0.3, n1 + 0.3, wall_h),
           P(0.0, n1 + 0.3, wall_h + ridge_rise), P(0.0, n0 - 0.3 - porch_m, wall_h + ridge_rise))
    m.quad(METAL, P(0.0, n0 - 0.3 - porch_m, wall_h + ridge_rise), P(0.0, n1 + 0.3, wall_h + ridge_rise),
           P(x1 + 0.3, n1 + 0.3, wall_h), P(x1 + 0.3, n0 - 0.3 - porch_m, wall_h))

    # Threshold strip outside the door (standable approach)
    thresh = open_ring(ring_xz([(-dw - 0.2, n0 - 1.2), (dw + 0.2, n0 - 1.2),
                                (dw + 0.2, n0), (-dw - 0.2, n0)]))
    m.extrude(STONE, thresh, -0.05, 0.0)
    m.floor(thresh, 0.0, 'threshold')

    meta = {
        'capacity_standing': min(capacity, standing_cap),
        'capacity_seated': seated_cap,
        'clear_floor_m2': round(clear_m2, 1),
        'door_w_m': door_w,
        'width_m': width_m,
        'depth_m': depth_m,
        'm2_per_standing': round(clear_m2 / max(min(capacity, standing_cap), 1), 2),
    }
    return m, meta
