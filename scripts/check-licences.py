"""
C23.2 — every tracked binary has an allowed licence; sha256 matches disk.

    python scripts/check-licences.py
    python scripts/check-licences.py --self-test
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'licence-manifest.json'

BINARY_SUFFIXES = {
    '.glb', '.gltf', '.bin', '.png', '.jpg', '.jpeg', '.webp',
    '.ktx2', '.basis', '.tif', '.tiff', '.npz', '.npz.gz',
}

# Licences that permit redistribution from a public repository / public app.
ALLOWED = {
    'CC0-1.0',
    'MIT',
    'BSD-2-Clause',
    'BSD-3-Clause',
    'Apache-2.0',
    'Unlicense',
    'own-work',
}

# Known-bad identifiers used by --self-test (must never appear for real assets).
FORBIDDEN = {
    'proprietary',
    'Commercial-NoRedistrib',
    'All-Rights-Reserved',
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def git_tracked_binaries() -> set[str]:
    out = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT)
    found = set()
    for raw in out.split(b'\0'):
        if not raw:
            continue
        rel = raw.decode('utf-8', errors='replace').replace('\\', '/')
        if Path(rel).suffix.lower() in BINARY_SUFFIXES:
            found.add(rel)
    return found


def run_checks(manifest: dict) -> list[str]:
    errs = []
    allowed = set(manifest.get('allowed_licences') or [])
    if allowed != ALLOWED:
        # allow manifest to list the same set
        if not ALLOWED.issubset(allowed):
            errs.append(f'allowed_licences missing entries: {sorted(ALLOWED - allowed)}')
    for bad in FORBIDDEN:
        if bad in allowed:
            errs.append(f'allowed_licences must not include forbidden {bad}')

    assets = manifest.get('assets') or []
    by_path = {}
    for a in assets:
        p = a.get('path')
        if not p:
            errs.append('asset missing path')
            continue
        if p in by_path:
            errs.append(f'duplicate manifest path {p}')
        by_path[p] = a
        lic = a.get('licence')
        if lic not in ALLOWED:
            errs.append(f'{p}: licence {lic!r} not allowed')
        if lic in FORBIDDEN:
            errs.append(f'{p}: forbidden licence {lic}')
        if not a.get('source'):
            errs.append(f'{p}: missing source')
        disk = ROOT / p
        if not disk.is_file():
            errs.append(f'{p}: missing on disk')
            continue
        got = sha256(disk)
        if got != a.get('sha256'):
            errs.append(f'{p}: sha256 mismatch')
        if int(a.get('bytes') or -1) != disk.stat().st_size:
            errs.append(f'{p}: byte size mismatch')

    tracked = git_tracked_binaries()
    missing = sorted(tracked - set(by_path))
    extra = sorted(set(by_path) - tracked)
    if missing:
        errs.append('tracked binaries absent from licence-manifest: ' + ', '.join(missing[:12])
                    + (f' (+{len(missing) - 12} more)' if len(missing) > 12 else ''))
    if extra:
        errs.append('licence-manifest paths not git-tracked: ' + ', '.join(extra[:12]))

    # models.json / materials.json stamps
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    for m in man.get('models') or []:
        if m.get('licence') not in ALLOWED:
            errs.append(f"models.json {m.get('id')}: bad licence {m.get('licence')!r}")
        if not m.get('source'):
            errs.append(f"models.json {m.get('id')}: missing source")

    mats = json.loads((ROOT / 'materials.json').read_text(encoding='utf-8'))
    if mats.get('licence') not in ALLOWED and mats.get('licence') != 'CC0-1.0':
        # accept only SPDX form
        if mats.get('licence') not in ALLOWED:
            errs.append(f"materials.json licence {mats.get('licence')!r} not allowed")

    print(
        f'  licence-manifest: {len(assets)} assets; '
        f'tracked binaries {len(tracked)}; '
        f'by_licence={manifest.get("by_licence")}'
    )
    return errs


def self_test():
    if not MANIFEST.exists():
        print('FAIL negative: run build-licence-manifest.py first')
        raise SystemExit(1)
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    bad = copy.deepcopy(manifest)
    if not bad['assets']:
        print('FAIL negative: empty manifest')
        raise SystemExit(1)
    bad['assets'][0]['licence'] = 'Commercial-NoRedistrib'
    errs = run_checks(bad)
    if not any('not allowed' in e or 'forbidden' in e for e in errs):
        print('FAIL negative: forbidden licence should fail')
        raise SystemExit(1)
    print(f'OK negative check-licences ({len(errs)} errs as expected)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    if not MANIFEST.exists():
        raise SystemExit('missing licence-manifest.json — run scripts/build-licence-manifest.py')
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    errs = run_checks(manifest)
    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print('OK check-licences')


if __name__ == '__main__':
    main()
