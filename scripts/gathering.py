"""
Shared helpers for gathering buildings — NOT a parametric hall.

  Occupancy factors (stated in C7-done.md):
    standing / reception   0.5 m² / person
    assembly, no tables    0.65 m² / person
    seated at tables       1.4 m² / person

  Egress: total clear exit width 28 mm per person of design occupancy (matches a ~3.6 m
  opening for ~128 seated), shared across exits, minimum 1.8 m per opening;
  a second exit when design occupancy > 49.
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
RIVER = surface('river_stone')

# m² per person
STANDING = 0.5
ASSEMBLY = 0.65
SEATED = 1.4

MM_PER_PERSON_TOTAL = 28.0  # total clear width across all exits
MIN_DOOR_M = 1.8
SECOND_EXIT_ABOVE = 49


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


def capacity(area_m2: float, factor: float) -> int:
    return max(1, int(math.floor(area_m2 / factor)))


def door_width_m(design_occupancy: int, n_exits: int = 1) -> float:
    """Share total egress width across n_exits; never below MIN_DOOR_M per opening."""
    total = design_occupancy * MM_PER_PERSON_TOTAL / 1000.0
    each = total / max(n_exits, 1)
    return max(MIN_DOOR_M, round(each, 2))


def needs_second_exit(design_occupancy: int) -> bool:
    return design_occupancy > SECOND_EXIT_ABOVE


def wall_gap(m, mat, name_w, name_e, x0, x1, n, t, h, door_w, y0=0.0):
    """South-facing wall along north=n from x0..x1 with a centred door gap."""
    dw = door_w / 2
    cx = 0.5 * (x0 + x1)
    for label, ring in (
        (name_w, [(x0, n), (cx - dw, n), (cx - dw, n + t), (x0, n + t)]),
        (name_e, [(cx + dw, n), (x1, n), (x1, n + t), (cx + dw, n + t)]),
    ):
        xz = ring_xz(ring)
        m.extrude(mat, xz, y0, y0 + h)
        m.solid(xz, y0, y0 + h, label)


def solid_wall(m, mat, name, ring, h, y0=0.0):
    xz = ring_xz(ring)
    m.extrude(mat, xz, y0, y0 + h)
    m.solid(xz, y0, y0 + h, name)


def floor_rect(m, mat, name, x0, n0, x1, n1, y=0.0, thick=0.05):
    ring = open_ring(ring_xz([(x0, n0), (x1, n0), (x1, n1), (x0, n1)]))
    m.extrude(mat, ring, y - thick, y)
    m.floor(ring, y, name)
    return (x1 - x0) * (n1 - n0)
