"""
Cultivated plants — orchard rows and garden beds as DATA, not meshes.

  Same local frame as trees.csv (integer decimetres). The engine instances by species;
  this pack ships positions only. Cultivated-ground polygons keep the wild vegetation
  rule out of orchard and beds.

  Spacing (stated in C9-done.md):
    olives  — 6.0 m in-row and between rows (chosen: Mediterranean hillside orchard)
    citrus  — 5.0 m (small block by the beds)

    python scripts/cultivated.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from terrain import elevation_en, en_to_lnglat, lnglat_to_en  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PACK = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
OL = float(PACK['frame']['origin_lng'])
OA = float(PACK['frame']['origin_lat'])
MX = float(PACK['frame']['metres_per_deg_lng'])
MY = float(PACK['frame']['metres_per_deg_lat'])

# --- programme ---------------------------------------------------------------
OLIVE_SPACING_M = 6.0
CITRUS_SPACING_M = 5.0

# Ag hub origin (shed south bay) — beds sit just south; orchard on the contour east/south.
AG_LL = (-119.155982, 34.433478)

# Olive orchard: contour rows on the gentle slope SE of the ag hub (working orchard).
OLIVE = {
    'species': 'olive',
    'spacing_m': OLIVE_SPACING_M,
    # row anchors: (east, north) pack EN of first tree in each contour row
    # rows follow roughly constant elevation (~421–423 m), spaced 6 m downhill.
    'rows': 7,
    'trees_per_row': 12,
    'row0_en': None,  # filled from AG offset
    'row_dir': (1.0, 0.15),   # along-contour (mostly east)
    'downhill': (0.05, -1.0), # between rows (south)
    'height_m': 4.5,
    'crown_m': 3.0,
}

CITRUS = {
    'species': 'citrus',
    'spacing_m': CITRUS_SPACING_M,
    'rows': 4,
    'trees_per_row': 6,
    'row_dir': (1.0, 0.1),
    'downhill': (0.0, -1.0),
    'height_m': 3.2,
    'crown_m': 2.4,
}

# Garden beds — small rectangles in a group south of the ag shed (aerial signature).
# Six beds, 8.0 × 1.2 m, 0.8 m paths between, long axis east–west.
BEDS = {
    'n': 6,
    'length_m': 8.0,
    'width_m': 1.2,
    'gap_m': 0.8,
    'origin_offset_en': (2.0, -14.0),  # relative to ag hub EN
}


def en_to_dm(e, n, z):
    return (
        int(round(e * 10)),
        int(round(n * 10)),
        int(round(z * 10)),
    )


def unit(vx, vy):
    L = math.hypot(vx, vy) or 1.0
    return vx / L, vy / L


def place_block(spec, row0_en):
    """Return list of plant dicts for an orchard block."""
    along = unit(*spec['row_dir'])
    down = unit(*spec['downhill'])
    sp = spec['spacing_m']
    plants = []
    for r in range(spec['rows']):
        # one DEM sample per row (engine sits trees on terrain at runtime anyway)
        e_row = row0_en[0] + down[0] * r * sp
        n_row = row0_en[1] + down[1] * r * sp
        z_row = elevation_en(e_row, n_row)
        for t in range(spec['trees_per_row']):
            e = row0_en[0] + along[0] * t * sp + down[0] * r * sp
            n = row0_en[1] + along[1] * t * sp + down[1] * r * sp
            plants.append({
                'e': e, 'n': n, 'z': z_row,
                'species': spec['species'],
                'height_m': spec['height_m'],
                'crown_m': spec['crown_m'],
            })
    return plants


def bed_polygons(ag_en):
    """Return list of (id, ring_ll) for garden beds."""
    ox = ag_en[0] + BEDS['origin_offset_en'][0]
    oy = ag_en[1] + BEDS['origin_offset_en'][1]
    L, W, G = BEDS['length_m'], BEDS['width_m'], BEDS['gap_m']
    polys = []
    for i in range(BEDS['n']):
        n0 = oy - i * (W + G)
        n1 = n0 - W
        e0, e1 = ox, ox + L
        ring_en = [(e0, n0), (e1, n0), (e1, n1), (e0, n1), (e0, n0)]
        ring_ll = [list(en_to_lnglat(e, n)) for e, n in ring_en]
        polys.append((f'garden-bed-{i + 1}', ring_ll, ring_en))
    return polys


def orchard_footprint(plants, pad_m=3.0):
    """AABB of plant positions padded — wild rule stays out of the block."""
    es = [p['e'] for p in plants]
    ns = [p['n'] for p in plants]
    e0, e1 = min(es) - pad_m, max(es) + pad_m
    n0, n1 = min(ns) - pad_m, max(ns) + pad_m
    ring_en = [(e0, n0), (e1, n0), (e1, n1), (e0, n1), (e0, n0)]
    ring_ll = [list(en_to_lnglat(e, n)) for e, n in ring_en]
    return ring_ll, ring_en


def main():
    ag_en = lnglat_to_en(*AG_LL)

    # Olive block: start ~18 m east and 8 m south of the shed bay
    olive_row0 = (ag_en[0] + 18.0, ag_en[1] - 8.0)
    citrus_row0 = (ag_en[0] - 6.0, ag_en[1] - 28.0)  # smaller citrus block further south

    olives = place_block(OLIVE, olive_row0)
    citrus = place_block(CITRUS, citrus_row0)
    plants = olives + citrus

    # CSV — same frame as trees.csv + species
    csv_path = ROOT / 'cultivated.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['x_east_dm', 'y_north_dm', 'height_dm', 'crown_radius_dm', 'ground_dm', 'species'])
        for p in plants:
            xe, yn, gd = en_to_dm(p['e'], p['n'], p['z'])
            w.writerow([
                xe, yn,
                int(round(p['height_m'] * 10)),
                int(round(p['crown_m'] * 10)),
                gd,
                p['species'],
            ])

    # Cultivated-ground footprints (GeoJSON) — wild rule exclusion
    beds = bed_polygons(ag_en)
    olive_fp, olive_en = orchard_footprint(olives, pad_m=3.0)
    citrus_fp, citrus_en = orchard_footprint(citrus, pad_m=2.5)

    features = []
    for pid, ring_ll, ring_en in beds:
        area = abs(sum(
            ring_en[i][0] * ring_en[(i + 1) % 4][1] - ring_en[(i + 1) % 4][0] * ring_en[i][1]
            for i in range(4)
        )) * 0.5
        features.append({
            'type': 'Feature',
            'properties': {
                'id': pid,
                'kind': 'garden_bed',
                'authority': 'proposed',
                'suppresses': 'wild_vegetation',
                'area_m2': round(area, 1),
            },
            'geometry': {'type': 'Polygon', 'coordinates': [ring_ll]},
        })
    features.append({
        'type': 'Feature',
        'properties': {
            'id': 'olive-orchard',
            'kind': 'orchard',
            'species': 'olive',
            'spacing_m': OLIVE_SPACING_M,
            'authority': 'proposed',
            'suppresses': 'wild_vegetation',
            'n_plants': len(olives),
        },
        'geometry': {'type': 'Polygon', 'coordinates': [olive_fp]},
    })
    features.append({
        'type': 'Feature',
        'properties': {
            'id': 'citrus-block',
            'kind': 'orchard',
            'species': 'citrus',
            'spacing_m': CITRUS_SPACING_M,
            'authority': 'proposed',
            'suppresses': 'wild_vegetation',
            'n_plants': len(citrus),
        },
        'geometry': {'type': 'Polygon', 'coordinates': [citrus_fp]},
    })

    geo_path = ROOT / 'cultivated-ground.geojson'
    geo_path.write_text(json.dumps({
        'type': 'FeatureCollection',
        'name': 'cultivated-ground',
        'note': 'Footprints that keep the wild vegetation rule out of orchard rows and garden beds. Plants themselves are in cultivated.csv.',
        'features': features,
    }, indent=1) + '\n', encoding='utf-8')

    by_sp = {}
    for p in plants:
        by_sp.setdefault(p['species'], 0)
        by_sp[p['species']] += 1

    report = {
        'csv_bytes': csv_path.stat().st_size,
        'geojson_bytes': geo_path.stat().st_size,
        'total_positions': len(plants),
        'by_species': by_sp,
        'spacing_m': {'olive': OLIVE_SPACING_M, 'citrus': CITRUS_SPACING_M},
        'beds': BEDS['n'],
        'bed_size_m': [BEDS['length_m'], BEDS['width_m']],
    }
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
