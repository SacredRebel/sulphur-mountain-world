"""
C14.1 — tile the parcel into ~20 x 20 m capture zones with 3 m overlap.

    python scripts/capture-plan.py

Writes:
  capture-plan.geojson
  analysis/capture-plan.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LightSource
from shapely.geometry import Polygon, box, mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_grid import parcel_window, sample_dem  # noqa: E402
from terrain import en_to_lnglat, lnglat_to_en  # noqa: E402

ZONE_M = 20.0
OVERLAP_M = 3.0
STEP_M = ZONE_M - OVERLAP_M  # 17 m


def main():
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    from shapely.geometry import shape
    boundary_ll = shape(survey['features'][0]['geometry'])
    b_en = Polygon([lnglat_to_en(x, y) for x, y in boundary_ll.exterior.coords])

    e0, n0, e1, n1 = b_en.bounds
    # pad half a step so edge zones cover the ring
    cols = int(np.ceil((e1 - e0) / STEP_M))
    rows = int(np.ceil((n1 - n0) / STEP_M))

    features = []
    # serpentine walk order: west→east on even rows, east→west on odd
    order_cells = []
    for ri in range(rows):
        js = range(cols) if ri % 2 == 0 else range(cols - 1, -1, -1)
        for cj in js:
            order_cells.append((ri, cj))

    walk = 0
    for ri, cj in order_cells:
        we = e0 + cj * STEP_M
        sn = n0 + ri * STEP_M
        cell = box(we, sn, we + ZONE_M, sn + ZONE_M)
        inter = cell.intersection(b_en)
        if inter.is_empty or inter.area < 25.0:  # skip tiny edge scraps
            continue
        walk += 1
        zid = f'z{walk:03d}'
        # tip by position
        cx, cy = cell.centroid.x, cell.centroid.y
        if ri == 0 and cj == 0:
            tip = 'start at the NW corner post, walk the edge slowly, then a figure-eight inside'
        elif inter.area < ZONE_M * ZONE_M * 0.5:
            tip = 'edge zone — stay inside the survey line; walk the parcel edge first, then fill the interior'
        else:
            tip = 'start at the NW corner of this square, walk the perimeter slowly, then a figure-eight inside'
        ring_ll = [list(en_to_lnglat(x, y)) for x, y in cell.exterior.coords]
        features.append({
            'type': 'Feature',
            'properties': {
                'id': zid,
                'walk_order': walk,
                'tip': tip,
                'size_m': ZONE_M,
                'overlap_m': OVERLAP_M,
                'area_in_parcel_m2': round(float(inter.area), 1),
            },
            'geometry': {'type': 'Polygon', 'coordinates': [ring_ll]},
        })

    geo = {
        'type': 'FeatureCollection',
        'properties': {
            'authority': 'derived',
            'evidence': 'modelled',
            'zone_m': ZONE_M,
            'overlap_m': OVERLAP_M,
            'generator': 'scripts/capture-plan.py',
            'n_zones': len(features),
            'note': 'Scan files stay private (scans/ is git-ignored). This plan is the walk order only.',
        },
        'features': features,
    }
    (ROOT / 'capture-plan.geojson').write_text(json.dumps(geo, indent=2) + '\n', encoding='utf-8')

    # figure
    _, pe0, pn0, pe1, pn1 = parcel_window(5)
    es, ns, Z = sample_dem(pe0, pn0, pe1, pn1)
    fig, ax = plt.subplots(figsize=(10, 8))
    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.hillshade(np.nan_to_num(Z, nan=np.nanmean(Z)), vert_exag=2, dx=1, dy=1)
    ax.imshow(rgb, origin='lower', extent=[es[0], es[-1], ns[0], ns[-1]], cmap='gray')
    bx, by = b_en.exterior.xy
    ax.plot(bx, by, color='black', lw=1.4)
    for f in features:
        g = Polygon([lnglat_to_en(a, b) for a, b in f['geometry']['coordinates'][0]])
        xs, ys = g.exterior.xy
        ax.plot(xs, ys, color='#1565c0', lw=0.6, alpha=0.8)
        c = g.centroid
        ax.text(c.x, c.y, str(f['properties']['walk_order']), fontsize=5,
                ha='center', va='center', color='#0d47a1')
    ax.set_aspect('equal')
    ax.set_title(f'C14 capture plan — {len(features)} zones of {ZONE_M:.0f} m (overlap {OVERLAP_M:.0f} m)')
    ax.set_xlabel('east m')
    ax.set_ylabel('north m')
    fig.tight_layout()
    out = ROOT / 'analysis' / 'capture-plan.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f'OK capture-plan: {len(features)} zones -> capture-plan.geojson, {out.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
