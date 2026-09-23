"""
C21.3 — display PNGs + pack-layers.json manifest for map overlays.

  · analysis/display/<id>.png — RGBA per grid (transparent nodata / score 0)
  · grid sidecars gain display_raster + ramp
  · pack-layers.json lists image + geojson drawables

    python scripts/pack-layers.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colormaps
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DISPLAY = ROOT / 'analysis' / 'display'
MANIFEST = ROOT / 'pack-layers.json'
NODATA = 65535

SCORE_LAYERS = frozenset({'buildable', 'gathering', 'gathers'})

GRID_META = {
    'twi': {
        'label': 'Topographic wetness', 'group': 'water', 'z': 18, 'opacity': 0.7,
        'cmap': 'YlGnBu',
    },
    'stormwater_depth': {
        'label': 'Storm sheet depth', 'group': 'water', 'z': 19, 'opacity': 0.65,
        'cmap': 'Blues',
    },
    'flow_accum': {
        'label': 'Flow accumulation', 'group': 'water', 'z': 17, 'opacity': 0.6,
        'cmap': 'YlGnBu',
    },
    'cold_air': {
        'label': 'Cold-air index', 'group': 'water', 'z': 16, 'opacity': 0.65,
        'cmap': 'YlGnBu',
    },
    'sun_hours_annual': {
        'label': 'Annual sun hours', 'group': 'sun', 'z': 22, 'opacity': 0.7,
        'cmap': 'YlOrRd',
    },
    'sun_hours_dec': {
        'label': 'December sun hours', 'group': 'sun', 'z': 21, 'opacity': 0.7,
        'cmap': 'YlOrRd',
    },
    'sun_hours_jun': {
        'label': 'June sun hours', 'group': 'sun', 'z': 23, 'opacity': 0.7,
        'cmap': 'YlOrRd',
    },
    'wind_sea_breeze': {
        'label': 'Sea breeze exposure', 'group': 'habitat', 'z': 14, 'opacity': 0.65,
        'cmap': 'Purples',
    },
    'wind_santa_ana': {
        'label': 'Santa Ana exposure', 'group': 'habitat', 'z': 15, 'opacity': 0.65,
        'cmap': 'Purples',
    },
    'corridors': {
        'label': 'Wildlife corridors', 'group': 'habitat', 'z': 13, 'opacity': 0.7,
        'cmap': 'YlGn',
    },
    'landforms': {
        'label': 'Landform classes', 'group': 'terrain', 'z': 11, 'opacity': 0.75,
        'cmap': 'tab10', 'categorical': True,
    },
    'terrain': {
        'label': 'Terrain hillshade', 'group': 'terrain', 'z': 8, 'opacity': 0.88,
        'cmap': 'grey',
    },
    'buildable': {
        'label': 'Buildable score', 'group': 'surfaces', 'z': 28, 'opacity': 0.72,
        'cmap': 'YlGn',
    },
    'gathering': {
        'label': 'Gathering score', 'group': 'surfaces', 'z': 29, 'opacity': 0.72,
        'cmap': 'YlGn',
    },
    'gathers': {
        'label': 'Gathers score', 'group': 'surfaces', 'z': 27, 'opacity': 0.72,
        'cmap': 'YlGn',
    },
}

VECTOR_SPECS = [
    ('trees_crowns', 'trees-crowns.geojson', 'height_m', 'habitat', 8, 0.35, 'Tree crowns'),
    ('trees_trunks', 'trees-trunks.geojson', 'height_m', 'habitat', 9, 0.5, 'Tree trunks'),
    ('horizon', 'horizon.geojson', 'viewpoint', 'sun', 18, 0.75, 'Horizon profile'),
    ('alignments', 'alignments.geojson', 'event', 'sun', 19, 0.8, 'Solar alignments'),
    ('guides', 'guides.geojson', 'kind', 'proposed', 52, 0.85, 'Snap guides'),
    ('construction_grid', 'construction-grid.geojson', 'kind', 'proposed', 53, 0.55,
     'Construction grid (symbolic)'),
    ('drainage', 'drainage.geojson', 'order', 'water', 24, 0.85, 'Drainage channels'),
    ('keylines', 'keylines.geojson', 'kind', 'water', 25, 0.8, 'Keylines'),
    ('thermal_belt', 'thermal-belt.geojson', 'kind', 'habitat', 20, 0.55, 'Thermal belt'),
    ('oak_leaf_knoll', 'analysis/oak-leaf-knoll.geojson', 'kind', 'terrain', 12, 0.75,
     'Oak Leaf knoll analysis'),
    ('buildable_zones', 'buildable.geojson', 'band', 'surfaces', 30, 0.9, 'Buildable zones'),
    ('gathering_zones', 'gathering.geojson', 'band', 'surfaces', 31, 0.9, 'Gathering zones'),
    ('gathers_zones', 'gathers.geojson', 'band', 'surfaces', 32, 0.9, 'Gathers zones'),
    ('defensible_space', 'defensible-space.geojson', 'zone', 'defensible', 36, 0.7,
     'Defensible space'),
    ('water_harvest', 'water-harvest.geojson', 'kind', 'proposed', 42, 0.85, 'Water harvest'),
    ('capture_plan', 'capture-plan.geojson', 'walk_order', 'proposed', 41, 0.5, 'Capture plan'),
    ('cultivated_ground', 'cultivated-ground.geojson', 'kind', 'habitat', 37, 0.6,
     'Cultivated ground'),
    ('vision', 'vision.geojson', 'type', 'proposed', 45, 0.9, 'Vision zones'),
    ('survey', 'survey.geojson', 'layer', 'terrain', 50, 0.95, 'Survey'),
    ('roofs', 'roofs.geojson', 'kind', 'surfaces', 26, 0.85, 'Roof planes'),
    ('edits', 'edits.geojson', 'op', 'proposed', 48, 0.75, 'Owner edits'),
]

BAND_LABELS = {'best': 'Best', 'good': 'Good', 'workable': 'Workable'}
LANDFORM_LABELS = {
    1: 'Ridge', 2: 'Upper slope', 3: 'Mid slope', 4: 'Flat', 5: 'Lower slope', 6: 'Valley',
}


def load_pack():
    return json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))


def decode_pixel(pixel: int, meta: dict) -> float | None:
    if int(pixel) == int(meta['nodata']):
        return None
    vmin, vmax = float(meta['value_min']), float(meta['value_max'])
    return vmin + (float(pixel) / 65534.0) * (vmax - vmin)


def load_values_north_to_south(layer: dict, meta: dict) -> np.ndarray:
    """2D float array, row 0 = north (same indexing as data PNG)."""
    nrows, ncols = int(meta['nrows']), int(meta['ncols'])
    npz_path = ROOT / layer['file']
    if npz_path.exists():
        raw = np.asarray(np.load(npz_path)['data'], dtype=np.float64)
        if raw.shape != (nrows, ncols):
            raise SystemExit(f'{layer}: npz shape {raw.shape} != {ncols}x{nrows}')
        return np.flipud(raw)
    png = np.array(Image.open(ROOT / layer['raster']))
    if png.shape != (nrows, ncols):
        raise SystemExit(f'{layer}: png shape {png.shape} != nrows x ncols')
    out = np.full((nrows, ncols), np.nan, dtype=np.float64)
    for r in range(nrows):
        for c in range(ncols):
            out[r, c] = decode_pixel(int(png[r, c]), meta)
    return out


def fmt_value(v: float, units: str) -> str:
    if 'class' in units or re.search(r'\b1-6\b', units):
        return str(int(round(v)))
    av = abs(v)
    if av >= 1000:
        return f'{v:.3g}'
    if av >= 10:
        return f'{v:.1f}'
    if av >= 1:
        return f'{v:.2f}'
    return f'{v:.3g}'


def build_ramp_continuous(cmap_name: str, vmin: float, vmax: float, units: str, n: int = 6):
    cmap = colormaps.get_cmap(cmap_name)
    if vmax <= vmin:
        vmax = vmin + 1e-9
    stops = []
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0.0
        val = vmin + t * (vmax - vmin)
        r, g, b, _ = cmap(t)
        stops.append({
            'value': round(val, 6),
            'rgba': [int(round(r * 255)), int(round(g * 255)), int(round(b * 255)), 255],
            'label': fmt_value(val, units),
        })
    return {'name': cmap_name, 'stops': stops}


def build_ramp_landforms(meta: dict):
    cmap = colormaps.get_cmap('tab10')
    classes = list(range(1, 7))
    stops = []
    for k in classes:
        t = (k - 1) / max(len(classes) - 1, 1)
        r, g, b, _ = cmap(t)
        stops.append({
            'value': float(k),
            'rgba': [int(round(r * 255)), int(round(g * 255)), int(round(b * 255)), 255],
            'label': LANDFORM_LABELS.get(k, f'Class {k}'),
        })
    return {'name': 'tab10', 'stops': stops}


def value_mask(values: np.ndarray, layer_id: str, meta: dict) -> np.ndarray:
    valid = np.isfinite(values)
    if layer_id in SCORE_LAYERS:
        valid &= values > 0.0
    return valid


def render_display(values: np.ndarray, valid: np.ndarray, ramp: dict, meta: dict,
                   layer_id: str) -> np.ndarray:
    nrows, ncols = values.shape
    rgba = np.zeros((nrows, ncols, 4), dtype=np.uint8)
    if meta.get('categorical') or layer_id == 'landforms':
        cmap = colormaps.get_cmap(ramp['name'])
        for k in range(1, 7):
            m = valid & (np.abs(values - k) < 0.51)
            if not m.any():
                continue
            t = (k - 1) / 5.0
            r, g, b, _ = cmap(t)
            rgba[m, 0] = int(round(r * 255))
            rgba[m, 1] = int(round(g * 255))
            rgba[m, 2] = int(round(b * 255))
            rgba[m, 3] = 255
        return rgba

    cmap = colormaps.get_cmap(ramp['name'])
    vmin = float(meta['value_min'])
    vmax = float(meta['value_max'])
    if layer_id in SCORE_LAYERS:
        vmin, vmax = 0.0, 1.0
    span = max(vmax - vmin, 1e-9)
    norm = np.clip((values - vmin) / span, 0.0, 1.0)
    colors = cmap(norm)
    rgb = (colors[..., :3] * 255).astype(np.uint8)
    rgba[..., :3] = rgb
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return rgba


def grid_layers_from_pack(pack: dict) -> list[tuple[str, dict]]:
    items = []
    for lid, layer in pack['layers'].items():
        if layer.get('kind') != 'grid':
            continue
        if not layer.get('raster'):
            continue
        if not (ROOT / layer['raster']).exists():
            continue
        items.append((lid, layer))
    prim = [x for x in items if not x[1].get('alias_of')]
    alias = [x for x in items if x[1].get('alias_of')]
    return prim + alias


def process_grid(lid: str, layer: dict, pack: dict, display_cache: dict) -> dict:
    meta_path = ROOT / layer['meta']
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    gmeta = GRID_META.get(lid, {
        'label': lid.replace('_', ' ').title(),
        'group': 'terrain', 'z': 15, 'opacity': 0.7, 'cmap': 'viridis',
    })
    meta['categorical'] = gmeta.get('categorical', False)

    alias_of = layer.get('alias_of')
    if alias_of and alias_of in display_cache:
        rel = display_cache[alias_of]['path']
        ramp = display_cache[alias_of]['ramp']
        meta['display_raster'] = rel
        meta['ramp'] = ramp
        meta_path.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
        display_cache[lid] = {'path': rel, 'ramp': ramp}
        return manifest_image_entry(lid, layer, pack, gmeta, rel, ramp, meta)

    values = load_values_north_to_south(layer, meta)
    valid = value_mask(values, lid, meta)
    units = layer.get('units') or meta.get('units') or ''
    if lid == 'landforms':
        ramp = build_ramp_landforms(meta)
    else:
        ramp = build_ramp_continuous(
            gmeta['cmap'],
            float(meta['value_min']),
            float(meta['value_max']),
            units,
        )

    rgba = render_display(values, valid, ramp, meta, lid)
    DISPLAY.mkdir(parents=True, exist_ok=True)
    rel = f'analysis/display/{lid}.png'
    out = ROOT / rel
    Image.fromarray(rgba, mode='RGBA').save(out)

    meta['display_raster'] = rel
    meta['ramp'] = ramp
    meta_path.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    display_cache[lid] = {'path': rel, 'ramp': ramp}
    return manifest_image_entry(lid, layer, pack, gmeta, rel, ramp, meta)


def manifest_image_entry(lid, layer, pack, gmeta, rel, ramp, meta, data_raster: str | None = None):
    dr = data_raster if data_raster is not None else layer.get('raster')
    return {
        'id': lid,
        'label': gmeta['label'],
        'group': gmeta['group'],
        'kind': 'image',
        'path': rel,
        'data_raster': dr,
        'bounds_lnglat': meta['bounds_lnglat'],
        'z': gmeta['z'],
        'opacity_default': gmeta['opacity'],
        'units': layer.get('units') or meta.get('units') or '',
        'authority': layer.get('authority', 'derived'),
        'evidence': layer.get('evidence', 'modelled'),
        'legend': {'type': 'ramp', 'stops': ramp['stops']},
    }


def geojson_bounds(gj: dict) -> list[float]:
    coords: list[list[float]] = []

    def walk(c):
        if isinstance(c, (int, float)):
            return
        if len(c) >= 2 and isinstance(c[0], (int, float)) and isinstance(c[1], (int, float)):
            coords.append([float(c[0]), float(c[1])])
            return
        for part in c:
            walk(part)

    for feat in gj.get('features') or []:
        geom = feat.get('geometry')
        if geom:
            walk(geom.get('coordinates'))
    if not coords:
        pack = load_pack()
        return list(pack['aoi']['bbox'])
    lngs = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return [
        round(min(lngs), 7), round(min(lats), 7),
        round(max(lngs), 7), round(max(lats), 7),
    ]


def category_legend(style_by: str, values: list, lid: str) -> dict:
    uniq = sorted(set(values), key=lambda x: (isinstance(x, str), x))
    cmap = colormaps.get_cmap('tab20')
    categories = []
    for i, val in enumerate(uniq):
        r, g, b, _ = cmap(i / max(len(uniq) - 1, 1))
        label = str(val)
        if style_by == 'band' and val in BAND_LABELS:
            label = BAND_LABELS[val]
        if lid == 'water_harvest' and isinstance(val, str):
            label = val.replace('_', ' ').title()
        categories.append({
            'value': val,
            'rgba': [int(round(r * 255)), int(round(g * 255)), int(round(b * 255)), 200],
            'label': label,
        })
    if len(categories) < 2:
        categories.append({
            'value': '__other__',
            'rgba': [180, 180, 180, 120],
            'label': 'Other',
        })
    return {'type': 'categories', 'categories': categories}


def manifest_terrain_hillshade(pack: dict) -> dict | None:
    meta_path = ROOT / 'analysis' / 'grids' / 'terrain.json'
    display_path = ROOT / 'analysis' / 'display' / 'terrain.png'
    if not meta_path.exists() or not display_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    layer = pack['layers'].get('terrain_hillshade', {})
    gmeta = GRID_META['terrain']
    rel = meta.get('display_raster', 'analysis/display/terrain.png')
    ramp = meta.get('ramp') or {
        'name': 'greyscale',
        'stops': [
            {'value': 0.0, 'rgba': [0, 0, 0, 255], 'label': '0'},
            {'value': 1.0, 'rgba': [255, 255, 255, 255], 'label': '1'},
        ],
    }
    return manifest_image_entry(
        'terrain', layer, pack, gmeta, rel, ramp, meta,
        data_raster=layer.get('meta') or meta.get('source_dem'),
    )


def vector_manifest_entry(spec, pack: dict) -> dict | None:
    vid, relpath, style_by, group, z, opacity, label = spec
    path = ROOT / relpath
    if not path.exists():
        return None
    gj = json.loads(path.read_text(encoding='utf-8'))
    feats = gj.get('features') or []
    if not feats:
        return None

    prop_vals = []
    for f in feats:
        p = f.get('properties') or {}
        prop_vals.append(p.get(style_by))

    pack_layer = pack['layers'].get(vid) or pack['layers'].get(vid.split('_')[0]) or {}
    if vid.endswith('_zones'):
        base = vid.replace('_zones', '')
        pack_layer = pack['layers'].get(base, pack_layer)

    bounds = geojson_bounds(gj)
    legend = category_legend(style_by, prop_vals, vid)
    units = pack_layer.get('units') or 'geometry'
    if vid == 'water_harvest':
        units = 'm3 / m2'

    return {
        'id': vid,
        'label': label,
        'group': group,
        'kind': 'geojson',
        'path': relpath.replace('\\', '/'),
        'style_by': style_by,
        'bounds_lnglat': bounds,
        'z': z,
        'opacity_default': opacity,
        'units': units,
        'authority': pack_layer.get('authority', 'derived'),
        'evidence': pack_layer.get('evidence', 'modelled'),
        'legend': legend,
    }


def patch_pack_registry():
    pack_path = ROOT / 'pack.json'
    pack = json.loads(pack_path.read_text(encoding='utf-8'))
    entry = {
        'file': 'pack-layers.json',
        'kind': 'table',
        'authority': 'derived',
        'evidence': 'modelled',
        'units': 'overlay registry',
        'generator': 'scripts/pack-layers.py',
        'what': 'RGBA display rasters and drawable vector layers for the map UI',
    }
    if pack.get('pack_layers') == entry:
        return
    pack['pack_layers'] = entry
    pack_path.write_text(json.dumps(pack, indent=2) + '\n', encoding='utf-8')


def main():
    plt.ioff()
    pack = load_pack()
    display_cache: dict[str, dict] = {}
    manifest_layers: list[dict] = []

    for lid, layer in grid_layers_from_pack(pack):
        manifest_layers.append(process_grid(lid, layer, pack, display_cache))

    for spec in VECTOR_SPECS:
        entry = vector_manifest_entry(spec, pack)
        if entry:
            manifest_layers.append(entry)

    terrain_entry = manifest_terrain_hillshade(pack)
    if terrain_entry:
        manifest_layers.append(terrain_entry)

    manifest_layers.sort(key=lambda L: (L['z'], L['id']))
    # pack.json keys that are intentionally not atlas overlays (C22.3)
    not_drawable = {
        'models': 'GLB inventory and meshes — engine loads, not a map overlay',
        'scans': 'placement table; splat binaries stay private / gitignored',
        'positions': 'placement CSV for the engine, not an atlas drawable',
        'materials': 'material table, not geometry',
        'imagery': 'streamed XYZ tiles, never committed',
        'county': 'assessor ring kept for drift checks, not for siting or drawing',
        'trees': 'tabular crowns; drawn as trees_crowns + trees_trunks',
        'cultivated': 'tabular plantings; drawn as cultivated_ground',
        'sky_events': 'event table; drawn as alignments',
        'terrain': 'terrarium tile pyramid; hillshade display is layer terrain',
        'walkable': 'walkable.geojson published; atlas export deferred (C24 contract file)',
        'walk_graph': 'connectivity table, not a map overlay',
        'collision': 'physics mesh, not a map overlay',
        'trees_instances': 'instance table + archetype meshes; not an atlas overlay',
        'budget': 'cost table, not geometry',
        'grid': 'snap-grid definition table; drawn via guides / construction_grid',
        'contract': 'consumer contract table, not geometry',
    }
    manifest = {
        'schema': 1,
        'generator': 'scripts/pack-layers.py',
        'layers': manifest_layers,
        'not_drawable': not_drawable,
        # pack keys that resolve to a different manifest id
        'pack_aliases': {
            'terrain_hillshade': 'terrain',
            'trees': ['trees_crowns', 'trees_trunks'],
            'cultivated': 'cultivated_ground',
            'sky_events': 'alignments',
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    patch_pack_registry()

    n_img = sum(1 for L in manifest_layers if L['kind'] == 'image')
    n_geo = sum(1 for L in manifest_layers if L['kind'] == 'geojson')
    print(f'OK pack-layers: {n_img} image, {n_geo} geojson; not_drawable={len(not_drawable)}')


if __name__ == '__main__':
    main()
