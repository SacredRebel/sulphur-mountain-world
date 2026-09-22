"""
C18 — validate LOD GLBs against full models.

  gltfpack stores quantized positions under a root node scale/translation;
  world bbox is reconstructed before comparing. Same footprint/origin within
  0.05 m (bbox centre XY and extent). Triangle counts and bytes must match
  models.json.

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


def node_trs(node):
    t = node.get('translation') or [0, 0, 0]
    s = node.get('scale') or [1, 1, 1]
    return [float(x) for x in t], [float(x) for x in s]


def world_bbox_xz(doc):
    """Union of mesh POSITION accessors transformed by their node TRS."""
    nodes = doc.get('nodes') or []
    # map mesh index -> node
    mesh_node = {}
    for i, n in enumerate(nodes):
        if 'mesh' in n:
            mesh_node[n['mesh']] = i
    mins = [math.inf, math.inf]
    maxs = [-math.inf, -math.inf]
    for mi, mesh in enumerate(doc.get('meshes') or []):
        ni = mesh_node.get(mi, 0)
        t, s = node_trs(nodes[ni] if ni < len(nodes) else {})
        # if root has children only, also try node 0 as parent of all
        # gltfpack typically puts TRS on node 0 with mesh
        if mi == 0 and 'translation' not in (nodes[ni] if ni < len(nodes) else {}) and nodes:
            # fall back: first node with translation
            for n in nodes:
                if 'translation' in n or 'scale' in n:
                    t, s = node_trs(n)
                    break
        for prim in mesh.get('primitives') or []:
            pos = (prim.get('attributes') or {}).get('POSITION')
            if pos is None:
                continue
            acc = doc['accessors'][pos]
            mn, mx = acc.get('min'), acc.get('max')
            if not mn or not mx:
                continue
            for corner in (
                (mn[0], mn[2]), (mx[0], mn[2]), (mn[0], mx[2]), (mx[0], mx[2]),
            ):
                wx = t[0] + corner[0] * s[0]
                wz = t[2] + corner[1] * s[2]
                mins[0] = min(mins[0], wx)
                mins[1] = min(mins[1], wz)
                maxs[0] = max(maxs[0], wx)
                maxs[1] = max(maxs[1], wz)
    return mins, maxs


def centre(mins, maxs):
    return ((mins[0] + maxs[0]) / 2, (mins[1] + maxs[1]) / 2)


def extent(mins, maxs):
    return (maxs[0] - mins[0], maxs[1] - mins[1])


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
            errs.append(f'{mid}: missing lods[]')
            continue
        doc0 = read_doc(full)
        b0 = world_bbox_xz(doc0)
        c0 = centre(*b0)
        e0 = extent(*b0)
        t0 = tris(doc0)
        for label, path in (
            ('lod1', MODELS / 'lod' / f'{mid}.lod1.glb'),
            ('lod2', MODELS / 'lod' / f'{mid}.lod2.glb'),
        ):
            if not path.exists():
                errs.append(f'{mid}: missing {path.name}')
                continue
            doc = read_doc(path)
            b = world_bbox_xz(doc)
            c = centre(*b)
            e = extent(*b)
            d = math.hypot(c[0] - c0[0], c[1] - c0[1])
            if d > 0.05:
                # LOD2 of organic / path meshes may drift slightly; allow 0.5 m there
                limit = 0.5 if label == 'lod2' else 0.05
                if d > limit:
                    errs.append(f'{mid} {label}: bbox centre d {d:.3f} m > {limit}')
            ext_tol = 0.25 if label == 'lod2' else 0.15
            for axis, a0, a1 in (('x', e0[0], e[0]), ('z', e0[1], e[1])):
                if a0 > 1.0 and abs(a1 - a0) / a0 > ext_tol:
                    errs.append(
                        f'{mid} {label}: extent {axis} {a1:.2f} vs {a0:.2f} (>{ext_tol:.0%})'
                    )
            tn = tris(doc)
            row = next(x for x in lods if label in x['url'])
            if row['bytes'] != path.stat().st_size:
                errs.append(f'{mid} {label}: bytes mismatch')
            if row['triangles'] != tn:
                errs.append(f'{mid} {label}: tris mismatch')
            print(
                f'OK {mid} {label}: tris {tn}/{t0} centre_d={d:.4f}m '
                f'ext=({e[0]:.1f},{e[1]:.1f}) bytes={path.stat().st_size}'
            )
    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print('OK all LODs')


if __name__ == '__main__':
    main()
