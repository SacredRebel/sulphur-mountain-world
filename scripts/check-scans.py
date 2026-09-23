"""
C14.3 — synthetic scan placement check.

  Builds a DEM-sampled "scan" with a known similarity, recovers it via
  scripts/scan.py, and asserts RMS < 0.1 m and centre within 0.2 m.

    python scripts/check-scans.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from scan import build_synthetic, place, load_or_init_scans, SCANS_JSON  # noqa: E402
from terrain import lnglat_to_en  # noqa: E402


def main():
    errs = []
    zone = 'z-synth'
    path, gcps, truth = build_synthetic(zone)
    row = place(path, zone, gcps, synthetic_truth=truth)

    if row['rms_m'] > 0.1:
        errs.append(f"RMS {row['rms_m']} m > 0.1 m")

    e, n = lnglat_to_en(row['lng'], row['lat'])
    te, tn = truth['centre_en']
    d = math.hypot(e - te, n - tn)
    if d > 0.2:
        errs.append(f'centre offset {d:.3f} m > 0.2 m (got EN {e:.3f},{n:.3f} want {te},{tn})')

    # scale should recover ~1.05
    if abs(row['scale'] - truth['s']) > 0.05:
        errs.append(f"scale {row['scale']} far from truth {truth['s']}")

    proof = {
        'zone': zone,
        'rms_m': row['rms_m'],
        'centre_offset_m': round(d, 4),
        'scale': row['scale'],
        'truth_s': truth['s'],
        'truth_centre_en': truth['centre_en'],
        'placed_en': [round(e, 4), round(n, 4)],
        'splats': row['splats'],
    }
    (ROOT / 'analysis' / 'scans-proof.json').write_text(
        json.dumps(proof, indent=2) + '\n', encoding='utf-8',
    )

    # strip synthetic row from committed scans.json — keep template only
    doc = load_or_init_scans()
    doc['scans'] = [r for r in doc.get('scans', []) if not r.get('synthetic')]
    SCANS_JSON.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')

    # pack layer
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    layer = pack.get('layers', {}).get('scans')
    if not layer:
        errs.append('pack.layers.scans missing')
    else:
        for k in ('kind', 'authority', 'evidence', 'units', 'file'):
            if k not in layer:
                errs.append(f'pack.layers.scans missing {k}')
        if layer.get('file') != 'scans.json':
            errs.append('pack.layers.scans.file should be scans.json')

    if not (ROOT / 'capture-plan.geojson').exists():
        errs.append('missing capture-plan.geojson')
    if not (ROOT / 'analysis' / 'capture-plan.png').exists():
        errs.append('missing analysis/capture-plan.png')

    plan = json.loads((ROOT / 'capture-plan.geojson').read_text(encoding='utf-8'))
    if len(plan['features']) < 10:
        errs.append(f"capture plan has only {len(plan['features'])} zones")

    print(f"synthetic RMS={row['rms_m']:.4f} m  centre_d={d:.4f} m  scale={row['scale']:.4f}")
    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit(1)
    print('OK check-scans')


if __name__ == '__main__':
    main()
