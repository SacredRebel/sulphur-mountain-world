"""
Example box — the worked generator every later massing starts from.

  A 4×6 m timber shed on a stone pad. Origin is the centre of the door threshold on the
  south wall (a place someone can point at), not the centroid. One door: a GAP in the
  solid run on the south face. Materials come only from materials.json via glb.surface.

  Frame: plan (east, north) → model (x east, y up, z south) through P / ring_xz.

    python scripts/example-box.py models/example-box.glb
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, rect, surface  # noqa: E402

TIMBER = surface('board_and_batten')
STONE = surface('stone')
METAL = surface('standing_seam_metal')
GLASS = surface('glass')


def P(e, n, y=0.0):
    """plan (east, north) → model (x east, y up, z south)"""
    return (float(e), float(y), float(-n))


def ring_xz(pts):
    return [(float(e), float(-n)) for e, n in pts]


def build():
    m = Model('Example box — toolkit template')
    # Footprint in plan metres relative to the door threshold at (0, 0):
    # room runs 2 m west / 2 m east, and 6 m north into the shed.
    x0, x1, n0, n1 = -2.0, 2.0, 0.0, 6.0
    floor = ring_xz([(x0, n0), (x1, n0), (x1, n1), (x0, n1)])
    m.extrude(STONE, floor, -0.15, 0.0)
    m.floor(floor, 0.0, 'pad')

    wall_h = 2.4
    # South wall: two solids with a 1.0 m door gap centred on the origin.
    # A door is a GAP — never a flag.
    door_w = 1.0
    m.extrude(TIMBER, ring_xz([(x0, n0), (-door_w / 2, n0), (-door_w / 2, n0 + 0.15), (x0, n0 + 0.15)]), 0.0, wall_h)
    m.solid(ring_xz([(x0, n0), (-door_w / 2, n0), (-door_w / 2, n0 + 0.15), (x0, n0 + 0.15)]), 0.0, wall_h, 'south wall W')
    m.extrude(TIMBER, ring_xz([(door_w / 2, n0), (x1, n0), (x1, n0 + 0.15), (door_w / 2, n0 + 0.15)]), 0.0, wall_h)
    m.solid(ring_xz([(door_w / 2, n0), (x1, n0), (x1, n0 + 0.15), (door_w / 2, n0 + 0.15)]), 0.0, wall_h, 'south wall E')

    # East, west, north walls as continuous solids.
    for name, ring in (
        ('east wall', [(x1 - 0.15, n0), (x1, n0), (x1, n1), (x1 - 0.15, n1)]),
        ('west wall', [(x0, n0), (x0 + 0.15, n0), (x0 + 0.15, n1), (x0, n1)]),
        ('north wall', [(x0, n1 - 0.15), (x1, n1 - 0.15), (x1, n1), (x0, n1)]),
    ):
        xz = ring_xz(ring)
        m.extrude(TIMBER, xz, 0.0, wall_h)
        m.solid(xz, 0.0, wall_h, name)

    # One window bay on the east wall (glass panel; solid already runs behind as thin timber).
    m.grid(GLASS, [
        [P(x1, 1.5, 0.9), P(x1, 3.5, 0.9)],
        [P(x1, 1.5, 2.0), P(x1, 3.5, 2.0)],
    ], up=True)

    # Simple shed roof: ridge along east–west at the north half.
    roof = ring_xz([(x0 - 0.2, n0 - 0.2), (x1 + 0.2, n0 - 0.2), (x1 + 0.2, n1 + 0.2), (x0 - 0.2, n1 + 0.2)])
    m.extrude(METAL, roof, wall_h, wall_h + 0.12)
    return m


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/example-box.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m = build()
    info = m.write(out)
    info['floors'] = len(m.walk['floors'])
    info['solids'] = len(m.walk['solids'])
    print(json.dumps(info))
