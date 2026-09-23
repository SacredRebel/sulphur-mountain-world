"""
C28 — pack contract / version check.

    python scripts/check-contract.py
    python scripts/check-contract.py --self-test
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'contract.json'
PACK = ROOT / 'pack.json'
MANIFEST = ROOT / 'pack-layers.json'
DOCS = ROOT / 'docs' / 'consuming-the-pack.md'


def parse_semver(v: str) -> tuple[int, int, int]:
    m = re.match(r'^(\d+)\.(\d+)\.(\d+)$', v.strip())
    if not m:
        raise ValueError(f'bad semver {v!r}')
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def major_bumped(prev: str, cur: str) -> bool:
    return parse_semver(cur)[0] > parse_semver(prev)[0]


def load_baseline_from_tag(contract: dict) -> dict | None:
    """Prefer previous git tag's contract.json; else embedded baseline."""
    try:
        tags = subprocess.check_output(
            ['git', 'tag', '-l', 'v*'], cwd=ROOT, text=True,
        ).strip().splitlines()
    except Exception:
        tags = []
    tags = [t for t in tags if re.match(r'^v\d+\.\d+\.\d+$', t)]
    if not tags:
        return None
    # sort semver
    tags.sort(key=lambda t: parse_semver(t[1:]))
    cur = contract.get('pack_version') or '0.0.0'
    prev_tags = [t for t in tags if parse_semver(t[1:]) < parse_semver(cur)]
    if not prev_tags:
        return None
    prev = prev_tags[-1]
    try:
        raw = subprocess.check_output(
            ['git', 'show', f'{prev}:contract.json'], cwd=ROOT, text=True,
        )
        return json.loads(raw)
    except Exception:
        return None


