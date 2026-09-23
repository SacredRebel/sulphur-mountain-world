"""
C25.2 — budget.json for every drawable layer and LOD band totals.

    python scripts/build-budget.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

BANDS = {
    'near': {'distance_m': [0, 60], 'lod': 'full'},
    'mid': {'distance_m': [60, 250], 'lod': 'lod1'},
    'far': {'distance_m': [250, None], 'lod': 'lod2'},
}


def file_bytes(rel: str) -> int:
    p = ROOT / rel
    return p.stat().st_size if p.exists() else 0


def geojson_features(rel: str) -> int:
    p = ROOT / rel
    if not p.exists():
        return 0
    return len(json.loads(p.read_text(encoding='utf-8')).get('features') or [])


def grid_cells(layer_id: str, pack: dict) -> int | None:
    layer = pack['layers'].get(layer_id) or {}
    meta_path = layer.get('meta')
    if not meta_path:
        return None
    meta = json.loads((ROOT / meta_path).read_text(encoding='utf-8'))
    return int(meta.get('nrows', 0)) * int(meta.get('ncols', 0))


def main():
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'pack-layers.json').read_text(encoding='utf-8'))
    rows = []
    for entry in manifest.get('layers') or []:
        lid = entry['id']
        path = entry['path']
        kind = entry['kind']
        row = {
            'id': lid,
            'kind': kind,
            'path': path,
            'bytes': file_bytes(path),
            'group': entry.get('group'),
            'appear_band': 'near' if entry.get('z', 20) <= 12 else 'mid',
            'disappear_band': 'far',
        }
        if kind == 'geojson':
            row['feature_count'] = geojson_features(path)
        if kind == 'image':
            # cell count from matching pack grid if any
            cells = grid_cells(lid, pack)
            if cells:
                row['cell_count'] = cells
            data = entry.get('data_raster')
            if data and data.endswith('.png'):
                row['data_bytes'] = file_bytes(data)
        rows.append(row)

    # tree instances + archetypes
    inst = json.loads((ROOT / 'trees-instances.json').read_text(encoding='utf-8')) if (ROOT / 'trees-instances.json').exists() else None
    if inst:
        arch_bytes = sum(file_bytes(a['path']) for a in inst['archetypes'])
        rows.append({
            'id': 'trees_instances',
            'kind': 'instances',
            'path': 'trees-instances.json',
            'bytes': file_bytes('trees-instances.json') + arch_bytes,
            'feature_count': inst['instance_count'],
            'triangle_count': sum(a['triangles'] for a in inst['archetypes']),
            'appear_band': 'near',
            'disappear_band': 'far',
        })

    # model LOD totals
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    lod_totals = {'full': {'triangles': 0, 'bytes': 0}, 'lod1': {'triangles': 0, 'bytes': 0}, 'lod2': {'triangles': 0, 'bytes': 0}}
    lod_rows = []
    for m in man['models']:
        lods = m.get('lods') or []
        full_tris = int(m.get('triangles') or 0)
        full_bytes = int(m.get('bytes') or 0)
        lod_totals['full']['triangles'] += full_tris
        lod_totals['full']['bytes'] += full_bytes
        entry = {'id': m['id'], 'full_tris': full_tris, 'full_bytes': full_bytes, 'levels': {}}
        for lod in lods:
            url = lod.get('url') or ''
            name = Path(url).name
            if 'lod1' in name:
                key = 'lod1'
            elif 'lod2' in name:
                key = 'lod2'
            else:
                key = 'full'
            tris = int(lod.get('triangles') or 0)
            b = int(lod.get('bytes') or 0)
            entry['levels'][key] = {'triangles': tris, 'bytes': b}
            if key != 'full':
                lod_totals[key]['triangles'] += tris
                lod_totals[key]['bytes'] += b
        # ratios
        if entry['levels'].get('lod1') and full_tris:
            entry['levels']['lod1']['ratio'] = round(entry['levels']['lod1']['triangles'] / full_tris, 3)
        if entry['levels'].get('lod2') and full_tris:
            entry['levels']['lod2']['ratio'] = round(entry['levels']['lod2']['triangles'] / full_tris, 3)
        lod_rows.append(entry)

    # independent scene totals = sum of layer bytes + model band bytes
    layer_bytes = sum(r['bytes'] for r in rows)
    scene = {}
    for band, spec in BANDS.items():
        lod_key = spec['lod']
        scene[band] = {
            'distance_m': spec['distance_m'],
            'triangles': lod_totals.get(lod_key if lod_key != 'full' else 'full', lod_totals['full'])['triangles'],
            'bytes_models': lod_totals.get(lod_key if lod_key != 'full' else 'full', lod_totals['full'])['bytes'],
            'bytes_layers': layer_bytes,
            'bytes_total': layer_bytes + lod_totals.get(lod_key if lod_key != 'full' else 'full', lod_totals['full'])['bytes'],
        }

    out = {
        'authority': 'derived',
        'evidence': 'modelled',
        'generator': 'scripts/build-budget.py',
        'bands': BANDS,
        'layers': rows,
        'models_lod': lod_rows,
        'lod_totals': lod_totals,
        'scene_by_band': scene,
        'layer_bytes_sum': layer_bytes,
    }
    (ROOT / 'budget.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    print(f'OK budget: {len(rows)} layers; scene near tris={scene["near"]["triangles"]}')


if __name__ == '__main__':
    main()
