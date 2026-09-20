"""
Community Hub — gathering hall for ~30 people standing.

  Clear floor 12×8 m = 96 m² (~3.2 m²/person). Crowd door 3.0 m south gap.
  Origin: south door threshold centre.

    python scripts/community-hub.py models/community-hub.glb
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gathering import build_hall  # noqa: E402
from glb import surface  # noqa: E402

BOARD = surface('board_and_batten')


def build():
    return build_hall(
        'Community Hub — gathering hall',
        width_m=12.0,
        depth_m=8.0,
        wall_h=3.8,
        door_w=3.0,
        capacity=30,
        seated=True,
        cladding=BOARD,
        porch_m=2.0,
        ridge_rise=1.6,
    )


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/community-hub.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, meta = build()
    info = m.write(out, extras={
        'authority': 'proposal',
        'origin_note': 'south door threshold centre',
        'gathering': meta,
        'footprint_en_m': [[-6.4, -2.4], [6.4, -2.4], [6.4, 8.4], [-6.4, 8.4]],
    })
    print(json.dumps({
        'bytes': info['bytes'], 'triangles': info['triangles'],
        'floors': len(m.walk['floors']), 'solids': len(m.walk['solids']),
        **meta,
    }))
