"""
C13.1 — accept organic build / shell roof / flatten structure fields on edits.

  Validates edits.geojson (and optional fixture) against the organic-spec ranges.
  Unknown keys on build/terrain features are allowed (never stripped by this check).

    python scripts/check-edits.py
    python scripts/check-edits.py fixtures/organic-edit.geojson
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORMS = {'fit', 'lobed', 'oval', 'leaf', 'shell'}
STRUCTURES = {'steel', 'timber', 'bamboo', 'none'}
INFILLS = {
    'cob', 'hempcrete', 'strawbale', 'rammed_earth', 'adobe', 'stone',
    'plaster', 'wood', 'timber', 'glass',
}
INSULATIONS = {'hemp', 'wool', 'cork', 'strawbale', 'none'}
ROOFS = {'solar', 'living', 'metal', 'thatch', 'tile', 'shingle'}
FLOORS = {'earth', 'stone', 'wood', 'concrete', 'timber'}
ROOF_FORMS = {'flat', 'shed', 'gable', 'hip', 'vault', 'shell'}


def _num(v, lo, hi, path, errors):
    if v is None:
        return
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        errors.append(f'{path}: expected number, got {type(v).__name__}')
        return
    if v < lo or v > hi:
        errors.append(f'{path}: {v} outside [{lo}, {hi}]')


def _enum(v, allowed, path, errors):
    if v is None:
        return
    if v not in allowed:
        errors.append(f'{path}: {v!r} not in {sorted(allowed)}')


def check_organic(org: dict, path: str, errors: list):
    if not isinstance(org, dict):
        errors.append(f'{path}: organic must be an object')
        return
    _enum(org.get('form'), FORMS, f'{path}.form', errors)
    if org.get('form') == 'lobed' or 'lobes' in org:
        _num(org.get('lobes'), 2, 12, f'{path}.lobes', errors)
    _num(org.get('depth'), 0, 0.6, f'{path}.depth', errors)
    _num(org.get('turn'), -360, 360, f'{path}.turn', errors)
    _num(org.get('inset'), 0, 10, f'{path}.inset', errors)
    _num(org.get('height'), 2.2, 9, f'{path}.height', errors)
    _num(org.get('rise'), 0.3, 8, f'{path}.rise', errors)
    _num(org.get('overhang'), 0, 3, f'{path}.overhang', errors)
    _num(org.get('thick'), 0.12, 1, f'{path}.thick', errors)
    _enum(org.get('structure'), STRUCTURES, f'{path}.structure', errors)
    _enum(org.get('infill'), INFILLS, f'{path}.infill', errors)
    _enum(org.get('insulation'), INSULATIONS, f'{path}.insulation', errors)
    _enum(org.get('roof'), ROOFS, f'{path}.roof', errors)
    _num(org.get('solar'), 0, 1, f'{path}.solar', errors)
    _num(org.get('glazing'), 0, 1, f'{path}.glazing', errors)
    _num(org.get('facing'), 0, 360, f'{path}.facing', errors)
    _num(org.get('door'), 0, 360, f'{path}.door', errors)
    _enum(org.get('floor'), FLOORS, f'{path}.floor', errors)
    if 'pad' in org and not isinstance(org['pad'], bool):
        errors.append(f'{path}.pad: expected boolean')
    per = org.get('perimeter')
    if per is not None:
        if not isinstance(per, list) or len(per) < 3:
            errors.append(f'{path}.perimeter: need ≥3 [lng,lat] rings')
        else:
            for i, pt in enumerate(per):
                if not (isinstance(pt, (list, tuple)) and len(pt) >= 2):
                    errors.append(f'{path}.perimeter[{i}]: need [lng,lat]')
    # pad_id, and any extra keys — allowed (never stripped)


def check_assembly_wall(asm: dict, path: str, errors: list):
    if not isinstance(asm, dict):
        errors.append(f'{path}: assembly must be an object')
        return
    _enum(asm.get('structure'), STRUCTURES, f'{path}.structure', errors)
    _enum(asm.get('infill'), INFILLS, f'{path}.infill', errors)
    _enum(asm.get('insulation'), INSULATIONS, f'{path}.insulation', errors)


def check_assembly_roof(asm: dict, path: str, errors: list):
    if not isinstance(asm, dict):
        errors.append(f'{path}: assembly must be an object')
        return
    _enum(asm.get('roof_structure'), STRUCTURES, f'{path}.roof_structure', errors)
    _enum(asm.get('insulation'), INSULATIONS, f'{path}.insulation', errors)


def check_feature(f: dict, errors: list):
    props = f.get('properties') or {}
    layer = props.get('layer')
    kind = props.get('kind')
    fid = props.get('id') or '(no id)'
    base = f'feature {fid}'

    if layer == 'build' and kind == 'floor' and 'organic' in props:
        check_organic(props['organic'], f'{base}.organic', errors)

    if layer == 'build' and kind == 'wall':
        if props.get('smooth') not in (None, True, False):
            errors.append(f'{base}.smooth: expected boolean')
        if 'assembly' in props:
            check_assembly_wall(props['assembly'], f'{base}.assembly', errors)
        if 'openings' in props and not isinstance(props['openings'], list):
            errors.append(f'{base}.openings: expected list')

    if layer == 'build' and kind == 'roof':
        _enum(props.get('form'), ROOF_FORMS, f'{base}.form', errors)
        if props.get('form') == 'shell' or props.get('form') == 'shell':
            _num(props.get('eaves_m'), 0, 20, f'{base}.eaves_m', errors)
            _num(props.get('rise_m'), 0, 20, f'{base}.rise_m', errors)
            _num(props.get('overhang_m'), 0, 10, f'{base}.overhang_m', errors)
            _enum(props.get('finish'), ROOFS, f'{base}.finish', errors)
            _num(props.get('solar_ratio'), 0, 1, f'{base}.solar_ratio', errors)
            _num(props.get('solar_facing_deg'), 0, 360, f'{base}.solar_facing_deg', errors)
        if 'assembly' in props:
            check_assembly_roof(props['assembly'], f'{base}.assembly', errors)

    if layer == 'terrain' and props.get('terrain_op') == 'flatten':
        if 'structure' in props and not isinstance(props['structure'], str):
            errors.append(f'{base}.structure: expected string name')


def check_doc(doc: dict, label: str) -> list[str]:
    errors: list[str] = []
    if doc.get('type') != 'FeatureCollection':
        errors.append(f'{label}: expected FeatureCollection')
        return errors
    for f in doc.get('features') or []:
        check_feature(f, errors)
    return errors


def main():
    paths = [ROOT / 'edits.geojson']
    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    fixture = ROOT / 'fixtures' / 'organic-edit.geojson'
    if fixture.exists() and fixture not in paths:
        paths.append(fixture)

    all_err = []
    for p in paths:
        if not p.exists():
            print(f'skip missing {p}')
            continue
        doc = json.loads(p.read_text(encoding='utf-8'))
        err = check_doc(doc, str(p))
        if err:
            print(f'FAIL {p}')
            for e in err:
                print(' ', e)
            all_err.extend(err)
        else:
            n = len(doc.get('features') or [])
            print(f'OK {p} ({n} features; organic fields accepted, extras kept)')

    if all_err:
        raise SystemExit(1)
    print('OK edits schema')


if __name__ == '__main__':
    main()
