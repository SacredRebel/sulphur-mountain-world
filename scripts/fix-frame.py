"""
C15.3 — set pack frame to WGS84 metres at origin_lat; reproject frame-metre layers.

  Trees (and cultivated) must not move on the ground:
    old x,y → lng/lat with OLD constants → new x,y with NEW constants.

    python scripts/fix-frame.py
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / 'pack.json'


def wgs84_metres_per_deg(lat_deg: float) -> tuple[float, float]:
    """Return (metres_per_deg_lng, metres_per_deg_lat) at latitude, 3 decimals."""
    a = 6378137.0
    f = 1 / 298.257223563
    e2 = f * (2 - f)
    phi = math.radians(lat_deg)
    sin2 = math.sin(phi) ** 2
    N = a / math.sqrt(1 - e2 * sin2)
    M = a * (1 - e2) / (1 - e2 * sin2) ** 1.5
    mx = N * math.cos(phi) * math.pi / 180.0
    my = M * math.pi / 180.0
    return round(mx, 3), round(my, 3)


def reproject_dm_csv(path: Path, old_mx, old_my, new_mx, new_my, ol, oa, extra_cols=0):
    rows = []
    with path.open(encoding='utf-8', newline='') as f:
        r = csv.reader(f)
        header = next(r)
        rows.append(header)
        for row in r:
            if not row:
                continue
            x_dm, y_dm = int(row[0]), int(row[1])
            e, n = x_dm / 10.0, y_dm / 10.0
            lng = ol + e / old_mx
            lat = oa + n / old_my
            e2 = (lng - ol) * new_mx
            n2 = (lat - oa) * new_my
            # keep sub-dm precision so lng/lat stay within 1 cm after the frame scale change
            row = [f'{e2 * 10:.3f}', f'{n2 * 10:.3f}'] + row[2:]
            rows.append(row)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerows(rows)
    return len(rows) - 1


def main():
    pack = json.loads(PACK_PATH.read_text(encoding='utf-8'))
    fr = pack['frame']
    old_mx = float(fr['metres_per_deg_lng'])
    old_my = float(fr['metres_per_deg_lat'])
    ol = float(fr['origin_lng'])
    oa = float(fr['origin_lat'])
    new_mx, new_my = wgs84_metres_per_deg(oa)
    print(f'frame MX {old_mx} -> {new_mx}')
    print(f'frame MY {old_my} -> {new_my}')

    fr['metres_per_deg_lng'] = new_mx
    fr['metres_per_deg_lat'] = new_my
    fr['note'] = (
        'WGS84 meridional / prime-vertical radii at origin_lat '
        '(a=6378137, f=1/298.257223563). C15.3 corrected from prior approximate constants.'
    )
    PACK_PATH.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    n_trees = reproject_dm_csv(ROOT / 'trees.csv', old_mx, old_my, new_mx, new_my, ol, oa)
    n_cult = reproject_dm_csv(ROOT / 'cultivated.csv', old_mx, old_my, new_mx, new_my, ol, oa)
    print(f'reprojected trees.csv rows={n_trees}, cultivated.csv rows={n_cult}')
    print('done — run scripts/check-frame.py')


if __name__ == '__main__':
    main()
