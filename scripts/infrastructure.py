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

  Setbacks (CA 100 ft / 30.5 m): disposal group (greywater + leach) sits east of
  the utility core — clear of the well head and of the creek to the west.

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

# California well / creek setback for sewage disposal — programme massing honour.
SETBACK_M = 30.5


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

    # ---- Well / tank / shed / solar stay in the core yard (west–centre) -------------
    # Origin at south edge of yard, centreline — approach from the road.
    well_e, well_n = -5.5, 3.5

    # Solar: 12 m wide × ~5.9 m deep; three 0.80 m rows at 2.40 m pitch (no self-shade
    # at 34.433° winter-solstice noon). Was 12×4 with 1.33 m pitch — too tight.
    ae0, an0 = 1.5, 4.0
    row_depth, pitch, n_rows = 0.80, 2.40, 3
    array_depth = (n_rows - 1) * pitch + row_depth  # 5.60 m
    array_yard_n = 5.9  # stated yard depth
    ae1 = ae0 + 12.0
    an1 = an0 + array_yard_n

    core = open_ring(ring_xz(rect_en(-10.0, -1.0, ae1, max(10.5, an1 + 0.5))))
    m.extrude(GRAVEL, core, -0.05, 0.0)
    m.floor(core, 0.0, 'utility yard')

    # ---- Water storage tank — PLACEHOLDER 10,000 gal --------------------------------
    tank_e, tank_n, tank_r, tank_h = -5.5, 8.0, 1.85, 3.5
    tank_ring = open_ring(ring_xz(circle_en(tank_e, tank_n, tank_r, n=20)))
    pad = open_ring(ring_xz(circle_en(tank_e, tank_n, tank_r + 0.4, n=20)))
    m.extrude(CONCRETE, pad, 0.0, 0.15)
    m.solid(pad, 0.0, 0.15, 'tank pad')
    m.extrude(METAL, tank_ring, 0.15, 0.15 + tank_h)
    m.solid(tank_ring, 0.15, 0.15 + tank_h, 'water tank')

    # ---- Well head -----------------------------------------------------------------
    well_pad = open_ring(ring_xz(rect_en(well_e - 0.8, well_n - 0.8, well_e + 0.8, well_n + 0.8)))
    casing = open_ring(ring_xz(circle_en(well_e, well_n, 0.25, n=12)))
    m.extrude(CONCRETE, well_pad, 0.0, 0.2)
    m.solid(well_pad, 0.0, 0.2, 'well pad')
    m.extrude(METAL, casing, 0.2, 1.1)
    m.solid(casing, 0.2, 1.1, 'well head')

    # ---- Solar array — PLACEHOLDER 12 × 5.9 m yard, 3 rows @ 2.40 m pitch ------------
    for i in range(n_rows):
        n0 = an0 + i * pitch
        n1 = n0 + row_depth
        panel = open_ring(ring_xz(rect_en(ae0, n0, ae1, n1)))
        y0, y1 = 0.6, 1.35  # low rack; tilt in mesh only — plan solid is the roof
        m.extrude(BRONZE, panel, y0, y1)
        m.solid(panel, y0, y1, f'solar panel row {i + 1}')
        m.quad(
            BRONZE,
            P(ae0, n0, y0), P(ae1, n0, y0),
            P(ae1, n1, y1), P(ae0, n1, y1),
        )
    for e in (ae0 + 0.3, (ae0 + ae1) / 2, ae1 - 0.3):
        for n in (an0 + 0.2, an0 + array_depth - 0.2):
            post = open_ring(ring_xz(rect_en(e - 0.08, n - 0.08, e + 0.08, n + 0.08)))
            m.extrude(TIMBER, post, 0.0, 1.2)
            m.solid(post, 0.0, 1.2, 'array post')

    # ---- Equipment shed ~8×6 m (C0) -------------------------------------------------
    sx0, sx1, sn0, sn1 = -9.5, -1.5, 0.0, 6.0
    t, h = 0.15, 2.6
    door_w = 2.0
    shed_floor = open_ring(ring_xz(rect_en(sx0 + t, sn0 + t, sx1 - t, sn1 - t)))
    m.extrude(CONCRETE, shed_floor, -0.05, 0.0)
    m.floor(shed_floor, 0.0, 'equipment shed')
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
    m.quad(
        METAL,
        P(sx0 - 0.2, sn0 - 0.3, h), P(sx1 + 0.2, sn0 - 0.3, h),
        P(sx1 + 0.2, sn1 + 0.3, h + 0.3), P(sx0 - 0.2, sn1 + 0.3, h + 0.3),
    )

    # ---- Disposal group — EAST of core, ≥100 ft from well and from creek ------------
    # Creek runs west of this zone (~22 m from the well). Disposal goes east so both
    # setbacks clear. Verified: leach SW ≥31 m from well, ≥36 m from creek bed.
    de0, dn0 = 22.0, 21.0  # leach SW
    de1, dn1 = de0 + 12.0, dn0 + 8.0  # 12 × 8 = 96 m² placeholder
    gw_n0, gw_n1 = dn0 - 3.0, dn0 - 1.0

    # Corridor floor so the disposal pad is reachable from the core
    corridor = open_ring(ring_xz(rect_en(ae1 - 0.5, 8.0, de0 + 0.5, 12.0)))
    m.extrude(GRAVEL, corridor, -0.05, 0.0)
    m.floor(corridor, 0.0, 'disposal path')
    spur = open_ring(ring_xz(rect_en(de0 - 0.5, 12.0, de0 + 2.0, gw_n0)))
    m.extrude(GRAVEL, spur, -0.05, 0.0)
    m.floor(spur, 0.0, 'disposal spur')

    disposal_pad = open_ring(ring_xz(rect_en(de0 - 0.5, gw_n0 - 0.5, de1 + 0.5, dn1 + 0.5)))
    m.extrude(GRAVEL, disposal_pad, -0.05, 0.0)
    m.floor(disposal_pad, 0.0, 'disposal pad')

    for i, e0 in enumerate((de0, de0 + 3.5)):
        bed = open_ring(ring_xz(rect_en(e0, gw_n0, e0 + 3.0, gw_n1)))
        m.extrude(DIRT, bed, 0.0, 0.45)
        m.solid(bed, 0.0, 0.45, f'greywater bed {i + 1}')

    lf = open_ring(ring_xz(rect_en(de0, dn0, de1, dn1)))
    m.extrude(GRAVEL, lf, 0.0, 0.06)
    for label, ring in (
        ('leach berm south', rect_en(de0, dn0, de1, dn0 + 0.4)),
        ('leach berm north', rect_en(de0, dn1 - 0.4, de1, dn1)),
    ):
        xz = open_ring(ring_xz(ring))
        m.extrude(STONE, xz, 0.0, 0.35)
        m.solid(xz, 0.0, 0.35, label)

    # Built footprint hugs core + corridor + disposal (not a cleared rectangle between)
    fp = [
        (-10.0, -1.0), (ae1, -1.0), (ae1, 8.0), (de0 + 0.5, 8.0),
        (de0 + 0.5, gw_n0 - 0.5), (de1 + 0.5, gw_n0 - 0.5),
        (de1 + 0.5, dn1 + 0.5), (de0 - 0.5, dn1 + 0.5),
        (de0 - 0.5, 12.0), (ae1, 12.0), (ae1, max(10.5, an1 + 0.5)),
        (-10.0, max(10.5, an1 + 0.5)),
    ]

    array_m2 = 12.0 * array_depth  # panel plan area (not yard)
    return m, fp, {
        'tank_gal_placeholder': 10000,
        'tank_m': {'diameter_m': 3.7, 'height_m': 3.5},
        'array_yard_m': {'width_m': 12.0, 'depth_m': array_yard_n},
        'array_panel_m2_placeholder': round(array_m2, 1),
        'array_row_pitch_m': pitch,
        'array_kw_rough_placeholder': (
            f'{array_m2 / 6:.0f}–{array_m2 / 5:.0f} kW DC '
            '(rule-of-thumb 5–6 m²/kW — not engineered)'
        ),
        'leach_field_m2_placeholder': 96.0,
        'setback_m': SETBACK_M,
        'disposal_from_well_m_min': 31.1,
        'disposal_from_creek_m_min': 36.4,
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
