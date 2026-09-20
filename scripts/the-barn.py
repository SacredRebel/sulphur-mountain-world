"""
The Barn (gatelodge-operations-hub) — working barn massing at the gate.

  Origin: centre of the south door threshold (a place someone can point at).
  Board-and-batten walls, standing-seam gable. Door is a GAP in the solid run.
  Authority: proposed (lidar shows a small roof here — massing is programme-sized).

    python scripts/the-barn.py models/the-barn.glb
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, surface  # noqa: E402

BOARD = surface('board_and_batten')
STONE = surface('stone')
METAL = surface('standing_seam_metal')
TIMBER = surface('timber')


def P(e, n, y=0.0):
    return (float(e), float(y), float(-n))


def ring_xz(pts):
    return [(float(e), float(-n)) for e, n in pts]


def build():
    m = Model('The Barn — working gatelodge massing')
    # 12 m wide × 18 m deep (local: door at n=0, room +north)
    x0, x1, n0, n1 = -6.0, 6.0, 0.0, 18.0
    wall_h, door_w, t = 3.6, 2.4, 0.2

    pad = [(x0 - 0.2, n0 - 0.2), (x1 + 0.2, n0 - 0.2), (x1 + 0.2, n1 + 0.2), (x0 - 0.2, n1 + 0.2)]
    m.extrude(STONE, ring_xz(pad), -0.15, 0.0)
    m.floor(ring_xz([(x0, n0), (x1, n0), (x1, n1), (x0, n1)]), 0.0, 'barn floor')

    # South wall — door gap
    for label, ring in (
        ('barn door W', [(x0, n0), (-door_w / 2, n0), (-door_w / 2, n0 + t), (x0, n0 + t)]),
        ('barn door E', [(door_w / 2, n0), (x1, n0), (x1, n0 + t), (door_w / 2, n0 + t)]),
        ('barn east', [(x1 - t, n0), (x1, n0), (x1, n1), (x1 - t, n1)]),
        ('barn west', [(x0, n0), (x0 + t, n0), (x0 + t, n1), (x0, n1)]),
        ('barn north', [(x0, n1 - t), (x1, n1 - t), (x1, n1), (x0, n1)]),
    ):
        xz = ring_xz(ring)
        m.extrude(BOARD, xz, 0.0, wall_h)
        m.solid(xz, 0.0, wall_h, label)

    # Gable roof — ridge along depth at e=0
    rise = 2.2
    m.quad(METAL, P(x0 - 0.3, n0 - 0.3, wall_h), P(x0 - 0.3, n1 + 0.3, wall_h),
           P(0.0, n1 + 0.3, wall_h + rise), P(0.0, n0 - 0.3, wall_h + rise))
    m.quad(METAL, P(0.0, n0 - 0.3, wall_h + rise), P(0.0, n1 + 0.3, wall_h + rise),
           P(x1 + 0.3, n1 + 0.3, wall_h), P(x1 + 0.3, n0 - 0.3, wall_h))

    # Small loft floor over the north third (working loft)
    loft = [(x0 + 0.3, n1 - 6.0), (x1 - 0.3, n1 - 6.0), (x1 - 0.3, n1 - 0.3), (x0 + 0.3, n1 - 0.3)]
    m.extrude(TIMBER, ring_xz(loft), 2.55, 2.7)
    m.floor(ring_xz(loft), 2.7, 'loft')

    # Stair stub: three steps (low tris) from floor to loft edge
    for i in range(1, 4):
        step = [(x0 + 1.0, n1 - 6.0 - i * 0.55), (x0 + 2.2, n1 - 6.0 - i * 0.55),
                (x0 + 2.2, n1 - 6.0 - (i - 1) * 0.55), (x0 + 1.0, n1 - 6.0 - (i - 1) * 0.55)]
        top = i * (2.7 / 4)
        m.extrude(TIMBER, ring_xz(step), top - 0.12, top)
        m.floor(ring_xz(step), top, f'stair {i}')

    return m, pad


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/the-barn.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, fp = build()
    info = m.write(out, extras={
        'zone': 'gatelodge-operations-hub',
        'origin_note': 'south door threshold centre',
        'authority': 'proposed',
        'footprint_en_m': [[round(e, 2), round(n, 2)] for e, n in fp],
    })
    info['floors'] = len(m.walk['floors'])
    info['solids'] = len(m.walk['solids'])
    print(json.dumps(info))