def run_checks() -> list[str]:
    errs: list[str] = []
    contract = json.loads(CONTRACT.read_text(encoding='utf-8'))
    pack = json.loads(PACK.read_text(encoding='utf-8'))
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))

    ver = pack.get('version')
    if not ver:
        errs.append('pack.json missing version')
    elif ver != contract.get('pack_version'):
        errs.append(
            f"pack.json version {ver} != contract.pack_version {contract.get('pack_version')}"
        )
    else:
        print(f'version={ver}')

    # --- required fields on every manifest entry ---
    req_all = contract['manifest']['required_fields_all']
    req_img = contract['manifest']['required_fields_image']
    req_geo = contract['manifest']['required_fields_geojson']
    for entry in manifest.get('layers') or []:
        kind = entry.get('kind')
        need = req_img if kind == 'image' else req_geo if kind == 'geojson' else req_all
        for field in need:
            if field not in entry:
                errs.append(f"manifest {entry.get('id')}: missing {field}")
        legend = entry.get('legend') or {}
        nstops = len(legend.get('stops') or legend.get('categories') or [])
        if nstops < int(contract['manifest']['legend_min_stops_or_categories']):
            errs.append(f"manifest {entry.get('id')}: legend stops/categories < 2")
    print(f"manifest entries={len(manifest.get('layers') or [])} fields OK")

    # --- decode example reproduces real file ---
    ex = contract['raster']['worked_example']
    meta = json.loads((ROOT / ex['sidecar']).read_text(encoding='utf-8'))
    img = np.array(Image.open(ROOT / ex['png']))
    px = int(img[int(ex['png_row']), int(ex['png_col'])])
    if px != int(ex['pixel']):
        errs.append(f"decode example pixel {px} != contract {ex['pixel']}")
    decoded = meta['value_min'] + (px / 65534.0) * (meta['value_max'] - meta['value_min'])
    if abs(decoded - float(ex['decoded_value'])) > 1e-9:
        errs.append(f'decode mismatch {decoded} vs {ex["decoded_value"]}')
    z = np.load(ROOT / 'analysis' / 'grids' / 'twi.npz')['data']
    i = int(ex['npz_row'])
    j = int(ex['png_col'])
    npz_val = float(z[i, j])
    if abs(npz_val - float(ex['npz_value'])) > 1e-9:
        errs.append(f'npz example {npz_val} != contract {ex["npz_value"]}')
    if abs(decoded - npz_val) > float(ex['max_abs_diff']):
        errs.append(f'decode vs npz Δ={abs(decoded-npz_val)} > {ex["max_abs_diff"]}')
    print(f"decode example pixel={px} value={decoded:.6f} npz={npz_val:.6f}")

    # --- frame example round-trip ---
    fr = pack['frame']
    fex = contract['frame']['worked_example']
    lng = fr['origin_lng'] + fex['east_m'] / fr['metres_per_deg_lng']
    lat = fr['origin_lat'] + fex['north_m'] / fr['metres_per_deg_lat']
    if abs(lng - fex['lng']) > 1e-12 or abs(lat - fex['lat']) > 1e-12:
        errs.append(f'frame forward ({lng},{lat}) != contract')
    e2 = (lng - fr['origin_lng']) * fr['metres_per_deg_lng']
    n2 = (lat - fr['origin_lat']) * fr['metres_per_deg_lat']
    if abs(e2 - fex['east_m']) > 1e-9 or abs(n2 - fex['north_m']) > 1e-9:
        errs.append(f'frame roundtrip EN ({e2},{n2}) != ({fex["east_m"]},{fex["north_m"]})')
    print(f'frame example round-trip OK')

    # docs mention the decode numbers
    docs = DOCS.read_text(encoding='utf-8')
    if '8497' not in docs or '2.020466' not in docs:
        errs.append('docs/consuming-the-pack.md missing decode worked numbers')

    # --- removal / rename without major bump ---
    tagged = load_baseline_from_tag(contract)
    if tagged and tagged.get('compatibility'):
        baseline_pack = set(tagged['compatibility'].get('baseline_pack_layer_ids') or [])
        baseline_man = set(tagged['compatibility'].get('baseline_manifest_ids') or [])
        prev_ver = tagged.get('pack_version') or '0.0.0'
    else:
        baseline_pack = set(contract['compatibility']['baseline_pack_layer_ids'])
        baseline_man = set(contract['compatibility']['baseline_manifest_ids'])
        prev_ver = contract['compatibility'].get('baseline_version') or ver

    cur_pack = set(pack.get('layers') or {})
    cur_man = {L['id'] for L in manifest.get('layers') or []}
    removed_pack = sorted(baseline_pack - cur_pack)
    removed_man = sorted(baseline_man - cur_man)
    if removed_pack or removed_man:
        if ver and prev_ver and not major_bumped(prev_ver, ver) and prev_ver == ver:
            # same version as baseline: removals are hard errors
            if removed_pack:
                errs.append(f'pack layers removed without major bump: {removed_pack}')
            if removed_man:
                errs.append(f'manifest ids removed without major bump: {removed_man}')
        elif ver and prev_ver and not major_bumped(prev_ver, ver):
            if removed_pack:
                errs.append(
                    f'pack layers removed since {prev_ver} without major bump: {removed_pack}'
                )
            if removed_man:
                errs.append(
                    f'manifest ids removed since {prev_ver} without major bump: {removed_man}'
                )
        else:
            print(f'removals allowed by major bump → {ver}: pack={removed_pack} man={removed_man}')
    else:
        print('no baseline ids removed')

    # instances + collision presence
    inst = json.loads((ROOT / 'trees-instances.json').read_text(encoding='utf-8'))
    for k in contract['instances']['required_top']:
        if k not in inst:
            errs.append(f'trees-instances missing {k}')
    iex = contract['instances']['worked_example']
    row = next((r for r in inst['instances'] if r['tree_id'] == iex['tree_id']), None)
    if not row or row.get('archetype_id') != iex['archetype_id']:
        errs.append('instances worked example mismatch')
    col = json.loads((ROOT / 'collision.json').read_text(encoding='utf-8'))
    for k in contract['collision']['required_meta']:
        if k not in col:
            errs.append(f'collision.json missing {k}')
    if col.get('triangles') != contract['collision']['worked_example']['triangles']:
        errs.append('collision triangles mismatch vs contract example')

    return errs


def self_test() -> list[str]:
    errs: list[str] = []
    pack = json.loads(PACK.read_text(encoding='utf-8'))
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    contract = json.loads(CONTRACT.read_text(encoding='utf-8'))

    # 1) strip required field
    bad = copy.deepcopy(manifest)
    for L in bad['layers']:
        if L['kind'] == 'geojson':
            L.pop('style_by', None)
            break
    MANIFEST.write_text(json.dumps(bad) + '\n', encoding='utf-8')
    try:
        found = run_checks()
        if not any('missing style_by' in e for e in found):
            errs.append('self-test: missing style_by not caught')
        else:
            print('self-test: missing style_by caught')
    finally:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    # 2) remove a baseline pack layer without major bump
    badp = copy.deepcopy(pack)
    # delete a baseline id
    victim = 'guides'
    if victim in badp['layers']:
        del badp['layers'][victim]
    PACK.write_text(json.dumps(badp, indent=2) + '\n', encoding='utf-8')
    try:
        found = run_checks()
        if not any('removed' in e and victim in e for e in found):
            errs.append('self-test: layer removal not caught')
        else:
            print('self-test: layer removal caught')
    finally:
        PACK.write_text(json.dumps(pack, indent=2) + '\n', encoding='utf-8')

    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        errs = self_test()
    else:
        errs = run_checks()
    if errs:
        print('FAIL check-contract:')
        for e in errs:
            print(' ', e)
        raise SystemExit(1)
    print('OK check-contract')


if __name__ == '__main__':
    main()
