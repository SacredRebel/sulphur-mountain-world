"""
C18 — LOD1 (~25% tris) and LOD2 (~5% tris) via meshoptimizer gltfpack.

  Uses the official gltfpack binary (meshoptimizer MIT). Weld + simplify;
  no Draco, no KTX2. (gltf-transform CLI unavailable here due to npm TLS;
  gltfpack is the same meshoptimizer simplify path.)

    python scripts/build-lods.py
"""
from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'models'
MAN = ROOT / 'models.json'
GLTFPACK = ROOT / 'tools' / 'gltfpack' / 'gltfpack.exe'
if not GLTFPACK.exists():
    # unzipped layout may put exe at tools/gltfpack.exe
    cands = list((ROOT / 'tools').rglob('gltfpack.exe'))
    GLTFPACK = cands[0] if cands else GLTFPACK

LOD_FULL_M = 60
LOD_1_M = 250
BASE_URL = 'https://raw.githubusercontent.com/SacredRebel/sulphur-mountain-world/main/models'


def triangle_count(glb: Path) -> int:
    data = glb.read_bytes()
    off, doc = 12, None
    while off + 8 <= len(data):
        clen, ctype = struct.unpack_from('<II', data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk)
    if not doc:
        return 0
    accessors = doc.get('accessors') or []
    tris = 0
    for m in doc.get('meshes') or []:
        for p in m.get('primitives') or []:
            ind = p.get('indices')
            if ind is not None:
                tris += accessors[ind]['count'] // 3
            else:
                pos = (p.get('attributes') or {}).get('POSITION')
                if pos is not None:
                    tris += accessors[pos]['count'] // 3
    return tris


def build_lod(src: Path, dst: Path, ratio: float, *, lock_silhouette: bool = True):
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(GLTFPACK),
        '-i', str(src),
        '-o', str(dst),
        '-si', str(ratio),
        '-se', '0.02',
    ]
    if lock_silhouette:
        cmd.append('-slb')
    print(' ', ' '.join(cmd))
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit(f'gltfpack failed for {src.name} ratio={ratio}')


def main():
    if not GLTFPACK.exists():
        raise SystemExit(f'missing {GLTFPACK} — unpack tools/gltfpack-windows.zip')
    man = json.loads(MAN.read_text(encoding='utf-8'))
    total_before = 0
    for m in man['models']:
        p = MODELS / f"{m['id']}.glb"
        if p.exists():
            total_before += p.stat().st_size

    for m in man['models']:
        mid = m['id']
        src = MODELS / f'{mid}.glb'
        if not src.exists():
            print('skip missing', mid)
            continue
        full_tris = triangle_count(src)
        lod1 = MODELS / 'lod' / f'{mid}.lod1.glb'
        lod2 = MODELS / 'lod' / f'{mid}.lod2.glb'
        print(f'{mid}: full {full_tris} tris')
        build_lod(src, lod1, 0.35, lock_silhouette=True)
        build_lod(src, lod2, 0.12, lock_silhouette=False)
        t1, t2 = triangle_count(lod1), triangle_count(lod2)
        # C25: each level must be strictly smaller; relax silhouette lock / ratio if not
        if t1 >= full_tris and full_tris > 0:
            build_lod(src, lod1, 0.5, lock_silhouette=False)
            t1 = triangle_count(lod1)
        if t2 >= t1:
            for ratio in (0.08, 0.04, 0.02):
                build_lod(src, lod2, ratio, lock_silhouette=False)
                t2 = triangle_count(lod2)
                if t2 < t1:
                    break
        if not (t2 < t1 < full_tris or full_tris <= 24):
            print(f'  WARN not strictly decreasing: full={full_tris} lod1={t1} lod2={t2}')
        m['lods'] = [
            {
                'url': f'{BASE_URL}/{mid}.glb',
                'triangles': full_tris,
                'bytes': src.stat().st_size,
                'max_distance_m': LOD_FULL_M,
            },
            {
                'url': f'{BASE_URL}/lod/{mid}.lod1.glb',
                'triangles': t1,
                'bytes': lod1.stat().st_size,
                'max_distance_m': LOD_1_M,
                'ratio': round(t1 / full_tris, 4) if full_tris else None,
            },
            {
                'url': f'{BASE_URL}/lod/{mid}.lod2.glb',
                'triangles': t2,
                'bytes': lod2.stat().st_size,
                'max_distance_m': None,
                'ratio': round(t2 / full_tris, 4) if full_tris else None,
            },
        ]
        print(f'  lod1 {t1} tris ({t1 / max(full_tris, 1):.2f}); lod2 {t2} tris ({t2 / max(full_tris, 1):.2f})')

    lod_bytes = 0
    for m in man['models']:
        for name in (f"{m['id']}.lod1.glb", f"{m['id']}.lod2.glb"):
            p = MODELS / 'lod' / name
            if p.exists():
                lod_bytes += p.stat().st_size

    # triangles in view from parcel centre at bands (sum of LODs that would show)
    # Approximate: all models use their band LOD
    bands = {'0-60m_full': 0, '60-250m_lod1': 0, '250m+_lod2': 0}
    for m in man['models']:
        lods = m.get('lods') or []
        if len(lods) >= 3:
            bands['0-60m_full'] += lods[0]['triangles']
            bands['60-250m_lod1'] += lods[1]['triangles']
            bands['250m+_lod2'] += lods[2]['triangles']

    MAN.write_text(json.dumps(man, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    summary = {
        'tool': 'meshoptimizer gltfpack',
        'bytes_full_models': total_before,
        'bytes_lod_extra': lod_bytes,
        'bytes_pack_models_with_lods': total_before + lod_bytes,
        'triangles_in_view_bands_if_all_models': bands,
    }
    (ROOT / 'analysis' / 'c18-lod-summary.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8',
    )
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
