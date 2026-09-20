"""
Creek-Side Glamping — five seeded tipís along the draw.

  Origin: the arrival path where the creek path meets the first deck.
  Units sit 1.4 m lower than the ridge village (altitudeM on the manifest);
  within the model they rest on platforms at y=0 facing the creek (south-east).
  Canvas + timber. Trees between pads stay outside the built footprint.

  Seed 7 — same layout every build.

    python scripts/glamping-creek.py models/glamping-creek.glb
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dwelling import add_tipi, footprint_aabb, ring_xz, unit_params  # noqa: E402
from glb import Model, surface  # noqa: E402

SEED = 7
# Loose line along the creek corridor — not a grid. Yaw toward the water (SE).
LAYOUT = [
    (0.0, 0.0, 130),
    (9.5, 3.5, 125),
    (18.0, -1.0, 140),
    (27.5, 4.0, 118),
    (36.0, 0.5, 135),
]
# Documented offset vs ridge village when placed on the map.
CREEK_BELOW_RIDGE_M = 1.4


def build():
    rng = random.Random(SEED)
    m = Model('Creek-Side Glamping — five seeded tipís')
    stone = surface('stone')
    built = []

    # Soft path along the decks (built ground only)
    path = [(-3.0, -4.0), (40.0, -4.0), (40.0, -1.5), (-3.0, -1.5)]
    m.extrude(stone, ring_xz(path), -0.05, 0.02)
    m.floor(ring_xz(path), 0.02, 'creek path')
    built.append(path)

    for i, (e, n, yaw) in enumerate(LAYOUT):
        p = unit_params(rng, 'tipi')
        # creek platforms sit a hand lower toward the water
        base = -0.35 - 0.08 * i
        ring = add_tipi(m, e, n, yaw, base, p, name=f'tipi {i + 1}')
        built.append(ring)

    return m, footprint_aabb(built)


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/glamping-creek.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, fp = build()
    info = m.write(out, extras={
        'zone': 'glamping-creek-village',
        'seed': SEED,
        'units': len(LAYOUT),
        'origin_note': 'arrival path at the first tipí deck',
        'authority': 'proposed',
        'creek_below_ridge_m': CREEK_BELOW_RIDGE_M,
        'footprint_en_m': [[round(e, 2), round(n, 2)] for e, n in fp],
    })
    info['floors'] = len(m.walk['floors'])
    info['solids'] = len(m.walk['solids'])
    print(json.dumps(info))
