"""
C23.2 — build licence-manifest.json and stamp licence/source on asset records.

    python scripts/build-licence-manifest.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BINARY_SUFFIXES = {
    '.glb', '.gltf', '.bin', '.png', '.jpg', '.jpeg', '.webp',
    '.ktx2', '.basis', '.tif', '.tiff', '.npz', '.npz.gz',
}

ALLOWED = {
    'CC0-1.0',
    'MIT',
    'BSD-2-Clause',
    'BSD-3-Clause',
    'Apache-2.0',
    'Unlicense',
    'own-work',
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def git_tracked_binaries() -> list[Path]:
    out = subprocess.check_output(
        ['git', 'ls-files', '-z'],
        cwd=ROOT,
    )
    paths = []
    for raw in out.split(b'\0'):
        if not raw:
            continue
        rel = raw.decode('utf-8', errors='replace').replace('\\', '/')
        p = ROOT / rel
        if p.suffix.lower() in BINARY_SUFFIXES and p.is_file():
            paths.append(p)
    return sorted(paths, key=lambda p: p.as_posix().lower())


def classify(rel: str) -> tuple[str, str]:
    """Return (licence, source) for a repo-relative path."""
    r = rel.replace('\\', '/')
    if r.startswith('models/') and r.endswith('.glb'):
        return 'own-work', 'own-work'
    if r.startswith('textures/'):
        return 'CC0-1.0', 'https://ambientcg.com/'
    if r.startswith('terrain/'):
        return 'CC0-1.0', 'https://www.usgs.gov/3d-elevation-program'
    if r.startswith('analysis/'):
        return 'own-work', 'own-work'
    if r.endswith('.npz'):
        return 'own-work', 'own-work'
    if r.endswith(('.png', '.jpg', '.jpeg', '.webp')):
        return 'own-work', 'own-work'
    return 'own-work', 'own-work'


def stamp_models():
    path = ROOT / 'models.json'
    man = json.loads(path.read_text(encoding='utf-8'))
    for m in man['models']:
        m['licence'] = 'own-work'
        m['source'] = 'own-work'
        for lod in m.get('lods') or []:
            lod['licence'] = 'own-work'
            lod['source'] = 'own-work'
    path.write_text(json.dumps(man, indent=2) + '\n', encoding='utf-8')


def stamp_materials():
    path = ROOT / 'materials.json'
    man = json.loads(path.read_text(encoding='utf-8'))
    man['licence'] = 'CC0-1.0'
    for _name, mat in (man.get('materials') or {}).items():
        mat['licence'] = 'CC0-1.0'
        src = mat.get('source') or {}
        if isinstance(src, dict) and src.get('url'):
            mat['source'] = src['url']
        elif not isinstance(mat.get('source'), str):
            mat['source'] = 'https://ambientcg.com/'
    for _name, surf in (man.get('surfaces') or {}).items():
        if isinstance(surf, dict):
            surf.setdefault('licence', 'own-work')
            surf.setdefault('source', 'own-work')
    path.write_text(json.dumps(man, indent=2) + '\n', encoding='utf-8')


def main():
    stamp_models()
    stamp_materials()
    entries = []
    by_lic: dict[str, int] = {}
    for path in git_tracked_binaries():
        rel = path.relative_to(ROOT).as_posix()
        lic, src = classify(rel)
        if lic not in ALLOWED:
            raise SystemExit(f'classify produced disallowed licence for {rel}: {lic}')
        entries.append({
            'path': rel,
            'licence': lic,
            'source': src,
            'sha256': sha256(path),
            'bytes': path.stat().st_size,
        })
        by_lic[lic] = by_lic.get(lic, 0) + 1

    manifest = {
        'schema': 1,
        'generator': 'scripts/build-licence-manifest.py',
        'allowed_licences': sorted(ALLOWED),
        'count': len(entries),
        'by_licence': by_lic,
        'assets': entries,
    }
    out = ROOT / 'licence-manifest.json'
    out.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'OK licence-manifest: {len(entries)} assets {by_lic}')


if __name__ == '__main__':
    main()
