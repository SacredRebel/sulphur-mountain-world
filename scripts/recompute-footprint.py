"""
Recompute a model's lng/lat footprint from GLB extras.footprint_en_m + origin.

    python scripts/recompute-footprint.py models/foo.glb <id>
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_extras(path: Path):
    data = path.read_bytes()
    off, doc = 12, None
    while off + 8 <= len(data):
        clen, ctype = struct.unpack_from('<II', data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk)
    for n in doc['nodes']:
        if 'walk' in (n.get('extras') or {}):
            return n['extras']
    for s in doc.get('scenes') or []:
        if 'walk' in (s.get('extras') or {}):
            return s['extras']
    raise SystemExit('no extras')


def main():
    glb = Path(sys.argv[1])
    mid = sys.argv[2]
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    fr = pack['frame']
    mx = float(fr['metres_per_deg_lng'])
    my = float(fr['metres_per_deg_lat'])
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    m = next(x for x in man['models'] if x['id'] == mid)
    origin = m['origin']
    rot = math_rad = 0.0
    import math
    rot = math.radians(float(m.get('rotationDeg') or 0.0))
    extras = read_extras(glb)
    en = extras.get('footprint_en_m')
    if not en:
        raise SystemExit('no footprint_en_m in extras')
    fp = []
    for e, n in en:
        # rotate EN about origin (model local), then to lng/lat
        er = e * math.cos(rot) - n * math.sin(rot)
        nr = e * math.sin(rot) + n * math.cos(rot)
        fp.append([
            round(origin[0] + er / mx, 7),
            round(origin[1] + nr / my, 7),
        ])
    m['footprint'] = fp
    if 'bytes' in extras or True:
        m['bytes'] = glb.stat().st_size
    (ROOT / 'models.json').write_text(
        json.dumps(man, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
    )
    print(json.dumps({'id': mid, 'origin': origin, 'rotationDeg': m.get('rotationDeg', 0), 'footprint': fp}))


if __name__ == '__main__':
    main()
