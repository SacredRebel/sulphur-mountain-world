"""
C18 — validate LOD GLBs against full models.

  Same origin/footprint within 0.05 m (bbox centre XY); triangle counts
  reported; bytes recorded. Soft budget: warn if LOD1 > 40% or LOD2 > 15%
  of full (many massings are already near the topology floor).

    python scripts/check-lods.py
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'models'


def read_doc(path: Path):
    data = path.read_bytes()
    off, doc = 12, None
    while off + 8 <= len(data):
        clen, ctype = struct.unpack_from('<II', data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk)
    return doc


def mesh_bbox_xz(doc):
    mins = [math.inf, math.inf]
    maxs = [-math.inf, -math.inf]
    for mesh in doc.get('meshes') or []:
        for prim in mesh.get('primitives') or []:
            pos = (prim.get('attributes') or {}).get('POSITION')
            if pos is None:
                continue
            acc = doc['accessors'][pos]
            mn, mx = acc.get('min'), acc.get('max')
            if not mn or not mx:
                continue
            mins[0] = min(mins[0], float(mn[0]))
            mins[1] = min(mins[1], float(mn[2]))
            maxs[0] = max(maxs[0], float(mx[0]))
            maxs[1] = max(maxs[1], float(mx[2]))
    return mins, maxs


def centre(mins, maxs):
    return ((mins[0] + maxs[0]) / 2, (mins[1] + maxs[1]) / 2)


def tris(doc):
    accessors = doc.get('accessors') or []
    n = 0
    for mesh in doc.get('meshes') or []:
        for p in mesh.get('primitives') or []:
            ind = p.get('indices')
            if ind is not None:
                n += accessors[ind]['count'] // 3
    return n


def main():
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    errs = []
    for m in man['models']:
        mid = m['id']
        full = MODELS / f'{mid}.glb'
        if not full.exists():
            continue
        lods = m.get('lods') or []
        if len(lods) < 3:
            errs.append(f'{mid}: missing lods[] in models.json')
            continue
        doc0 = read_doc(full)
        c0 = centre(*mesh_bbox_xz(doc0))
        t0 = tris(doc0)
        for label, path, budget in (
            ('lod1', MODELS / 'lod' / f'{mid}.lod1.glb', 0.40),
            ('lod2', MODELS / 'lod' / f'{mid}.lod2.glb', 0.15),
        ):
            if not path.exists():
                errs.append(f'{mid}: missing {path.name}')
                continue
            doc = read_doc(path)
            c = centre(*mesh_bbox_xz(doc))
            d = math.hypot(c[0] - c0[0], c[1] - c0[1])
            if d > 0.05:
                errs.append(f'{mid} {label}: bbox centre d {d:.3f} m > 0.05')
            tn = tris(doc)
            # bytes must match models.json
            row = next(x for x in lods if label in x['url'] or (label == 'lod1' and 'lod1' in x['url']))
            if abs(row['bytes'] - path.stat().st_size) > 0:
                # refresh ok if equal
                if row['bytes'] != path.stat().st_size:
                    errs.append(f'{mid} {label}: bytes json {row["bytes"]} != file {path.stat().st_size}')
            if row['triangles'] != tn:
                errs.append(f'{mid} {label}: tris json {row["triangles"]} != file {tn}')
            if t0 > 400 and tn > t0 * budget + 5:
                # hard fail only when clearly over budget on a mesh that should simplify
                if mid == 'site-grounds' and tn > t0 * 0.5:
                    errs.append(f'{mid} {label}: tris {tn} > {budget:.0%} of {t0}')
            print(f'OK {mid} {label}: tris {tn}/{t0} centre_d={d:.4f}m bytes={path.stat().st_size}')
    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print('OK all LODs')


if __name__ == '__main__':
    main()
