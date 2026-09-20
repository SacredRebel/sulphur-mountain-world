"""
Parametric dwelling unit — shared by Retreat Village and Creek-Side Glamping.

  Designed for a hard triangle budget: eight units must stay under 20,000 tris total
  (~2,000 per dwelling). Geometry is deliberate quads, not dense grids. Same seed →
  same unit every time.

  Local frame of a unit: door threshold at plan (0, 0), room extends +north.
  Caller places the unit with east/north/yaw/base_y in the cluster frame.
"""
from __future__ import annotations

import math
import random

from glb import surface

BOARD = surface('board_and_batten')
TIMBER = surface('timber')
STONE = surface('stone')
METAL = surface('standing_seam_metal')
GLASS = surface('glass')
CANVAS = surface('canvas')
GREEN = surface('living_roof')


def P(e, n, y=0.0):
    return (float(e), float(y), float(-n))


def ring_xz(pts):
    return [(float(e), float(-n)) for e, n in pts]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(v):
    L = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (0.0, 1.0, 0.0) if L < 1e-9 else (v[0] / L, v[1] / L, v[2] / L)


def _rot(e, n, yaw_deg):
    a = math.radians(yaw_deg)
    c, s = math.cos(a), math.sin(a)
    return (e * c - n * s, e * s + n * c)


def _xf(pts_en, origin_e, origin_n, yaw_deg):
    out = []
    for e, n in pts_en:
        re, rn = _rot(e, n, yaw_deg)
        out.append((origin_e + re, origin_n + rn))
    return out


def _world(origin_e, origin_n, yaw_deg, local_e, local_n, y):
    re, rn = _rot(local_e, local_n, yaw_deg)
    return (origin_e + re, float(y), -(origin_n + rn))


def unit_params(rng: random.Random, kind='cabin'):
    if kind == 'tipi':
        return {
            'kind': 'tipi',
            'radius': rng.uniform(2.2, 2.7),
            'height': rng.uniform(3.4, 4.0),
            'deck': True,
            'deck_depth': rng.uniform(1.6, 2.2),
            'sides': 8,
        }
    return {
        'kind': 'cabin',
        'width': rng.uniform(3.6, 4.6),
        'depth': rng.uniform(5.0, 6.5),
        'wall_h': rng.uniform(2.2, 2.55),
        'pitch': rng.uniform(0.35, 0.55),
        'door_w': rng.uniform(0.9, 1.1),
        'deck_depth': rng.uniform(1.8, 2.8),
        'deck_side': rng.choice(['south', 'east', 'west']),
        'window': rng.choice(['east', 'west', 'both']),
        'living_roof': rng.random() < 0.25,
    }


