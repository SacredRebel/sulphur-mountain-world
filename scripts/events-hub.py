"""
Events & Gatherings Hub — the larger hall for performances and full-room events.

  Clear floor 14×10 m = 140 m² (~4.7 m²/person standing). Crowd door 3.6 m.
  Origin: south door threshold centre.

    python scripts/events-hub.py models/events-gatherings-hub.glb
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gathering import build_hall  # noqa: E402
from glb import surface  # noqa: E402

STUCCO = surface('stucco')


def build():
    return build_hall(
        'Events & Gatherings Hub — event hall',
        width_m=14.0,
        depth_m=10.0,
        wall_h=4.2,
        door_w=3.6,
        capacity=30,
        seated=True,
        cladding=STUCCO,
        porch_m=2.5,
        ridge_rise=2.0,
    )


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/events-gatherings-hub.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, meta = build()
    info = m.write(out, extras={
        'authority': 'proposal',
        'origin_note': 'south door threshold centre',
        'gathering': meta,
        'footprint_en_m': [[-7.4, -2.9], [7.4, -2.9], [7.4, 10.4], [-7.4, 10.4]],
    })
    print(json.dumps({
        'bytes': info['bytes'], 'triangles': info['triangles'],
        'floors': len(m.walk['floors']), 'solids': len(m.walk['solids']),
        **meta,
    }))
