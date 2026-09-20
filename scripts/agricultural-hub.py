"""
Agricultural Hub — open shed + potting wing.

  Origin: centre of the shed's open south bay (threshold of the working bay).
  Roofed ground only in the footprint — nursery yard stays outside so trees/planting remain.
  Authority: proposed.

    python scripts/agricultural-hub.py models/agricultural-hub.glb
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, surface  # noqa: E402

TIMBER = surface('timber')
STONE = surface('stone')
METAL = surface('standing_seam_metal')
BOARD = surface('board_and_batten')
GLASS = surface('glass')


def P(e, n, y=0.0):
    return (float(e), float(y), float(-n))


def ring_xz(pts):
    return [(float(e), float(-n)) for e, n in pts]


def build():
    m = Model('Agricultural Hub — shed and potting wing')
    # Open shed: 16 × 8 m, posts, metal roof, open south
    sx0, sx1, sn0, sn1 = -8.0, 8.0, 0.0, 8.0
    eave = 3.2

    pad = [(sx0 - 0.3, sn0 - 0.3), (sx1 + 0.3, sn0 - 0.3), (sx1 + 0.3, sn1 + 0.3), (sx0 - 0.3, sn1 + 0.3)]
    m.extrude(STONE, ring_xz(pad), -0.12, 0.0)
    m.floor(ring_xz([(sx0, sn0), (sx1, sn0), (sx1, sn1), (sx0, sn1)]), 0.0, 'shed floor')

    # Corner + mid posts (thin solids) — open bay, no south wall
    posts = [
        (sx0 + 0.15, sn0 + 0.15), (0.0, sn0 + 0.15), (sx1 - 0.15, sn0 + 0.15),
        (sx0 + 0.15, sn1 - 0.15), (0.0, sn1 - 0.15), (sx1 - 0.15, sn1 - 0.15),
    ]
    for i, (e, n) in enumerate(posts):
        ring = [(e - 0.12, n - 0.12), (e + 0.12, n - 0.12), (e + 0.12, n + 0.12), (e - 0.12, n + 0.12)]
        xz = ring_xz(ring)
        m.extrude(TIMBER, xz, 0.0, eave)
        m.solid(xz, 0.0, eave, f'post {i}')

    # North back wall (wind break) — continuous solid
    back = [(sx0, sn1 - 0.15), (sx1, sn1 - 0.15), (sx1, sn1), (sx0, sn1)]
    m.extrude(BOARD, ring_xz(back), 0.0, eave)
    m.solid(ring_xz(back), 0.0, eave, 'shed back')

    # Shed roof — single slope (south low → north high is wrong for rain; north high)
    m.quad(METAL,
           P(sx0 - 0.4, sn0 - 0.4, eave - 0.4), P(sx1 + 0.4, sn0 - 0.4, eave - 0.4),
           P(sx1 + 0.4, sn1 + 0.4, eave + 0.3), P(sx0 - 0.4, sn1 + 0.4, eave + 0.3))

    # Potting wing to the east: enclosed 7 × 5 m
    wx0, wx1, wn0, wn1 = 8.2, 15.2, 0.5, 5.5
    wh, door_w, t = 2.5, 1.0, 0.12
    wing_pad = [(wx0 - 0.15, wn0 - 0.15), (wx1 + 0.15, wn0 - 0.15), (wx1 + 0.15, wn1 + 0.15), (wx0 - 0.15, wn1 + 0.15)]
    m.extrude(STONE, ring_xz(wing_pad), -0.1, 0.0)
    m.floor(ring_xz([(wx0, wn0), (wx1, wn0), (wx1, wn1), (wx0, wn1)]), 0.0, 'potting floor')

    # West wall open toward shed except posts; door on south of wing
    mid = (wx0 + wx1) / 2
    for label, ring in (
        ('potting door W', [(wx0, wn0), (mid - door_w / 2, wn0), (mid - door_w / 2, wn0 + t), (wx0, wn0 + t)]),
        ('potting door E', [(mid + door_w / 2, wn0), (wx1, wn0), (wx1, wn0 + t), (mid + door_w / 2, wn0 + t)]),
        ('potting east', [(wx1 - t, wn0), (wx1, wn0), (wx1, wn1), (wx1 - t, wn1)]),
        ('potting west', [(wx0, wn0), (wx0 + t, wn0), (wx0 + t, wn1), (wx0, wn1)]),
        ('potting north', [(wx0, wn1 - t), (wx1, wn1 - t), (wx1, wn1), (wx0, wn1)]),
    ):
        xz = ring_xz(ring)
        m.extrude(BOARD, xz, 0.0, wh)
        m.solid(xz, 0.0, wh, label)

    m.grid(GLASS, [[P(wx1, wn0 + 1.2, 0.8), P(wx1, wn1 - 1.0, 0.8)],
                   [P(wx1, wn0 + 1.2, 2.0), P(wx1, wn1 - 1.0, 2.0)]], up=True)
    m.extrude(METAL, ring_xz([(wx0 - 0.2, wn0 - 0.2), (wx1 + 0.2, wn0 - 0.2),
                              (wx1 + 0.2, wn1 + 0.2), (wx0 - 0.2, wn1 + 0.2)]), wh, wh + 0.12)

    # Link slab between shed and wing (built ground)
    link = [(sx1 - 0.2, wn0), (wx0 + 0.2, wn0), (wx0 + 0.2, wn1), (sx1 - 0.2, min(sn1, wn1))]
    m.extrude(STONE, ring_xz(link), -0.08, 0.0)
    m.floor(ring_xz(link), 0.0, 'link')

    built = [
        (sx0 - 0.3, sn0 - 0.3), (wx1 + 0.15, sn0 - 0.3),
        (wx1 + 0.15, max(sn1, wn1) + 0.15), (sx0 - 0.3, max(sn1, wn1) + 0.15),
    ]
    return m, built


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/agricultural-hub.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, fp = build()
    info = m.write(out, extras={
        'zone': 'agricultural-hub',
        'origin_note': 'open south bay of the shed',
        'authority': 'proposed',
        'footprint_en_m': [[round(e, 2), round(n, 2)] for e, n in fp],
    })
    info['floors'] = len(m.walk['floors'])
    info['solids'] = len(m.walk['solids'])
    print(json.dumps(info))
