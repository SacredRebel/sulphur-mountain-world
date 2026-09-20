"""
Site grounds — drive, parking, and the path network that joins the six structures.

  Origin: pack spawn (the arrival point someone can point at). Plan metres are pack east/north
  relative to spawn; y is elevation minus spawn elevation so the model sits on the terrain.

  Drive: follows the surveyed 16 ft access easement up from the road, then to the gate parking
  and the Oak Leaf court. Grade and radius are vehicle limits, not walker limits.
  Paths: walkable links to barn, dome, glamping, retreat, ag hub, and the Oak Leaf court.

  Movement contract (enforced by scripts/check-paths.py):
    walk slope ≤ 1.2 (~50°)
    step up ≤ 0.55 m between adjacent floors
    drive grade ≤ DRIVE_MAX_GRADE (absolute DRIVE_ABS_GRADE), radius ≥ DRIVE_MIN_RADIUS_M

    python scripts/site-grounds.py models/site-grounds.glb
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, surface  # noqa: E402
from terrain import elevation_en, lnglat_to_en  # noqa: E402

DIRT = surface('dirt')
GRAVEL = surface('gravel')
RIVER = surface('river_stone')

PACK = json.loads((Path(__file__).resolve().parents[1] / 'pack.json').read_text(encoding='utf-8'))
SPAWN_LL = (PACK['spawn']['lng'], PACK['spawn']['lat'])
SPAWN_EN = lnglat_to_en(*SPAWN_LL)
SPAWN_Z = elevation_en(*SPAWN_EN)

PARAMS = {
    'seed': 5,
    'origin': {'lng': SPAWN_LL[0], 'lat': SPAWN_LL[1], 'note': 'pack spawn — arrival'},
    'walk': {
        'max_slope': 1.2,
        'max_step_m': 0.55,
        'width_m': 1.6,
        'sample_m': 4.0,
    },
    'drive': {
        'max_grade': 0.15,
        'abs_grade': 0.20,
        'min_radius_m': 7.5,
        'width_m': 3.6,
        'sample_m': 5.0,
    },
    'slab_thick': 0.12,
    'retain_below_m': 0.55,
}

COURT_Z = 422.4  # edits.geojson oak-leaf-court flatten


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
    return e - SPAWN_EN[0], n - SPAWN_EN[1]


ANCHORS = {
    'spawn': SPAWN_EN,
    'barn': lnglat_to_en(-119.156728, 34.433082),
    'dome': lnglat_to_en(-119.156763, 34.432888),
    'glamping': lnglat_to_en(-119.15654, 34.432479),
    'retreat': lnglat_to_en(-119.155628, 34.432173),
    'ag': lnglat_to_en(-119.155982, 34.433478),
    'oak': lnglat_to_en(-119.155333, 34.433118),
    'court': lnglat_to_en(-119.155425, 34.432952),
}


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def densify(pts, step):
    out = [tuple(pts[0])]
    for i in range(len(pts) - 1):
        e0, n0 = pts[i]
        e1, n1 = pts[i + 1]
        d = math.hypot(e1 - e0, n1 - n0)
        if d < 1e-6:
            continue
        nseg = max(1, int(math.ceil(d / step)))
        for k in range(1, nseg + 1):
            t = k / nseg
            out.append((e0 + (e1 - e0) * t, n0 + (n1 - n0) * t))
    return out


def arc_points(cx, cy, r, a0_deg, a1_deg, n=10):
    """Inclusive circular arc in degrees (CCW positive)."""
    a0, a1 = math.radians(a0_deg), math.radians(a1_deg)
    # pick the short sweep
    sweep = a1 - a0
    while sweep > math.pi:
        sweep -= 2 * math.pi
    while sweep < -math.pi:
        sweep += 2 * math.pi
    return [
        (cx + r * math.cos(a0 + sweep * i / n), cy + r * math.sin(a0 + sweep * i / n))
        for i in range(n + 1)
    ]


def build_drive_plan():
    """Easement centreline with two explicit 8 m arcs (above the 7.5 m minimum)."""
    r = 8.0
    pts = [(155.0, 223.0), (218.0, 223.0)]
    # East → north into the strip
    pts.extend(arc_points(218.0, 231.0, r, -90, 0, n=10)[1:])
    pts += [(234.0, 250.0), (234.0, 275.0)]
    # North → east toward gate parking
    pts.extend(arc_points(242.0, 275.0, r, 180, 90, n=10)[1:])
    pts.append((255.0, 285.0))
    return pts


def profile_along(pts, elev_fn, max_grade):
    """
    Assign elevations along a plan polyline so successive grades ≤ max_grade,
    ending at elev_fn(last). Prefers terrain; when terrain is steeper, holds grade
    and lets the profile catch up (cut/fill) — no sharp switchbacks.
    """
    if not pts:
        return []
    zs_terrain = [elev_fn(e, n) for e, n in pts]
    out_z = [zs_terrain[0]]
    for i in range(1, len(pts)):
        run = dist(pts[i - 1], pts[i])
        target = zs_terrain[i]
        max_dz = run * max_grade
        prev = out_z[-1]
        # stay as close as possible to terrain without exceeding grade
        lo, hi = prev - max_dz, prev + max_dz
        out_z.append(min(max(target, lo), hi))
    # second pass backward so the end lands on terrain
    out_z[-1] = zs_terrain[-1]
    for i in range(len(pts) - 2, -1, -1):
        run = dist(pts[i], pts[i + 1])
        max_dz = run * max_grade
        lo, hi = out_z[i + 1] - max_dz, out_z[i + 1] + max_dz
        # also prefer terrain
        prefer = zs_terrain[i]
        out_z[i] = min(max(min(max(prefer, lo), hi), lo), hi)
    # forward again to restore start
    out_z[0] = zs_terrain[0]
    for i in range(1, len(pts)):
        run = dist(pts[i - 1], pts[i])
        max_dz = run * max_grade
        lo, hi = out_z[i - 1] - max_dz, out_z[i - 1] + max_dz
        out_z[i] = min(max(out_z[i], lo), hi)
    return [(pts[i][0], pts[i][1], out_z[i]) for i in range(len(pts))]


def emit_stairs(m, mat, name, e0, n0, e1, n1, z0, z1, width, records_append=None):
    """Straight stair flight; each riser ≤ max_step_m. First tread top = z0 + riser."""
    max_step = PARAMS['walk']['max_step_m']
    rise = z1 - z0
    n_steps = max(1, int(math.ceil(abs(rise) / max_step - 1e-9)))
    # Keep each riser ≤ max_step
    riser = rise / n_steps
    de, dn = e1 - e0, n1 - n0
    L = math.hypot(de, dn) or 1.0
    ue, un = de / L, dn / L
    pe, pn = -un, ue
    half = width / 2
    tread = max(0.40, L / n_steps)
    for s in range(n_steps):
        t0 = s * tread
        t1 = (s + 1) * tread
        ea, na = e0 + ue * t0, n0 + un * t0
        eb, nb = e0 + ue * t1, n0 + un * t1
        z = z0 + riser * (s + 1)
        ring = [
            (ea + pe * half, na + pn * half),
            (eb + pe * half, nb + pn * half),
            (eb - pe * half, nb - pn * half),
            (ea - pe * half, na - pn * half),
        ]
        le = [to_local(e, n) for e, n in ring]
        xz = open_ring(ring_xz(le))
        y = z - SPAWN_Z
        m.extrude(mat, xz, y - 0.1, y)
        m.floor(xz, y, f'{name} step {s + 1}')
    return e0 + ue * n_steps * tread, n0 + un * n_steps * tread, z1


def emit_ribbon(m, mat, name, centre, width, kind):
    """Emit flat slabs along centre [(e,n,z)...]; walk uses stairs when Δz > max_step."""
    max_step = PARAMS['walk']['max_step_m']
    thick = PARAMS['slab_thick']
    half = width / 2
    k = 0

    def slab(e0, n0, e1, n1, z_top):
        nonlocal k
        de, dn = e1 - e0, n1 - n0
        L = math.hypot(de, dn)
        if L < 0.35:
            return
        ue, un = de / L, dn / L
        pe, pn = -un, ue
        ring = [
            (e0 + pe * half, n0 + pn * half),
            (e1 + pe * half, n1 + pn * half),
            (e1 - pe * half, n1 - pn * half),
            (e0 - pe * half, n0 - pn * half),
        ]
        le = [to_local(e, n) for e, n in ring]
        xz = open_ring(ring_xz(le))
        y = z_top - SPAWN_Z
        m.extrude(mat, xz, y - thick, y)
        m.floor(xz, y, f'{name} {k}')
        for side, sign in (('L', 1), ('R', -1)):
            mid_e = 0.5 * (e0 + e1) + pe * sign * (half + 1.2)
            mid_n = 0.5 * (n0 + n1) + pn * sign * (half + 1.2)
            ground = elevation_en(mid_e, mid_n)
            drop = z_top - ground
            if drop > PARAMS['retain_below_m']:
                a = (e0 + pe * sign * half, n0 + pn * sign * half)
                b = (e1 + pe * sign * half, n1 + pn * sign * half)
                wall = [
                    a, b,
                    (b[0] + pe * sign * 0.35, b[1] + pn * sign * 0.35),
                    (a[0] + pe * sign * 0.35, a[1] + pn * sign * 0.35),
                ]
                wxz = open_ring(ring_xz([to_local(e, n) for e, n in wall]))
                base = y - drop
                m.extrude(RIVER, wxz, base, y)
                m.solid(wxz, base, y, f'{name} retain {side}{k}')
        k += 1

    for i in range(len(centre) - 1):
        e0, n0, z0 = centre[i]
        e1, n1, z1 = centre[i + 1]
        de, dn = e1 - e0, n1 - n0
        L = math.hypot(de, dn)
        if L < 0.35:
            continue
        if abs(z1 - z0) > max_step + 1e-6:
            if kind == 'walk':
                # Landing at z0 so the previous slab meets the flight within max_step
                slab(e0, n0, e0 + de * 0.15, n0 + dn * 0.15, z0)
                emit_stairs(m, mat, name, e0 + de * 0.15, n0 + dn * 0.15, e1, n1, z0, z1, width)
                k += 1
            else:
                # drive: subdivide into flat pieces with Δtop ≤ max_step (drivable terrace)
                n_div = max(1, int(math.ceil(abs(z1 - z0) / max_step)))
                for s in range(n_div):
                    t0, t1 = s / n_div, (s + 1) / n_div
                    slab(e0 + de * t0, n0 + dn * t0, e0 + de * t1, n0 + dn * t1,
                         z0 + (z1 - z0) * (t0 + t1) / 2)
            continue
        slab(e0, n0, e1, n1, 0.5 * (z0 + z1))


def force_end_elev(centre, z_end, flat_m=14.0, max_grade=0.18):
    """Last flat_m metres sit at z_end; approach ramps in at max_grade."""
    if len(centre) < 2:
        return centre
    out = [list(p) for p in centre]
    # mark flat apron from the end
    acc = 0.0
    apron_start = len(out) - 1
    for i in range(len(out) - 1, -1, -1):
        out[i][2] = z_end
        apron_start = i
        if i == 0:
            break
        acc += dist(out[i - 1], out[i])
        if acc >= flat_m:
            break
    # ramp backward from apron_start to earlier points at max_grade
    for i in range(apron_start - 1, -1, -1):
        run = dist(out[i], out[i + 1])
        max_dz = run * max_grade
        lo, hi = out[i + 1][2] - max_dz, out[i + 1][2] + max_dz
        out[i][2] = min(max(out[i][2], lo), hi)
    return [(e, n, z) for e, n, z in out]


def force_start_elev(centre, z_start, blend_m=8.0):
    if len(centre) < 2:
        return centre
    out = [list(p) for p in centre]
    out[0][2] = z_start
    acc = 0.0
    for i in range(1, len(out)):
        acc += dist(out[i - 1], out[i])
        if acc >= blend_m:
            break
        t = acc / blend_m
        out[i][2] = z_start * (1 - t) + out[i][2] * t
    return [(e, n, z) for e, n, z in out]


def emit_path(m, mat, name, waypoints, width, kind, records, elev_overrides=None,
              end_z=None, start_z=None):
    grade_cap = (PARAMS['drive']['abs_grade'] - 0.01) if kind == 'drive' else 0.18
    step = PARAMS['drive']['sample_m'] if kind == 'drive' else PARAMS['walk']['sample_m']

    def elev_fn(e, n):
        if elev_overrides:
            for (oe, on), z in elev_overrides.items():
                d = math.hypot(e - oe, n - on)
                if d < 12.0:
                    t = 1.0 - d / 12.0
                    return elevation_en(e, n) * (1 - t) + z * t
        return elevation_en(e, n)

    plan = densify(waypoints, step)
    centre = profile_along(plan, elev_fn, grade_cap)
    if start_z is not None:
        centre = force_start_elev(centre, start_z)
    if end_z is not None:
        centre = force_end_elev(centre, end_z)
    elif elev_overrides and centre:
        e, n, _ = centre[-1]
        for (oe, on), z in elev_overrides.items():
            if math.hypot(e - oe, n - on) < 12.0:
                centre = force_end_elev(centre, z)

    length = sum(dist(centre[i], centre[i + 1]) for i in range(len(centre) - 1))
    records.append({
        'name': name,
        'kind': kind,
        'width_m': width,
        'centreline_en': [[round(e, 2), round(n, 2), round(z, 2)] for e, n, z in centre],
        'length_m': round(length, 2),
    })
    emit_ribbon(m, mat, name, centre, width, kind)
    return centre[-1] if centre else None


def rect_pad(m, mat, name, e0, n0, e1, n1, z_abs):
    le = [to_local(e, n) for e, n in ((e0, n0), (e1, n0), (e1, n1), (e0, n1))]
    xz = open_ring(ring_xz(le))
    y = z_abs - SPAWN_Z
    m.extrude(mat, xz, y - PARAMS['slab_thick'], y)
    m.floor(xz, y, name)


def naive_failures():
    max_walk = PARAMS['walk']['max_slope']
    max_step = PARAMS['walk']['max_step_m']
    max_drive = PARAMS['drive']['abs_grade']
    failed = 0
    details = []

    def check_line(a_en, b_en, max_grade, label, sample, also_step=False):
        nonlocal failed
        pts = densify([a_en, b_en], sample)
        zs = [elevation_en(e, n) for e, n in pts]
        for i in range(len(pts) - 1):
            run = dist(pts[i], pts[i + 1])
            if run < 1e-6:
                continue
            rise = abs(zs[i + 1] - zs[i])
            grade = rise / run
            if grade > max_grade + 1e-9:
                failed += 1
                details.append(f'{label} grade {grade:.3f}>{max_grade} over {run:.1f}m')
            elif also_step and rise > max_step + 1e-9:
                failed += 1
                details.append(f'{label} step {rise:.2f}>{max_step} over {run:.1f}m')

    pairs = [
        ('spawn', 'barn'), ('barn', 'dome'), ('dome', 'glamping'),
        ('glamping', 'retreat'), ('spawn', 'ag'), ('barn', 'ag'),
        ('spawn', 'oak'), ('oak', 'court'),
    ]
    for a, b in pairs:
        check_line(ANCHORS[a], ANCHORS[b], max_walk, f'walk {a}->{b}',
                   PARAMS['walk']['sample_m'], also_step=True)

    check_line((160.0, 223.0), ANCHORS['barn'], max_drive, 'drive entry->barn', 4.0)
    check_line(ANCHORS['barn'], ANCHORS['court'], max_drive, 'drive barn->court', 4.0)
    return failed, details


def build():
    m = Model('Site grounds — drive, parking, paths')
    records = []
    failed_before, fail_details = naive_failures()
    court_e, court_n = ANCHORS['court']
    overrides = {(court_e, court_n): COURT_Z}
    be, bn = ANCHORS['barn']

    drive_pts = build_drive_plan()
    emit_path(m, DIRT, 'drive', drive_pts, PARAMS['drive']['width_m'], 'drive', records)

    spur = [
        (255.0, 285.0),
        (280.0, 282.0),
        (310.0, 279.0),
        (340.0, 277.5),
        (court_e, court_n),
    ]
    emit_path(m, DIRT, 'drive to court', spur, PARAMS['drive']['width_m'], 'drive', records, overrides)

    # Parking
    rect_pad(m, GRAVEL, 'gate parking', be - 8.0, bn - 14.0, be + 8.0, bn - 4.0,
             elevation_en(be, bn - 9.0))
    rect_pad(m, GRAVEL, 'oak court parking',
             court_e - 10.0, court_n - 4.0, court_e + 10.0, court_n + 4.0, COURT_Z)

    w = PARAMS['walk']['width_m']
    emit_path(m, GRAVEL, 'path to barn',
              [SPAWN_EN, (270.0, 265.0), (260.0, 280.0), (be, bn - 2.0)], w, 'walk', records)
    emit_path(m, GRAVEL, 'path to dome',
              [SPAWN_EN, (265.0, 255.0), ANCHORS['dome']], w, 'walk', records)
    g_end = emit_path(m, GRAVEL, 'path to glamping',
                      [SPAWN_EN, (275.0, 235.0), ANCHORS['glamping']], w, 'walk', records)
    emit_path(m, GRAVEL, 'path to retreat',
              [ANCHORS['glamping'], (295.0, 215.0), (320.0, 202.0), (340.0, 195.0), ANCHORS['retreat']],
              w, 'walk', records, start_z=(g_end[2] if g_end else None))
    emit_path(m, GRAVEL, 'path to ag',
              [(be, bn - 2.0), (280.0, 305.0), (300.0, 322.0), ANCHORS['ag']], w, 'walk', records)
    emit_path(m, GRAVEL, 'path to oak',
              [(court_e, court_n + 5.5), (court_e + 1.0, court_n + 14.0), ANCHORS['oak']],
              w, 'walk', records, start_z=COURT_Z)
    emit_path(m, GRAVEL, 'path court link',
              [SPAWN_EN, (320.0, 260.0), (350.0, 272.0), (court_e, court_n)],
              w, 'walk', records, end_z=COURT_Z)

    se, sn = SPAWN_EN
    rect_pad(m, GRAVEL, 'arrival', se - 3.0, sn - 3.0, se + 3.0, sn + 3.0, SPAWN_Z)

    extras = {
        'params': PARAMS,
        'authority': 'proposal',
        'origin_note': 'pack spawn',
        'spawn_elev_m': round(SPAWN_Z, 2),
        'paths': records,
        'failed_segments_before_fix': failed_before,
        'failed_segment_notes': fail_details[:40],
        'drive_spec': {
            'max_grade': PARAMS['drive']['max_grade'],
            'abs_grade': PARAMS['drive']['abs_grade'],
            'min_radius_m': PARAMS['drive']['min_radius_m'],
            'width_m': PARAMS['drive']['width_m'],
            'note': '15% preferred vehicle grade, 20% absolute on a short pitch; 7.5 m minimum outside turning radius',
        },
    }
    return m, extras, failed_before


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/site-grounds.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, extras, failed_before = build()
    info = m.write(out, extras=extras)
    total_len = sum(p['length_m'] for p in extras['paths'])
    print(json.dumps({
        'bytes': info['bytes'],
        'triangles': info['triangles'],
        'floors': len(m.walk['floors']),
        'solids': len(m.walk['solids']),
        'path_length_m': round(total_len, 1),
        'failed_before_fix': failed_before,
        'n_paths': len(extras['paths']),
    }))
