"""
Check every materials.json surface has a world field in the world's vocabulary,
and every surface key used by massing scripts maps.

    python scripts/check-materials.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD_WORDS = {
    # walls / infill
    'cob', 'hempcrete', 'strawbale', 'rammed_earth', 'adobe', 'stone', 'plaster',
    'wood', 'timber', 'glass',
    # roofs
    'solar', 'living', 'metal', 'thatch', 'tile', 'shingle',
}


def main():
    doc = json.loads((ROOT / 'materials.json').read_text(encoding='utf-8'))
    surfaces = {k: v for k, v in doc['surfaces'].items() if isinstance(v, dict) and k not in ('schema',)}
    errs = []
    for key, s in surfaces.items():
        w = s.get('world')
        if not w:
            errs.append(f'{key}: missing world field')
        elif w not in WORLD_WORDS:
            errs.append(f'{key}: world={w!r} not in world vocabulary')

    used = set()
    for py in (ROOT / 'scripts').glob('*.py'):
        text = py.read_text(encoding='utf-8')
        for m in re.finditer(r"surface\(\s*'([a-z_]+)'\s*\)", text):
            used.add(m.group(1))
    for key in sorted(used):
        if key not in surfaces:
            errs.append(f'script uses unknown surface {key}')
        elif not surfaces[key].get('world'):
            errs.append(f'used surface {key} has no world field')

    for e in errs:
        print('FAIL', e)
    if errs:
        sys.exit(1)
    print(f'OK {len(surfaces)} surfaces; {len(used)} used by scripts; all map to world words')


if __name__ == '__main__':
    main()
