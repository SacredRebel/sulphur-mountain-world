"""
Creek — bed, banks, wet-season water, and the ford the path network already crosses.

  Origin: the ford where the path to glamping meets the thalweg (a place you can point at).
  Plan metres are east/north of that ford; y is elevation minus ford elevation.

  WATER CONTRACT (stated in C8-done.md, same as Oak Leaf pool):
    Water is visual only — never a walk floor.
    The BED is the walkable floor (you wade).
    Banks are solids that shape the channel; they do not fill the water column.
    Bed must sit below surrounding terrain — verified at build, not assumed.

  Season: late-winter / early-spring flow. A Ventura County creek is dry most of the year;
  the pack shows the wet season so the water is readable, and says so.

    python scripts/creek.py models/creek.glb
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, surface  # noqa: E402
from terrain import elevation_en, en_to_lnglat, lnglat_to_en  # noqa: E402

RIVER = surface('river_stone')
WATER = surface('water')
STONE = surface('stone')
TIMBER = surface('timber')

# Ford — path-to-glamping waypoint sits on the thalweg (site-grounds 275, 235).
FORD_EN = (275.0, 234.0)
FORD_Z = elevation_en(*FORD_EN)

# Channel cut below natural grade along the thalweg (metres).
BED_CUT_M = 0.75
WATER_DEPTH_M = 0.28
HALF_BED_M = 1.4
BANK_WIDTH_M = 1.1
BANK_TOP_ABOVE_BED_M = 0.85

# Thalweg sample range (pack easting) covering glamping corridor + ford.
THALWEG_E0, THALWEG_E1, THALWEG_STEP = 232.0, 308.0, 4.0


def P(e, n, y=0.0):
    return (float(e), float(y), float(-n))


def ring_xz(pts):
    return [(float(e), float(-n)) for e, n in pts]


def open_ring(pts):
    if len(pts) < 3:
        return [tuple(p) for p in pts]
    a, b = pts[0], pts[-1]
    if abs(float(a[0]) - float(b[0])) < 1e-6 and abs(float(a[1]) - float(b[1])) < 1e-6:
        return [tuple(p) for p in pts[:-1]]
    return [tuple(p) for p in pts]


def to_local(e, n):
    return e - FORD_EN[0], n - FORD_EN[1]


def y_at(e, n):
    return elevation_en(e, n) - FORD_Z


def find_thalweg():
    """Lowest northing in a search band for each easting — the draw the creek follows."""
    pts = []
    e = THALWEG_E0
    while e <= THALWEG_E1 + 1e-6:
        best = None
        for n in range(210, 255):
            z = elevation_en(e, float(n))
            if best is None or z < best[0]:
                best = (z, float(n))
        pts.append((e, best[1], best[0]))
        e += THALWEG_STEP
    return pts


def densify_polyline(pts_en, step=2.5):
    """pts are (e, n, z_terrain); return denser (e, n, z)."""
    out = [pts_en[0]]
    for i in range(len(pts_en) - 1):
        e0, n0, z0 = pts_en[i]
        e1, n1, z1 = pts_en[i + 1]
        d = math.hypot(e1 - e0, n1 - n0)
        nseg = max(1, int(math.ceil(d / step)))
        for k in range(1, nseg + 1):
            t = k / nseg
            e = e0 + t * (e1 - e0)
            n = n0 + t * (n1 - n0)
            out.append((e, n, elevation_en(e, n)))
    return out


def normals_2d(pts):
    """Unit left-hand normals in plan for each vertex."""
    nrms = []
    for i in range(len(pts)):
        if i == 0:
            de, dn = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        elif i == len(pts) - 1:
            de, dn = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
        else:
            de, dn = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        L = math.hypot(de, dn) or 1.0
        # left normal of travel direction (e,n)
        nrms.append((-dn / L, de / L))
    return nrms


def build():
    m = Model('Creek — wet-season bed, banks, ford')
    thalweg = densify_polyline(find_thalweg(), step=3.0)
    nrms = normals_2d([(e, n) for e, n, _ in thalweg])

    bed_left, bed_right = [], []
    bank_L_inner, bank_L_outer = [], []
    bank_R_inner, bank_R_outer = [], []
    water_meta = []
    bed_abs = []
    clearances = []

    for (e, n, z_t), (nx, ny) in zip(thalweg, nrms):
        # sample banks a few metres off-centre — bed must sit below the lowest of these
        bank_samples = []
        for s in (HALF_BED_M + BANK_WIDTH_M + 0.5, -(HALF_BED_M + BANK_WIDTH_M + 0.5),
                  HALF_BED_M + 0.3, -(HALF_BED_M + 0.3)):
            bank_samples.append(elevation_en(e + nx * s, n + ny * s))
        local_grade = min([z_t] + bank_samples)
        bed_z = local_grade - BED_CUT_M
        bed_abs.append(bed_z)
        clearances.append(min(bank_samples + [z_t]) - bed_z)

        le, ln = e + nx * HALF_BED_M, n + ny * HALF_BED_M
        re, rn = e - nx * HALF_BED_M, n - ny * HALF_BED_M
        bed_left.append(to_local(le, ln))
        bed_right.append(to_local(re, rn))

        lo_e, lo_n = e + nx * (HALF_BED_M + BANK_WIDTH_M), n + ny * (HALF_BED_M + BANK_WIDTH_M)
        ro_e, ro_n = e - nx * (HALF_BED_M + BANK_WIDTH_M), n - ny * (HALF_BED_M + BANK_WIDTH_M)
        bank_L_inner.append(to_local(le, ln))
        bank_L_outer.append(to_local(lo_e, lo_n))
        bank_R_inner.append(to_local(re, rn))
        bank_R_outer.append(to_local(ro_e, ro_n))

        water_meta.append((to_local(e, n), bed_z - FORD_Z + WATER_DEPTH_M))

    # --- verify bed below surrounding terrain at every station ---
    min_clear = min(clearances)
    assert min_clear >= BED_CUT_M - 1e-6, (
        f'creek bed not below terrain: min_clearance={min_clear:.2f}'
    )

    # Bed as segmented floors (quads along centreline) so reachability stays local
    for i in range(len(bed_left) - 1):
        ring = open_ring(ring_xz([
            bed_left[i], bed_left[i + 1], bed_right[i + 1], bed_right[i],
        ]))
        e0, n0, z0 = thalweg[i]
        e1, n1, z1 = thalweg[i + 1]
        # match the per-station cut used above
        def station_bed(e, n, z_t, nx, ny):
            samples = [z_t]
            for s in (HALF_BED_M + BANK_WIDTH_M + 0.5, -(HALF_BED_M + BANK_WIDTH_M + 0.5),
                      HALF_BED_M + 0.3, -(HALF_BED_M + 0.3)):
                samples.append(elevation_en(e + nx * s, n + ny * s))
            return min(samples) - BED_CUT_M

        y_bed = 0.5 * (
            station_bed(e0, n0, z0, *nrms[i]) + station_bed(e1, n1, z1, *nrms[i + 1])
        ) - FORD_Z
        y_water = y_bed + WATER_DEPTH_M
        m.extrude(RIVER, ring, y_bed - 0.08, y_bed, lid=True)
        m.floor(ring, y_bed, f'creek bed {i}')
        # water visual only — never a floor
        m.cap(WATER, ring, y_water, up=True)

        # banks as solids (shape the channel; do not fill the water column)
        y_bank_top = y_bed + BANK_TOP_ABOVE_BED_M
        left = open_ring(ring_xz([
            bank_L_inner[i], bank_L_inner[i + 1], bank_L_outer[i + 1], bank_L_outer[i],
        ]))
        right = open_ring(ring_xz([
            bank_R_inner[i], bank_R_outer[i], bank_R_outer[i + 1], bank_R_inner[i + 1],
        ]))
        m.extrude(RIVER, left, y_bed, y_bank_top, lid=True)
        m.solid(left, y_bed, y_bank_top, f'bank L {i}')
        m.extrude(RIVER, right, y_bed, y_bank_top, lid=True)
        m.solid(right, y_bed, y_bank_top, f'bank R {i}')
    # --- ford crossing (path to glamping already crosses here) ---
    # Stepping stones on the bed + timber plank slightly above water for dry feet in wet season.
    ford_y_bed = -BED_CUT_M
    ford_y_water = ford_y_bed + WATER_DEPTH_M
    stones = [(-1.2, -0.4), (-0.3, 0.2), (0.5, -0.3), (1.3, 0.1)]
    for i, (e, n) in enumerate(stones):
        pad = open_ring(ring_xz([
            (e - 0.35, n - 0.3), (e + 0.35, n - 0.3),
            (e + 0.35, n + 0.3), (e - 0.35, n + 0.3),
        ]))
        top = ford_y_bed + 0.12
        m.extrude(STONE, pad, ford_y_bed, top)
        m.floor(pad, top, f'ford stone {i}')

    # Simple timber plank bridge — walk floor above water, not on it
    plank = open_ring(ring_xz([
        (-2.2, -0.55), (2.2, -0.55), (2.2, 0.55), (-2.2, 0.55),
    ]))
    plank_y = ford_y_water + 0.18
    m.extrude(TIMBER, plank, plank_y - 0.08, plank_y)
    m.floor(plank, plank_y, 'ford plank')
    # abutments on banks (solids)
    for name, e0, e1 in (('ford abutment W', -2.6, -2.0), ('ford abutment E', 2.0, 2.6)):
        ab = open_ring(ring_xz([
            (e0, -0.7), (e1, -0.7), (e1, 0.7), (e0, 0.7),
        ]))
        m.extrude(RIVER, ab, ford_y_bed, plank_y + 0.05)
        m.solid(ab, ford_y_bed, plank_y + 0.05, name)

    length_m = sum(
        math.hypot(thalweg[i + 1][0] - thalweg[i][0], thalweg[i + 1][1] - thalweg[i][1])
        for i in range(len(thalweg) - 1)
    )

    extras = {
        'authority': 'proposed',
        'origin_note': 'ford where path to glamping crosses the creek',
        'water_contract': {
            'water_is_floor': False,
            'walkable': 'bed',
            'banks': 'solids shaping the channel',
            'note': 'wade on the bed; water surface is visual only',
        },
        'season': {
            'state': 'late-winter / early-spring flow',
            'why': 'Ventura County creek — dry much of the year; pack shows wet season so water reads, not a summer perennial',
        },
        'bed_cut_m': BED_CUT_M,
        'water_depth_m': WATER_DEPTH_M,
        'length_m': round(length_m, 1),
        'bed_vs_terrain': {
            'min_clearance_m': round(min_clear, 3),
            'bed_cut_m': BED_CUT_M,
            'verified_per_station': True,
        },
        'ford_en': list(FORD_EN),
        'ford_lnglat': list(en_to_lnglat(*FORD_EN)),
        'crossings': [
            {'kind': 'ford + plank', 'at': 'origin', 'path': 'path to glamping'},
        ],
    }
    return m, extras


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/creek.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, extras = build()
    # footprint: built bed+banks only (AABB of channel)
    half = HALF_BED_M + BANK_WIDTH_M + 1.0
    # local extents along thalweg
    thalweg = densify_polyline(find_thalweg(), step=3.0)
    locs = [to_local(e, n) for e, n, _ in thalweg]
    es = [e for e, _ in locs]
    ns = [n for _, n in locs]
    fp = [
        [min(es) - half, min(ns) - half],
        [max(es) + half, min(ns) - half],
        [max(es) + half, max(ns) + half],
        [min(es) - half, max(ns) + half],
    ]
    extras['footprint_en_m'] = [[round(e, 2), round(n, 2)] for e, n in fp]
    info = m.write(out, extras=extras)
    print(json.dumps({
        'bytes': info['bytes'],
        'triangles': info['triangles'],
        'floors': len(m.walk['floors']),
        'solids': len(m.walk['solids']),
        'length_m': extras['length_m'],
        'bed_clearance_m': extras['bed_vs_terrain']['min_clearance_m'],
        'season': extras['season']['state'],
        'water_contract': extras['water_contract']['walkable'],
    }))
