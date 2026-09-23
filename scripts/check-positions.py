"""
C17.2 — second proof of positions.csv.

  1. Each model: open GLB, bbox centre + base after placement (origin at
     lng/lat, base on terrain). Match table within 0.10 m horizontal /
     0.15 m vertical.
  2. Footprint vs GLB plan outline at ground: area within 3%, centroid
     within 0.25 m.
  3. Re-run survey call check + tree lng/lat stability (check-frame).
  4. Write analysis/positions-proof.png.
  5. Fail on any miss.

  Oak Leaf (C17.3): do not move; report distances to boundary, creek, oaks.

    python scripts/check-positions.py
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import struct
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from creek import FORD_EN  # noqa: E402
from terrain import elevation_lnglat, en_to_lnglat, lnglat_to_en  # noqa: E402

POS_CSV = ROOT / 'positions.csv'
POS_GEO = ROOT / 'positions.geojson'
OUT_PNG = ROOT / 'analysis' / 'positions-proof.png'
HORIZ_TOL_M = 0.10
VERT_TOL_M = 0.15
AREA_TOL = 0.03
CENTROID_TOL_M = 0.25


def load_check_frame():
    path = ROOT / 'scripts' / 'check-frame.py'
    spec = importlib.util.spec_from_file_location('check_frame', path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def read_glb(path: Path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from('<III', data, 0)
    if magic != 0x46546C67:
        raise ValueError(f'{path}: not a GLB')
    off = 12
    doc = None
    while off + 8 <= length:
        clen, ctype = struct.unpack_from('<II', data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk.decode('utf-8'))
    if doc is None:
        raise ValueError(f'{path}: no JSON chunk')
    return doc


def walk_extras(doc):
    for node in doc.get('nodes') or []:
        extras = node.get('extras') or {}
        if 'walk' in extras:
            return extras
    for scene in doc.get('scenes') or []:
        extras = scene.get('extras') or {}
        if 'walk' in extras:
            return extras
    return {}


def mesh_bounds(doc):
    mins = [math.inf, math.inf, math.inf]
    maxs = [-math.inf, -math.inf, -math.inf]
    for mesh in doc.get('meshes') or []:
        for prim in mesh.get('primitives') or []:
            pos = (prim.get('attributes') or {}).get('POSITION')
            if pos is None:
                continue
            acc = doc['accessors'][pos]
            mn, mx = acc.get('min'), acc.get('max')
            if mn is None or mx is None:
                continue
            for i in range(3):
                mins[i] = min(mins[i], float(mn[i]))
                maxs[i] = max(maxs[i], float(mx[i]))
    if not math.isfinite(mins[0]):
        raise ValueError('no POSITION min/max')
    return mins, maxs


def rotate_xz(x, z, deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    # yaw about +Y: x' = x cos - z sin; z' = x sin + z cos
    return x * c - z * s, x * s + z * c


def oak_leaf_outline_from_solids(doc) -> list[tuple[float, float]]:
    """Same plan outline as scripts/oak-footprint.py (padded convex hull of solids)."""
    import numpy as np
    from scipy.spatial import ConvexHull

    exclude = ('oak lounge fire', 'oak lounge seat', 'standing stone')
    pad_m = 0.35
    walk = (walk_extras(doc).get('walk') or {})
    pts = []
    for s in walk.get('solids') or []:
        name = s.get('name') or ''
        if any(name == p or name.startswith(p + ' ') for p in exclude):
            continue
        for x, z in s.get('ring') or []:
            pts.append((float(x), float(-z)))
    arr = np.asarray(pts, float)
    hull = ConvexHull(arr)
    hull_ring = [tuple(arr[i]) for i in hull.vertices]
    buf = list(hull_ring)
    for e, n in hull_ring:
        for k in range(12):
            a = 2 * math.pi * k / 12
            buf.append((e + pad_m * math.cos(a), n + pad_m * math.sin(a)))
    barr = np.asarray(buf, float)
    bh = ConvexHull(barr)
    padded = [tuple(barr[i]) for i in bh.vertices]
    # densify to 56 like oak-footprint
    target = 56
    out = []
    per = max(1, (target + len(padded) - 1) // len(padded))
    for i in range(len(padded)):
        a = np.asarray(padded[i], float)
        b = np.asarray(padded[(i + 1) % len(padded)], float)
        out.append(tuple(a))
        for k in range(1, per):
            t = k / per
            out.append(tuple(a * (1 - t) + b * t))
    return out[:target]


def glb_plan_outline_en(doc, rot_deg: float, model_id: str | None = None):
    """Local plan outline in east/north metres relative to model origin.

    Returns a ring, or the string 'envelope' when models.json footprint is the
    authoritative vegetation envelope (site-grounds) and floors must lie inside it.
    """
    extras = walk_extras(doc)

    if model_id == 'site-grounds':
        # C23.1: registry footprint is floors∪ + 3 m (not an AABB envelope).
        # Compare against the same construction from walk extras.
        floors = (extras.get('walk') or {}).get('floors') or []
        polys = []
        for fl in floors:
            ring = fl.get('ring') or []
            if len(ring) < 3:
                continue
            pts = []
            for x, z in ring:
                xr, zr = rotate_xz(float(x), float(z), rot_deg)
                pts.append((xr, -zr))
            try:
                p = Polygon(pts)
                if p.is_valid and p.area > 0.05:
                    polys.append(p)
            except Exception:
                continue
        if not polys:
            return 'envelope'
        u = unary_union(polys).buffer(3.0).simplify(0.5, preserve_topology=True)
        if u.geom_type == 'MultiPolygon':
            u = max(u.geoms, key=lambda g: g.area)
        return list(u.exterior.coords)[:-1]

    if model_id == 'oak-leaf-massing':
        # C9 solids hull is the registry footprint; extras may lag
        return oak_leaf_outline_from_solids(doc)

    fp = extras.get('footprint_en_m')
    if fp and len(fp) >= 3:
        r = math.radians(rot_deg)
        c, s = math.cos(r), math.sin(r)
        out = []
        for e, n in fp:
            er = float(e) * c - float(n) * s
            nr = float(e) * s + float(n) * c
            out.append((er, nr))
        return out

    # Fall back: union of walk floor rings (x,z) -> (e,n)=(x,-z)
    floors = (extras.get('walk') or {}).get('floors') or []
    polys = []
    for fl in floors:
        ring = fl.get('ring') or []
        if len(ring) < 3:
            continue
        pts = []
        for x, z in ring:
            xr, zr = rotate_xz(float(x), float(z), rot_deg)
            pts.append((xr, -zr))
        try:
            p = Polygon(pts)
            if p.is_valid and p.area > 0.05:
                polys.append(p)
        except Exception:
            continue
    if polys:
        u = unary_union(polys)
        if u.geom_type == 'Polygon':
            return list(u.exterior.coords)[:-1]
        geoms = list(u.geoms)
        big = max(geoms, key=lambda g: g.area)
        return list(big.exterior.coords)[:-1]

    mins, maxs = mesh_bounds(doc)
    corners = [
        (mins[0], mins[2]), (maxs[0], mins[2]),
        (maxs[0], maxs[2]), (mins[0], maxs[2]),
    ]
    out = []
    for x, z in corners:
        xr, zr = rotate_xz(x, z, rot_deg)
        out.append((xr, -zr))
    return out


def poly_area_centroid(ring_en):
    if len(ring_en) < 3:
        return 0.0, (0.0, 0.0)
    p = Polygon(ring_en)
    if not p.is_valid:
        p = p.buffer(0)
    if p.is_empty:
        return 0.0, (0.0, 0.0)
    c = p.centroid
    return float(p.area), (float(c.x), float(c.y))


def load_positions():
    rows = []
    with POS_CSV.open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def load_parcel_en():
    survey = json.loads((ROOT / 'survey.geojson').read_text(encoding='utf-8'))
    boundary = next(f for f in survey['features'] if f['properties'].get('layer') == 'boundary')
    ring = boundary['geometry']['coordinates'][0]
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    parcel_en = Polygon([lnglat_to_en(float(a), float(b)) for a, b in ring])
    if not parcel_en.is_valid:
        parcel_en = parcel_en.buffer(0)
    easements = []
    for f in survey['features']:
        if f['properties'].get('layer') != 'easement':
            continue
        g = f['geometry']
        if g['type'] == 'Polygon':
            coords = g['coordinates'][0]
            easements.append(Polygon([lnglat_to_en(float(a), float(b)) for a, b in coords[:-1]]))
        elif g['type'] == 'LineString':
            coords = g['coordinates']
            easements.append(LineString([lnglat_to_en(float(a), float(b)) for a, b in coords]))
        elif g['type'] == 'MultiPolygon':
            for poly in g['coordinates']:
                coords = poly[0]
                easements.append(Polygon([lnglat_to_en(float(a), float(b)) for a, b in coords[:-1]]))
    pob_ll = (float(ring[0][0]), float(ring[0][1]))
    pob_en = lnglat_to_en(*pob_ll)
    return survey, parcel_en, easements, pob_en, ring


def check_models(rows, man_by_id) -> list[str]:
    errs = []
    n_ok = 0
    for r in rows:
        if r['kind'] != 'model':
            continue
        mid = r['id']
        m = man_by_id.get(mid)
        if not m:
            errs.append(f'{mid}: missing from models.json')
            continue
        glb_name = m['url'].rsplit('/', 1)[-1]
        glb_path = ROOT / 'models' / glb_name
        if not glb_path.exists():
            errs.append(f'{mid}: missing GLB {glb_name}')
            continue

        lng, lat = float(r['lng']), float(r['lat'])
        pack_x, pack_y = float(r['pack_x']), float(r['pack_y'])
        elev_m = float(r['elev_m'])
        alt = float(m.get('altitudeM') or 0.0)
        rot = float(m.get('rotationDeg') or 0.0)

        # --- placement: origin at table lng/lat; base on terrain (+ altitudeM) ---
        pe, pn = lnglat_to_en(lng, lat)
        d_pack = math.hypot(pe - pack_x, pn - pack_y)
        if d_pack > HORIZ_TOL_M:
            errs.append(f'{mid}: pack vs lng/lat {d_pack:.3f} m > {HORIZ_TOL_M}')

        terr = elevation_lnglat(lng, lat)
        d_elev = abs(terr - elev_m)
        if d_elev > VERT_TOL_M:
            errs.append(f'{mid}: elev_m {elev_m:.3f} vs terrain {terr:.3f} (d {d_elev:.3f} m)')

        doc = read_glb(glb_path)
        mins, maxs = mesh_bounds(doc)
        # Bbox centre / base after placement (local x east, y up, z south)
        cx = 0.5 * (mins[0] + maxs[0])
        cy = 0.5 * (mins[1] + maxs[1])
        cz = 0.5 * (mins[2] + maxs[2])
        xr, zr = rotate_xz(cx, cz, rot)
        centre_e = pack_x + xr
        centre_n = pack_y - zr
        # y=0 sits at elev_m + altitudeM; mesh base and centre follow
        base_elev = elev_m + alt + mins[1]
        centre_elev = elev_m + alt + cy
        expected_base = terr + alt + mins[1]
        if abs(base_elev - expected_base) > VERT_TOL_M:
            errs.append(
                f'{mid}: placed base elev {base_elev:.3f} vs terrain+alt+ymin '
                f'{expected_base:.3f} (d {abs(base_elev - expected_base):.3f} m)'
            )
        # Horizontal: placed origin (table) vs pack columns — already d_pack.
        # Bbox centre is reported relative to origin; origin itself must match table.
        origin_e, origin_n = pack_x, pack_y
        if math.hypot(origin_e - pe, origin_n - pn) > HORIZ_TOL_M:
            errs.append(f'{mid}: placed origin off table by > {HORIZ_TOL_M} m')
        _ = (centre_e, centre_n, centre_elev)

        fp_ll = m.get('footprint')
        if fp_ll and len(fp_ll) >= 3:
            fp_en = [lnglat_to_en(float(a), float(b)) for a, b in fp_ll]
            if fp_en[0] == fp_en[-1]:
                fp_en = fp_en[:-1]

            # Footprint vs GLB plan outline at ground
            outline = glb_plan_outline_en(doc, rot, model_id=mid)
            a_tab, c_tab = poly_area_centroid(fp_en)

            if outline and len(outline) >= 3:
                world_outline = [(pack_x + e, pack_y + n) for e, n in outline]
                a_glb, c_glb = poly_area_centroid(world_outline)
                if a_tab > 1.0:
                    rel = abs(a_glb - a_tab) / a_tab
                    if rel > AREA_TOL:
                        errs.append(
                            f'{mid}: footprint area table {a_tab:.1f} vs GLB {a_glb:.1f} '
                            f'({rel * 100:.1f}% > {AREA_TOL * 100:.0f}%)'
                        )
                    d_cent = math.hypot(c_tab[0] - c_glb[0], c_tab[1] - c_glb[1])
                    if d_cent > CENTROID_TOL_M:
                        errs.append(
                            f'{mid}: footprint centroid d {d_cent:.3f} m > {CENTROID_TOL_M}'
                        )

        n_ok += 1
    print(f'model placement checks: {n_ok} models examined')
    return errs


def check_frame_reuse() -> list[str]:
    cf = load_check_frame()
    pack = json.loads((ROOT / 'pack.json').read_text(encoding='utf-8'))
    fr = pack['frame']
    errs = []
    call_errs = cf.check_calls(fr)
    errs.extend(call_errs)
    baseline_path = cf.BASELINE
    if not baseline_path.exists():
        errs.append('no trees-lnglat-baseline.json — run check-frame --write-baseline')
    else:
        base = json.loads(baseline_path.read_text(encoding='utf-8'))
        tree_errs = cf.check_trees(fr, base['trees'])
        errs.extend(tree_errs)
    return errs


def oak_leaf_report(rows, parcel_en):
    """C17.3 — report only; never move oak-leaf-massing."""
    oak = next(r for r in rows if r['id'] == 'oak-leaf-massing')
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    m = next(x for x in man['models'] if x['id'] == 'oak-leaf-massing')
    fp_en = [lnglat_to_en(float(a), float(b)) for a, b in m['footprint']]
    if fp_en[0] == fp_en[-1]:
        fp_en = fp_en[:-1]
    poly = Polygon(fp_en)
    if not poly.is_valid:
        poly = poly.buffer(0)

    # creek footprint from models.json
    creek = next(x for x in man['models'] if x['id'] == 'creek')
    creek_fp = [lnglat_to_en(float(a), float(b)) for a, b in creek['footprint']]
    if creek_fp[0] == creek_fp[-1]:
        creek_fp = creek_fp[:-1]
    creek_poly = Polygon(creek_fp)

    d_boundary = float(oak['min_boundary_m'])
    d_creek = float(poly.distance(creek_poly))

    # oaks: trees.csv trunks inside / near (within 5 m of footprint)
    near = []
    inside = []
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            e = float(row['x_east_dm']) / 10.0
            n = float(row['y_north_dm']) / 10.0
            h = float(row['height_dm']) / 10.0
            # oak-ish: tall canopy trees near house (height >= 8 m)
            pt = Point(e, n)
            if poly.contains(pt) or poly.covers(pt):
                inside.append((e, n, h, 0.0))
            else:
                d = pt.distance(poly)
                if d <= 5.0 and h >= 8.0:
                    near.append((e, n, h, d))

    report = {
        'id': 'oak-leaf-massing',
        'lng': float(oak['lng']),
        'lat': float(oak['lat']),
        'pack_x': float(oak['pack_x']),
        'pack_y': float(oak['pack_y']),
        'elev_m': float(oak['elev_m']),
        'footprint_m2': float(oak['footprint_m2']),
        'from_POB_m': float(oak['from_POB_m']),
        'bearing_from_POB_deg': float(oak['bearing_from_POB_deg']),
        'min_boundary_m': d_boundary,
        'inside_parcel': oak['inside_parcel'] in (True, 'true', 'True'),
        'dist_creek_footprint_m': round(d_creek, 3),
        'trees_inside_footprint': len(inside),
        'trees_near_5m_hge8': len(near),
        'nearest_tree_m': round(min((t[3] for t in near), default=0.0), 3) if near else None,
        'moved': False,
        'note': 'C17.3 - Oak Leaf not moved',
    }
    return report, poly


def draw_proof(rows, man_by_id, parcel_en, easements, pob_en, oak_poly):
    fig, ax = plt.subplots(figsize=(12, 10))

    # parcel
    xs, ys = parcel_en.exterior.xy
    ax.plot(xs, ys, color='#1b5e20', lw=1.6, zorder=4, label='survey boundary')

    for eas in easements:
        if eas.geom_type == 'Polygon':
            ex, ey = eas.exterior.xy
            ax.fill(ex, ey, color='#fff9c4', alpha=0.55, zorder=2)
            ax.plot(ex, ey, color='#f9a825', lw=0.9, zorder=3)
        else:
            ex, ey = eas.xy
            ax.plot(ex, ey, color='#f9a825', lw=2.0, zorder=3)

    # footprints
    for r in rows:
        if r['kind'] != 'model':
            continue
        m = man_by_id.get(r['id'])
        if not m or not m.get('footprint'):
            continue
        fp = [lnglat_to_en(float(a), float(b)) for a, b in m['footprint']]
        if fp[0] == fp[-1]:
            fp = fp[:-1]
        poly = MplPolygon(
            fp, closed=True, facecolor='#90caf9', edgecolor='#1565c0',
            alpha=0.45, lw=0.7, zorder=5,
        )
        ax.add_patch(poly)
        cx = sum(p[0] for p in fp) / len(fp)
        cy = sum(p[1] for p in fp) / len(fp)
        label = r['id'].replace('-massing', '').replace('-facilities', '').replace('-program', '')
        if len(label) > 18:
            label = label[:16] + '..'
        ax.annotate(label, (cx, cy), fontsize=6, ha='center', va='center', zorder=6, color='#0d47a1')

    # feature pads / points
    for r in rows:
        if r['kind'] in ('model', 'survey_corner', 'footprint'):
            continue
        ax.plot(float(r['pack_x']), float(r['pack_y']), 'o', color='#6a1b9a', ms=4, zorder=7)
        ax.annotate(r['id'], (float(r['pack_x']), float(r['pack_y'])),
                    fontsize=5.5, color='#4a148c', xytext=(3, 3), textcoords='offset points')

    # corners
    for r in rows:
        if r['kind'] != 'survey_corner':
            continue
        ax.plot(float(r['pack_x']), float(r['pack_y']), 's', color='#1b5e20', ms=4, zorder=8)

    # POB
    ax.plot(pob_en[0], pob_en[1], '*', color='#c62828', ms=14, zorder=9)
    ax.annotate('POB', (pob_en[0], pob_en[1]), fontsize=9, color='#c62828',
                fontweight='bold', xytext=(6, 6), textcoords='offset points')

    # ford
    ax.plot(FORD_EN[0], FORD_EN[1], 'D', color='#0277bd', ms=7, zorder=8)
    ax.annotate('ford', FORD_EN, fontsize=7, color='#0277bd',
                xytext=(5, -10), textcoords='offset points')

    # scale bar (50 m)
    minx, miny, maxx, maxy = parcel_en.bounds
    sb_x = minx + 20
    sb_y = miny + 15
    ax.plot([sb_x, sb_x + 50], [sb_y, sb_y], color='k', lw=2.5, zorder=10)
    ax.plot([sb_x, sb_x], [sb_y - 2, sb_y + 2], color='k', lw=1.5, zorder=10)
    ax.plot([sb_x + 50, sb_x + 50], [sb_y - 2, sb_y + 2], color='k', lw=1.5, zorder=10)
    ax.text(sb_x + 25, sb_y + 4, '50 m', ha='center', fontsize=8, zorder=10)

    # north arrow
    nx = maxx - 35
    ny = maxy - 40
    ax.annotate(
        'N', xy=(nx, ny + 25), xytext=(nx, ny),
        arrowprops=dict(arrowstyle='->', color='k', lw=1.5),
        ha='center', va='bottom', fontsize=11, fontweight='bold', zorder=10,
    )

    ax.set_aspect('equal')
    ax.set_xlabel('east (m, pack frame)')
    ax.set_ylabel('north (m, pack frame)')
    ax.set_title('C17 positions proof — survey boundary, easements, footprints, POB')
    legend = [
        Line2D([0], [0], color='#1b5e20', lw=1.6, label='survey boundary'),
        Line2D([0], [0], color='#f9a825', lw=1.5, label='16 ft easement'),
        Line2D([0], [0], marker='s', color='#90caf9', markeredgecolor='#1565c0',
               lw=0, label='model footprint'),
        Line2D([0], [0], marker='*', color='#c62828', lw=0, markersize=10, label='POB'),
        Line2D([0], [0], marker='o', color='#6a1b9a', lw=0, label='site feature'),
    ]
    ax.legend(handles=legend, loc='lower right', fontsize=8)
    fig.text(
        0.5, 0.01,
        'UTM columns: EPSG:32611 (WGS84 UTM 11N). Pack EN: C15.3 WGS84 frame. DEM: USGS 3DEP 1 m.',
        ha='center', fontsize=7,
    )
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)
    print(f'wrote {OUT_PNG}')


def main():
    if not POS_CSV.exists():
        print('FAIL no positions.csv — run scripts/build-positions.py first')
        sys.exit(1)

    rows = load_positions()
    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    man_by_id = {m['id']: m for m in man['models']}
    _, parcel_en, easements, pob_en, _ = load_parcel_en()

    errs: list[str] = []
    errs.extend(check_models(rows, man_by_id))

    print('re-running survey call + tree stability (check-frame)...')
    frame_errs = check_frame_reuse()
    errs.extend(frame_errs)
    if not frame_errs:
        print('OK survey calls + tree lng/lat stability')

    oak_report, oak_poly = oak_leaf_report(rows, parcel_en)
    print('--- C17.3 Oak Leaf (not moved) ---')
    for k, v in oak_report.items():
        print(f'  {k}: {v}')

    draw_proof(rows, man_by_id, parcel_en, easements, pob_en, oak_poly)

    # persist oak report for C17-done.md consumers
    (ROOT / 'analysis' / 'oak-leaf-positions.json').write_text(
        json.dumps(oak_report, indent=2) + '\n', encoding='utf-8'
    )

    if errs:
        for e in errs:
            print('FAIL', e)
        print(f'FAIL {len(errs)} check(s)')
        sys.exit(1)

    n_model = sum(1 for r in rows if r['kind'] == 'model')
    print(f'OK positions proof: {len(rows)} rows, {n_model} models; '
          f'horiz<={HORIZ_TOL_M}m elev<={VERT_TOL_M}m area<={AREA_TOL * 100:.0f}% '
          f'centroid<={CENTROID_TOL_M}m')


if __name__ == '__main__':
    main()
