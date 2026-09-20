"""
Retreat Village — eight seeded cabins on the ridge, clustered to view and sun.

  Origin: the shared path node at the village heart (someone can point at it).
  Units face roughly south / south-west toward the view; never a grid.
  Seed 42 — same layout every build.

  Triangle budget: keep the whole model under 20,000 tris (~2k per dwelling).

    python scripts/retreat-village.py models/retreat-village.glb
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dwelling import add_cabin, footprint_aabb, ring_xz, unit_params  # noqa: E402
from glb import Model, surface  # noqa: E402

SEED = 42
# Cluster seats relative to the path node (east, north, yaw°). Proposed — not surveyed.
LAYOUT = [
    (-14.0, 8.0, 200),
    (-6.0, 12.5, 185),
    (4.0, 13.0, 170),
    (13.0, 9.0, 155),
    (-16.0, -2.0, 220),
    (-7.5, -6.5, 205),
    (5.5, -7.0, 175),
    (14.5, -1.5, 145),
]


def _spur(stone, m, built, x0, z0, x1, z1, w, name):
    """Axis-aligned path slab from (x0,z0) to (x1,z1) in plan east/north, width w."""
    if abs(x1 - x0) >= abs(z1 - z0):
        lo, hi = sorted([x0, x1])
        ring = [(lo, z0 - w / 2), (hi, z0 - w / 2), (hi, z0 + w / 2), (lo, z0 + w / 2)]
        # if mainly east-west but ends differ in n, add the north-south stub at the far end
        m.extrude(stone, ring_xz(ring), -0.05, 0.02)
        m.floor(ring_xz(ring), 0.02, name)
        built.append(ring)
        if abs(z1 - z0) > 0.4:
            ring2 = [(x1 - w / 2, min(z0, z1)), (x1 + w / 2, min(z0, z1)),
                     (x1 + w / 2, max(z0, z1)), (x1 - w / 2, max(z0, z1))]
            m.extrude(stone, ring_xz(ring2), -0.05, 0.02)
            m.floor(ring_xz(ring2), 0.02, name + 'b')
            built.append(ring2)
    else:
        lo, hi = sorted([z0, z1])
        ring = [(x0 - w / 2, lo), (x0 + w / 2, lo), (x0 + w / 2, hi), (x0 - w / 2, hi)]
        m.extrude(stone, ring_xz(ring), -0.05, 0.02)
        m.floor(ring_xz(ring), 0.02, name)
        built.append(ring)
        if abs(x1 - x0) > 0.4:
            ring2 = [(min(x0, x1), z1 - w / 2), (max(x0, x1), z1 - w / 2),
                     (max(x0, x1), z1 + w / 2), (min(x0, x1), z1 + w / 2)]
            m.extrude(stone, ring_xz(ring2), -0.05, 0.02)
            m.floor(ring_xz(ring2), 0.02, name + 'b')
            built.append(ring2)


def build():
    rng = random.Random(SEED)
    m = Model('Retreat Village — eight seeded cabins')
    stone = surface('stone')
    built = []

    # North–south spine through the heart
    spine = [(-2.0, -10.0), (2.0, -10.0), (2.0, 14.0), (-2.0, 14.0)]
    m.extrude(stone, ring_xz(spine), -0.06, 0.02)
    m.floor(ring_xz(spine), 0.02, 'village path')
    built.append(spine)

    for i, (e, n, yaw) in enumerate(LAYOUT):
        p = unit_params(rng, 'cabin')
        base = rng.uniform(-0.12, 0.2)
        ring = add_cabin(m, e, n, yaw, base, p, name=f'cabin {i + 1}')
        built.append(ring)
        # Approach: from the spine (clamped east) out to the door threshold
        _spur(stone, m, built, max(-1.5, min(1.5, e)), 0.0, e, n, 1.3, f'approach {i + 1}')

    return m, footprint_aabb(built)


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/retreat-village.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, fp = build()
    info = m.write(out, extras={
        'zone': 'retreat-village',
        'seed': SEED,
        'units': len(LAYOUT),
        'origin_note': 'shared path node at the village heart',
        'authority': 'proposed',
        'footprint_en_m': [[round(e, 2), round(n, 2)] for e, n in fp],
    })
    info['floors'] = len(m.walk['floors'])
    info['solids'] = len(m.walk['solids'])
    print(json.dumps(info))
