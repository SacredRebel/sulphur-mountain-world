"""
Infrastructure & Utilities — programme-sized massing, not engineering.

  Zone: water system, electric reactivation with solar, utility foundation.
  C0 sketch: tank pads, solar rack, shed ~8×6 m — working kit, not monumental.

  Walk contract for things that are not buildings:
    · solar panels  — solids; no floor beneath them (a roof you cannot walk on)
    · water tank    — solid cylinder; no interior floor (you cannot enter)
    · well head     — solid
    · yard ground between them — walkable floors
    · equipment shed — the one enterable room (tools), open south bay

  Sizes are PLACEHOLDER programme massing — see C11-done.md.

    python scripts/infrastructure.py models/infrastructure.glb
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, surface  # noqa: E402

CONCRETE = surface('concrete')
STONE = surface('stone')
GRAVEL = surface('gravel')
METAL = surface('standing_seam_metal')
BRONZE = surface('bronze')
BOARD = surface('board_and_batten')
TIMBER = surface('timber')
DIRT = surface('dirt')


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


def circle_en(ce, cn, r, n=20):
    return [
        (ce + r * math.cos(2 * math.pi * i / n), cn + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def rect_en(e0, n0, e1, n1):
    return [(e0, n0), (e1, n0), (e1, n1), (e0, n1)]


def build():
    m = Model('Infrastructure — utility yard massing')

    # ---- Yard apron (walkable ground between plant) ---------------------------------
    # Origin at south edge of yard, centreline — approach from the road.
    # One ground floor for the whole yard; solids (tank, panels, berms) block what they must.
    yard = open_ring(ring_xz(rect_en(-10.0, -1.0, 13.5, 23.5)))
    m.extrude(GRAVEL, yard, -0.05, 0.0)
    m.floor(yard, 0.0, 'utility yard')

    # ---- Water storage tank — PLACEHOLDER 10,000 gal --------------------------------
    # 10,000 gal ≈ 37.85 m³ → Ø 3.7 m × 3.5 m tall. Cylinder solid; no floor inside.
    tank_e, tank_n, tank_r, tank_h = -5.5, 8.0, 1.85, 3.5
    tank_ring = open_ring(ring_xz(circle_en(tank_e, tank_n, tank_r, n=20)))
    pad = open_ring(ring_xz(circle_en(tank_e, tank_n, tank_r + 0.4, n=20)))
    m.extrude(CONCRETE, pad, 0.0, 0.15)
    m.solid(pad, 0.0, 0.15, 'tank pad')
    m.extrude(METAL, tank_ring, 0.15, 0.15 + tank_h)
    m.solid(tank_ring, 0.15, 0.15 + tank_h, 'water tank')
    # No floor inside the tank.

    # ---- Well head — small casing on a pad ------------------------------------------
    well_e, well_n = -5.5, 3.5
    well_pad = open_ring(ring_xz(rect_en(well_e - 0.8, well_n - 0.8, well_e + 0.8, well_n + 0.8)))
    casing = open_ring(ring_xz(circle_en(well_e, well_n, 0.25, n=12)))
    m.extrude(CONCRETE, well_pad, 0.0, 0.2)
    m.solid(well_pad, 0.0, 0.2, 'well pad')
    m.extrude(METAL, casing, 0.2, 1.1)
    m.solid(casing, 0.2, 1.1, 'well head')

    # ---- Solar array — PLACEHOLDER 12×4 m = 48 m² (~8–10 kW rough) -----------------
    # Panels are solids (a roof you cannot walk on). No floor under the rack.
    ae0, an0, ae1, an1 = 1.5, 4.0, 13.5, 8.0  # 12 × 4 m plan
    # Three panel rows as plan solids; mesh shows a light tilt
    row_d = (an1 - an0) / 3.0
    for i in range(3):
        n0 = an0 + i * row_d + 0.1
        n1 = an0 + (i + 1) * row_d - 0.1
        panel = open_ring(ring_xz(rect_en(ae0, n0, ae1, n1)))
        y0, y1 = 0.6 + i * 0.15, 1.4 + i * 0.15  # low rack, slight step
        m.extrude(BRONZE, panel, y0, y1)
        m.solid(panel, y0, y1, f'solar panel row {i + 1}')
        # Visual tilt — leading edge lower toward south (negative n in world = +z)
        m.quad(
            BRONZE,
            P(ae0, n0, y0), P(ae1, n0, y0),
            P(ae1, n1, y1), P(ae0, n1, y1),
        )
    # Rack posts (solids) — still no floor under array
    for e in (ae0 + 0.3, (ae0 + ae1) / 2, ae1 - 0.3):
        for n in (an0 + 0.3, an1 - 0.3):
            post = open_ring(ring_xz(rect_en(e - 0.08, n - 0.08, e + 0.08, n + 0.08)))
            m.extrude(TIMBER, post, 0.0, 1.2)
            m.solid(post, 0.0, 1.2, 'array post')

    # ---- Greywater planter beds (massing) -------------------------------------------
    for i, e0 in enumerate((-9.0, -5.5)):
        bed = open_ring(ring_xz(rect_en(e0, 12.5, e0 + 3.0, 14.5)))
        m.extrude(DIRT, bed, 0.0, 0.45)
        m.solid(bed, 0.0, 0.45, f'greywater bed {i + 1}')

    # ---- Septic / leach field — PLACEHOLDER 8×12 m = 96 m² --------------------------
    # Gravel wash on the yard floor; low berm marks the programme pad. Not engineered.
    lf = open_ring(ring_xz(rect_en(-3.0, 15.5, 9.0, 23.5)))
    m.extrude(GRAVEL, lf, 0.0, 0.06)
    for label, ring in (
        ('leach berm south', rect_en(-3.0, 15.5, 9.0, 15.9)),
        ('leach berm north', rect_en(-3.0, 23.1, 9.0, 23.5)),
    ):
        xz = open_ring(ring_xz(ring))
        m.extrude(STONE, xz, 0.0, 0.35)
        m.solid(xz, 0.0, 0.35, label)

    # ---- Equipment shed ~8×6 m (C0) — the one enterable room ------------------------
    sx0, sx1, sn0, sn1 = -9.5, -1.5, 0.0, 6.0
    t, h = 0.15, 2.6
    door_w = 2.0
    shed_floor = open_ring(ring_xz(rect_en(sx0 + t, sn0 + t, sx1 - t, sn1 - t)))
    m.extrude(CONCRETE, shed_floor, -0.05, 0.0)
    m.floor(shed_floor, 0.0, 'equipment shed')

    # Walls with open south bay (door gap in south wall)
    walls = (
        ('shed west', rect_en(sx0, sn0, sx0 + t, sn1)),
        ('shed east', rect_en(sx1 - t, sn0, sx1, sn1)),
        ('shed north', rect_en(sx0, sn1 - t, sx1, sn1)),
        ('shed south west', rect_en(sx0, sn0, (sx0 + sx1) / 2 - door_w / 2, sn0 + t)),
        ('shed south east', rect_en((sx0 + sx1) / 2 + door_w / 2, sn0, sx1, sn0 + t)),
    )
    for name, r in walls:
        xz = open_ring(ring_xz(r))
        m.extrude(BOARD, xz, 0.0, h)
        m.solid(xz, 0.0, h, name)

    # Roof
    m.quad(
        METAL,
        P(sx0 - 0.2, sn0 - 0.3, h), P(sx1 + 0.2, sn0 - 0.3, h),
        P(sx1 + 0.2, sn1 + 0.3, h + 0.3), P(sx0 - 0.2, sn1 + 0.3, h + 0.3),
    )

    # Built footprint = yard built ground only (suppresses vegetation under plant)
    fp = [(-10.0, -1.0), (13.5, -1.0), (13.5, 23.5), (-10.0, 23.5)]
    return m, fp, {
        'tank_gal_placeholder': 10000,
        'tank_m': {'diameter_m': 3.7, 'height_m': 3.5},
        'array_m2_placeholder': 48.0,
        'array_kw_rough_placeholder': '8–10 kW DC (rule-of-thumb 5–6 m²/kW — not engineered)',
        'leach_field_m2_placeholder': 96.0,
        'massing_not_engineering': True,
    }


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/infrastructure.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, fp, sizing = build()
    info = m.write(out, extras={
        'zone': 'infrastructure',
        'work': 'store water, draw from the well, make power, and treat waste at programme scale',
        'massing_not_engineering': True,
        'sizing_placeholder': sizing,
        'origin_note': 'south edge of utility yard, centreline',
        'authority': 'proposed',
        'footprint_en_m': [[round(e, 2), round(n, 2)] for e, n in fp],
    })
    print(json.dumps({
        'bytes': info['bytes'], 'triangles': info['triangles'],
        'floors': len(m.walk['floors']), 'solids': len(m.walk['solids']),
        'sizing': sizing,
    }))