def add_cabin(m, origin_e, origin_n, yaw_deg, base_y, p, name='cabin'):
    w, d = p['width'], p['depth']
    x0, x1, n0, n1 = -w / 2, w / 2, 0.0, d
    wall_h, door_w = p['wall_h'], p['door_w']
    y0 = base_y

    def place(pts):
        return ring_xz(_xf(pts, origin_e, origin_n, yaw_deg))

    def W(le, ln, y):
        return _world(origin_e, origin_n, yaw_deg, le, ln, y)

    pad = [(x0 - 0.15, n0 - 0.15), (x1 + 0.15, n0 - 0.15), (x1 + 0.15, n1 + 0.15), (x0 - 0.15, n1 + 0.15)]
    m.extrude(STONE, place(pad), y0 - 0.12, y0)
    m.floor(place([(x0, n0), (x1, n0), (x1, n1), (x0, n1)]), y0, f'{name} floor')

    t = 0.12
    for label, ring in (
        (f'{name} door W', [(x0, n0), (-door_w / 2, n0), (-door_w / 2, n0 + t), (x0, n0 + t)]),
        (f'{name} door E', [(door_w / 2, n0), (x1, n0), (x1, n0 + t), (door_w / 2, n0 + t)]),
        (f'{name} east', [(x1 - t, n0), (x1, n0), (x1, n1), (x1 - t, n1)]),
        (f'{name} west', [(x0, n0), (x0 + t, n0), (x0 + t, n1), (x0, n1)]),
        (f'{name} north', [(x0, n1 - t), (x1, n1 - t), (x1, n1), (x0, n1)]),
    ):
        xz = place(ring)
        m.extrude(BOARD, xz, y0, y0 + wall_h)
        m.solid(xz, y0, y0 + wall_h, label)

    win = p['window']
    if win in ('east', 'both'):
        m.grid(GLASS, [[W(x1, 1.3, y0 + 0.85), W(x1, 2.7, y0 + 0.85)],
                       [W(x1, 1.3, y0 + 1.85), W(x1, 2.7, y0 + 1.85)]], up=True)
    if win in ('west', 'both'):
        m.grid(GLASS, [[W(x0, 1.3, y0 + 0.85), W(x0, 2.7, y0 + 0.85)],
                       [W(x0, 1.3, y0 + 1.85), W(x0, 2.7, y0 + 1.85)]], up=True)

    rise = p['pitch'] * (w / 2)
    roof_mat = GREEN if p['living_roof'] else METAL
    m.quad(roof_mat,
           W(x0 - 0.15, n0 - 0.15, y0 + wall_h), W(x0 - 0.15, n1 + 0.15, y0 + wall_h),
           W(0.0, n1 + 0.15, y0 + wall_h + rise), W(0.0, n0 - 0.15, y0 + wall_h + rise))
    m.quad(roof_mat,
           W(0.0, n0 - 0.15, y0 + wall_h + rise), W(0.0, n1 + 0.15, y0 + wall_h + rise),
           W(x1 + 0.15, n1 + 0.15, y0 + wall_h), W(x1 + 0.15, n0 - 0.15, y0 + wall_h))

    dd = p['deck_depth']
    side = p['deck_side']
    if side == 'south':
        deck = [(x0, n0 - dd), (x1, n0 - dd), (x1, n0), (x0, n0)]
    elif side == 'east':
        deck = [(x1, n0), (x1 + dd, n0), (x1 + dd, n1 * 0.55), (x1, n1 * 0.55)]
    else:
        deck = [(x0 - dd, n0), (x0, n0), (x0, n1 * 0.55), (x0 - dd, n1 * 0.55)]
    m.extrude(TIMBER, place(deck), y0 - 0.05, y0 + 0.05)
    m.floor(place(deck), y0 + 0.05, f'{name} deck')

    xs = [p[0] for p in pad + deck]
    ns = [p[1] for p in pad + deck]
    local_built = [(min(xs), min(ns)), (max(xs), min(ns)), (max(xs), max(ns)), (min(xs), max(ns))]
    return _xf(local_built, origin_e, origin_n, yaw_deg)


def add_tipi(m, origin_e, origin_n, yaw_deg, base_y, p, name='tipi'):
    r, h, n = p['radius'], p['height'], p['sides']
    y0 = base_y
    cx, cn = 0.0, r * 0.35
    deck_r = r + p['deck_depth']

    def W(le, ln, y):
        return _world(origin_e, origin_n, yaw_deg, le, ln, y)

    angles = [2 * math.pi * i / n - math.pi / 2 for i in range(n)]
    deck_pts = [(cx + deck_r * math.cos(a), cn + deck_r * math.sin(a)) for a in angles]
    deck_en = _xf(deck_pts, origin_e, origin_n, yaw_deg)
    m.extrude(TIMBER, ring_xz(deck_en), y0 - 0.08, y0)
    m.floor(ring_xz(deck_en), y0, f'{name} deck')

    tip = W(cx, cn, y0 + h)
    door_i = 0
    for i in range(n):
        if i == door_i:
            continue
        a0, a1 = angles[i], angles[(i + 1) % n]
        b0 = W(cx + r * math.cos(a0), cn + r * math.sin(a0), y0)
        b1 = W(cx + r * math.cos(a1), cn + r * math.sin(a1), y0)
        nrm = _norm(_cross(_sub(b1, b0), _sub(tip, b0)))
        m.tris(CANVAS, [b0, b1, tip], [nrm, nrm, nrm], [0, 1, 2])

        ring = [
            (cx + (r - 0.08) * math.cos(a0), cn + (r - 0.08) * math.sin(a0)),
            (cx + r * math.cos(a0), cn + r * math.sin(a0)),
            (cx + r * math.cos(a1), cn + r * math.sin(a1)),
            (cx + (r - 0.08) * math.cos(a1), cn + (r - 0.08) * math.sin(a1)),
        ]
        xz = ring_xz(_xf(ring, origin_e, origin_n, yaw_deg))
        m.solid(xz, y0, y0 + h * 0.85, f'{name} wall {i}')

    floor_pts = [(cx + (r - 0.25) * math.cos(a), cn + (r - 0.25) * math.sin(a)) for a in angles]
    m.floor(ring_xz(_xf(floor_pts, origin_e, origin_n, yaw_deg)), y0, f'{name} floor')
    return deck_en


def footprint_aabb(built_en_rings):
    xs, ns = [], []
    for ring in built_en_rings:
        for e, n in ring:
            xs.append(e)
            ns.append(n)
    if not xs:
        return []
    return [(min(xs), min(ns)), (max(xs), min(ns)), (max(xs), max(ns)), (min(xs), max(ns))]
