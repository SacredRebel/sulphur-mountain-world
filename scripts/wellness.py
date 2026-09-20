"""
Wellness Facilities — quieter gathering room for classes and treatment groups.

  Clear floor 10×7 m = 70 m² (~2.3 m²/person). Crowd door 2.8 m.
  Origin: south door threshold centre.

    python scripts/wellness.py models/wellness-facilities.glb
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gathering import build_hall  # noqa: E402
from glb import surface  # noqa: E402

TIMBER = surface('timber')


def build():
    return build_hall(
        'Wellness Facilities — class hall',
        width_m=10.0,
        depth_m=7.0,
        wall_h=3.4,
        door_w=2.8,
        capacity=30,
        seated=True,
        cladding=TIMBER,
        porch_m=1.8,
        ridge_rise=1.4,
    )


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/wellness-facilities.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, meta = build()
    info = m.write(out, extras={
        'authority': 'proposal',
        'origin_note': 'south door threshold centre',
        'gathering': meta,
        'footprint_en_m': [[-5.4, -2.2], [5.4, -2.2], [5.4, 7.4], [-5.4, 7.4]],
    })
    print(json.dumps({
        'bytes': info['bytes'], 'triangles': info['triangles'],
        'floors': len(m.walk['floors']), 'solids': len(m.walk['solids']),
        **meta,
    }))
