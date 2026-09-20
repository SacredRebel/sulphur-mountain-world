"""
Site grounds — drive, parking, and the path network that joins the six structures.

  Origin: pack spawn (the arrival point someone can point at). Plan metres are pack east/north
  relative to spawn; y is elevation minus spawn elevation so the model sits on the terrain.

  Drive: follows the surveyed 16 ft access easement up from the road, then to the gate parking
  and the Oak Leaf court. Grade and radius are vehicle limits, not walker limits.
  Paths: walkable links to barn, dome, glamping, retreat, ag hub, and the Oak Leaf court.

  Movement contract (enforced by scripts/check-paths.py):
    walk slope ≤ 1.2 (~50°) — engine limit
    building riser ≤ 0.18 m (default 0.17); tread ~0.29 m; Blondel 2R+T ≈ 0.63
    engine step backstop ≤ 0.55 m — must never be the binding limit
    ramps for long climbs ≤ 8%; human stairs for short climbs
    drive grade ≤ DRIVE abs grade, radius ≥ DRIVE_MIN_RADIUS_M

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
STONE = surface('stone')

PACK = json.loads((Path(__file__).resolve().parents[1] / 'pack.json').read_text(encoding='utf-8'))
SPAWN_LL = (PACK['spawn']['lng'], PACK['spawn']['lat'])
SPAWN_EN = lnglat_to_en(*SPAWN_LL)
SPAWN_Z = elevation_en(*SPAWN_EN)

PARAMS = {
    'seed': 5,
    'origin': {'lng': SPAWN_LL[0], 'lat': SPAWN_LL[1], 'note': 'pack spawn — arrival'},
    'walk': {
        'max_slope': 1.2,           # engine avatar limit
        'ramp_grade': 0.08,         # pleasant walking ramp — no steps needed
        'sample_m': 4.0,            # so ramp Δz per slab ≤ 0.18 at 8%
        'width_m': 1.6,
        'engine_step_m': 0.55,      # backstop only
    },
    'stair': {
        'riser_m': 0.17,            # human default (150–180)
        'max_riser_m': 0.18,        # building check — fails above this
        'tread_m': 0.29,            # 280–300
        'landing_every': 14,        # 12–16
        'landing_m': 1.2,           # min 1.1 m
        'short_rise_m': 4.0,        # climbs above this → prefer ramp/switchback
    },
    'drive': {
        'max_grade': 0.15,
        'abs_grade': 0.20,
        'min_radius_m': 7.5,
        'width_m': 3.6,
        'sample_m': 5.0,
    },
    'slab_thick': 0.12,
    'retain_below_m': 1.0,
}

COURT_Z = 422.4

# Accumulated while building — reported in extras / C6-done
STAIR_STATS = {
    'risers': [],           # each riser height
    'flights': [],          # {name, n_risers, mode}
    'longest_run': 0,       # consecutive risers without a landing
}


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


def enforce_max_grade(centre, max_grade):
    """Re-clamp centreline grades after start/end elevation forcing."""
    if len(centre) < 2:
        return centre
    z_start = centre[0][2]
    z_end = centre[-1][2]
    out = [list(p) for p in centre]
    cap = max_grade * (1.0 - 1e-6)
    for i in range(1, len(out)):
        run = dist(out[i - 1][:2], out[i][:2])
        if run < 1e-6:
            continue
        max_dz = run * cap
        lo, hi = out[i - 1][2] - max_dz, out[i - 1][2] + max_dz
        out[i][2] = min(max(out[i][2], lo), hi)
    for i in range(len(out) - 2, -1, -1):
        run = dist(out[i][:2], out[i + 1][:2])
        if run < 1e-6:
            continue
        max_dz = run * cap
        lo, hi = out[i + 1][2] - max_dz, out[i + 1][2] + max_dz
        out[i][2] = min(max(out[i][2], lo), hi)
    out[0][2] = z_start
    out[-1][2] = z_end
    for i in range(1, len(out)):
        run = dist(out[i - 1][:2], out[i][:2])
        if run < 1e-6:
            continue
        max_dz = run * cap
        lo, hi = out[i - 1][2] - max_dz, out[i - 1][2] + max_dz
        out[i][2] = min(max(out[i][2], lo), hi)
    out[-1][2] = z_end
    return [(e, n, z) for e, n, z in out]


def path_length(pts):
    return sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def switchback_plan(a, b, rise, max_grade, lane=6):
    """
    Zig-zag plan from a→b so |rise| / horizontal length ≤ max_grade.
    Inserts perpendicular offsets when the direct run is too short.
    """
    de = b[0] - a[0]
    dn = b[1] - a[1]
    direct = math.hypot(de, dn)
    if direct < 1e-6:
        return [a, b]
    min_len = abs(rise) / max_grade if max_grade > 1e-9 else direct
    if direct >= min_len - 0.5:
        return [a, b]
    ue, un = de / direct, dn / direct
    pe, pn = -un, ue
    extra = min_len - direct
    n_zigs = max(1, int(math.ceil(extra / (2 * lane))))
    pts = [a]
    for i in range(n_zigs):
        t = (i + 1) / (n_zigs + 1)
        mid_e = a[0] + de * t
        mid_n = a[1] + dn * t
        sign = 1 if i % 2 == 0 else -1
        pts.append((mid_e + pe * lane * sign, mid_n + pn * lane * sign))
    pts.append(b)
    return pts


def expand_switchbacks(waypoints, elev_fn, max_grade, start_z=None, end_z=None, lane=6):
    """Insert switchback legs on each span whose terrain rise exceeds grade cap."""
    if len(waypoints) < 2:
        return list(waypoints)
    out = [waypoints[0]]
    for i in range(len(waypoints) - 1):
        a, b = waypoints[i], waypoints[i + 1]
        za = start_z if i == 0 and start_z is not None else elev_fn(a[0], a[1])
        zb = end_z if i == len(waypoints) - 2 and end_z is not None else elev_fn(b[0], b[1])
        seg = switchback_plan(a, b, zb - za, max_grade, lane)
        out.extend(seg[1:])
    return out


def emit_human_stairs(m, mat, name, e0, n0, e1, n1, z0, z1, width, flight_name=None):
    """Human stair flight: riser ~0.17, tread ~0.29, Blondel 2R+T≈0.63, landings."""
    riser_target = PARAMS['stair']['riser_m']
    max_riser = PARAMS['stair']['max_riser_m']
    tread_target = PARAMS['stair']['tread_m']
    landing_every = PARAMS['stair']['landing_every']
    landing_len = PARAMS['stair']['landing_m']
    blondel = 0.63
    thick = PARAMS['slab_thick']

    rise = z1 - z0
    n_risers = max(1, int(math.ceil(abs(rise) / riser_target - 1e-9)))
    while abs(rise) / n_risers > max_riser + 1e-9:
        n_risers += 1
    riser = rise / n_risers

    de, dn = e1 - e0, n1 - n0
    horiz = math.hypot(de, dn)
    if horiz < 1e-6:
        de, dn, horiz = 1.0, 0.0, 1.0
    ue, un = de / horiz, dn / horiz
    pe, pn = -un, ue
    half = width / 2
    tread = max(0.25, min(tread_target, blondel - 2 * abs(riser)))
    tread = max(tread, tread_target * 0.85)

    flight_name = flight_name or name
    pos_e, pos_n, z = e0, n0, z0
    run_since_landing = 0
    step_k = 0

    def slab_ring(ea, na, eb, nb):
        return [
            (ea + pe * half, na + pn * half),
            (eb + pe * half, nb + pn * half),
            (eb - pe * half, nb - pn * half),
            (ea - pe * half, na - pn * half),
        ]

    def emit_slab(ea, na, eb, nb, z_top, label):
        nonlocal step_k
        le = [to_local(e, n) for e, n in slab_ring(ea, na, eb, nb)]
        xz = open_ring(ring_xz(le))
        y = z_top - SPAWN_Z
        m.extrude(mat, xz, y - thick, y)
        m.floor(xz, y, label)
        step_k += 1

    def emit_landing(e, n, z_top):
        nonlocal run_since_landing, pos_e, pos_n
        STAIR_STATS['longest_run'] = max(STAIR_STATS['longest_run'], run_since_landing)
        run_since_landing = 0
        le = landing_len
        emit_slab(e - ue * le * 0.5, n - un * le * 0.5,
                  e + ue * le * 0.5, n + un * le * 0.5, z_top, f'{name} landing {step_k}')
        pos_e, pos_n = e + ue * le * 0.5, n + un * le * 0.5

    for r in range(n_risers):
        if run_since_landing >= landing_every:
            emit_landing(pos_e, pos_n, z)
        z += riser
        eb, nb = pos_e + ue * tread, pos_n + un * tread
        emit_slab(pos_e, pos_n, eb, nb, z, f'{name} step {step_k + 1}')
        STAIR_STATS['risers'].append(abs(riser))
        run_since_landing += 1
        pos_e, pos_n = eb, nb

    STAIR_STATS['longest_run'] = max(STAIR_STATS['longest_run'], run_since_landing)
    STAIR_STATS['flights'].append({'name': flight_name, 'n_risers': n_risers, 'mode': 'stair'})
    return pos_e, pos_n, z1


def emit_ribbon(m, mat, name, centre, width, kind, mode='ramp'):
    """Flat slabs along centre; ramp Δz≤0.18, drive Δz≤0.55, stair = one human flight."""
    if mode == 'stair' and len(centre) >= 2:
        e0, n0, z0 = centre[0]
        e1, n1, z1 = centre[-1]
        emit_human_stairs(m, mat, name, e0, n0, e1, n1, z0, z1, width, flight_name=name)
        return

    if kind == 'drive':
        max_dz = PARAMS['walk']['engine_step_m']
    else:
        max_dz = PARAMS['stair']['max_riser_m']

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
        dz = z1 - z0
        if abs(dz) > max_dz + 1e-6:
            n_div = max(1, int(math.ceil(abs(dz) / max_dz)))
            for s in range(n_div):
                t0, t1 = s / n_div, (s + 1) / n_div
                zb = z0 + dz * t1
                slab(e0 + de * t0, n0 + dn * t0, e0 + de * t1, n0 + dn * t1, zb)
            continue
        slab(e0, n0, e1, n1, z1)


def force_end_elev(centre, z_end, flat_m=14.0, max_grade=0.08):
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


def force_start_elev(centre, z_start, flat_m=8.0, max_grade=0.08):
    """First flat_m metres sit at z_start; depart at max_grade."""
    if len(centre) < 2:
        return centre
    out = [list(p) for p in centre]
    out[0][2] = z_start
    acc = 0.0
    apron_end = 0
    for i in range(1, len(out)):
        out[i][2] = z_start
        apron_end = i
        acc += dist(out[i - 1], out[i])
        if acc >= flat_m:
            break
    for i in range(apron_end + 1, len(out)):
        run = dist(out[i - 1], out[i])
        max_dz = run * max_grade
        lo, hi = out[i - 1][2] - max_dz, out[i - 1][2] + max_dz
        out[i][2] = min(max(out[i][2], lo), hi)
    return [(e, n, z) for e, n, z in out]


def linear_z_centre(plan, z0, z1):
    total = path_length(plan)
    out = []
    acc = 0.0
    for i, (e, n) in enumerate(plan):
        if total > 1e-6:
            t = acc / total
        else:
            t = 0.0 if i == 0 else 1.0
        out.append((e, n, z0 + (z1 - z0) * t))
        if i < len(plan) - 1:
            acc += dist(plan[i], plan[i + 1])
    return out


def emit_path(m, mat, name, waypoints, width, kind, records, elev_overrides=None,
              end_z=None, start_z=None, mode=None):
    step = PARAMS['drive']['sample_m'] if kind == 'drive' else PARAMS['walk']['sample_m']

    def elev_fn(e, n):
        if elev_overrides:
            for (oe, on), z in elev_overrides.items():
                d = math.hypot(e - oe, n - on)
                if d < 12.0:
                    t = 1.0 - d / 12.0
                    return elevation_en(e, n) * (1 - t) + z * t
        return elevation_en(e, n)

    if kind == 'drive':
        grade_cap = PARAMS['drive']['abs_grade'] - 0.01
        plan = densify(waypoints, step)
        centre = profile_along(plan, elev_fn, grade_cap)
        if start_z is not None:
            centre = force_start_elev(centre, start_z)
        if end_z is not None:
            centre = force_end_elev(centre, end_z, flat_m=35.0 if end_z == COURT_Z else 14.0)
        elif elev_overrides and centre:
            e, n, _ = centre[-1]
            for (oe, on), z in elev_overrides.items():
                if math.hypot(e - oe, n - on) < 12.0:
                    centre = force_end_elev(centre, z, flat_m=35.0 if z == COURT_Z else 14.0)
        path_kind = 'drive'
        ribbon_mode = 'ramp'
    else:
        walk_mode = mode or 'auto'
        ramp_grade = PARAMS['walk']['ramp_grade'] * 0.9625  # ~7.7% — stays under 8% check
        if walk_mode == 'auto':
            za = start_z if start_z is not None else elev_fn(waypoints[0][0], waypoints[0][1])
            zb = end_z if end_z is not None else elev_fn(waypoints[-1][0], waypoints[-1][1])
            walk_mode = 'stair' if abs(zb - za) <= PARAMS['stair']['short_rise_m'] else 'ramp'

        if walk_mode == 'stair':
            plan = densify(waypoints, step)
            z0 = start_z if start_z is not None else elev_fn(plan[0][0], plan[0][1])
            z1 = end_z if end_z is not None else elev_fn(plan[-1][0], plan[-1][1])
            centre = linear_z_centre(plan, z0, z1)
            path_kind = 'stair'
            ribbon_mode = 'stair'
        else:
            expanded = expand_switchbacks(
                waypoints, elev_fn, ramp_grade, start_z=start_z, end_z=end_z)
            plan = densify(expanded, step)
            centre = profile_along(plan, elev_fn, ramp_grade)
            if start_z is not None:
                centre = force_start_elev(centre, start_z, flat_m=10.0)
            flat_m = 35.0 if end_z == COURT_Z else 14.0
            if end_z is not None:
                centre = force_end_elev(centre, end_z, flat_m=flat_m)
            elif elev_overrides and centre:
                e, n, _ = centre[-1]
                for (oe, on), z in elev_overrides.items():
                    if math.hypot(e - oe, n - on) < 12.0:
                        centre = force_end_elev(centre, z)
            centre = enforce_max_grade(centre, ramp_grade)
            path_kind = 'ramp'
            ribbon_mode = 'ramp'

    length = path_length(centre)
    records.append({
        'name': name,
        'kind': path_kind,
        'mode': ribbon_mode,
        'width_m': width,
        'centreline_en': [[round(e, 2), round(n, 2), round(z, 3)] for e, n, z in centre],
        'length_m': round(length, 2),
    })
    emit_ribbon(m, mat, name, centre, width, kind, mode=ribbon_mode)
    return centre[-1] if centre else None


def rect_pad(m, mat, name, e0, n0, e1, n1, z_abs):
    le = [to_local(e, n) for e, n in ((e0, n0), (e1, n0), (e1, n1), (e0, n1))]
    xz = open_ring(ring_xz(le))
    y = z_abs - SPAWN_Z
    m.extrude(mat, xz, y - PARAMS['slab_thick'], y)
    m.floor(xz, y, name)


def naive_failures():
    max_ramp = PARAMS['walk']['ramp_grade']
    max_riser = PARAMS['stair']['max_riser_m']
    max_drive = PARAMS['drive']['abs_grade']
    failed = 0
    details = []

    def check_line(a_en, b_en, max_grade, label, sample, also_riser=False):
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
            elif also_riser and rise > max_riser + 1e-9:
                failed += 1
                details.append(f'{label} riser {rise:.2f}>{max_riser} over {run:.1f}m')

    pairs = [
        ('spawn', 'barn'), ('barn', 'dome'), ('dome', 'glamping'),
        ('glamping', 'retreat'), ('spawn', 'ag'), ('barn', 'ag'),
        ('spawn', 'oak'), ('oak', 'court'),
    ]
    for a, b in pairs:
        check_line(ANCHORS[a], ANCHORS[b], max_ramp, f'walk {a}->{b}',
                   PARAMS['walk']['sample_m'], also_riser=True)

    check_line((160.0, 223.0), ANCHORS['barn'], max_drive, 'drive entry->barn', 4.0)
    check_line(ANCHORS['barn'], ANCHORS['court'], max_drive, 'drive barn->court', 4.0)
    return failed, details


def stair_stats_summary():
    risers = STAIR_STATS['risers']
    return {
        'total_risers': len(risers),
        'riser_min': round(min(risers), 3) if risers else 0.0,
        'riser_max': round(max(risers), 3) if risers else 0.0,
        'longest_run_without_landing': STAIR_STATS['longest_run'],
        'flights': list(STAIR_STATS['flights']),
    }


def build():
    global STAIR_STATS
    STAIR_STATS = {'risers': [], 'flights': [], 'longest_run': 0}
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

    rect_pad(m, GRAVEL, 'gate parking', be - 8.0, bn - 14.0, be + 8.0, bn - 4.0,
             elevation_en(be, bn - 9.0))
    rect_pad(m, GRAVEL, 'oak court parking',
             court_e - 10.0, court_n - 4.0, court_e + 10.0, court_n + 4.0, COURT_Z)

    w = PARAMS['walk']['width_m']
    emit_path(m, GRAVEL, 'path to barn',
              [SPAWN_EN, (270.0, 265.0), (260.0, 280.0), (be, bn - 2.0)],
              w, 'walk', records, start_z=SPAWN_Z, mode='ramp')
    emit_path(m, GRAVEL, 'path to dome',
              [SPAWN_EN, (265.0, 255.0), ANCHORS['dome']], w, 'walk', records,
              start_z=SPAWN_Z, mode='ramp')
    g_end = emit_path(m, GRAVEL, 'path to glamping',
                      [SPAWN_EN, (275.0, 235.0), ANCHORS['glamping']],
                      w, 'walk', records, start_z=SPAWN_Z, mode='ramp')
    retreat_wp = [ANCHORS['glamping'], (295.0, 215.0), (320.0, 202.0), (340.0, 195.0), ANCHORS['retreat']]
    if g_end:
        retreat_wp[0] = (g_end[0], g_end[1])
    emit_path(m, GRAVEL, 'path to retreat', retreat_wp,
              w, 'walk', records, start_z=(g_end[2] if g_end else None), mode='ramp')
    emit_path(m, GRAVEL, 'path to ag',
              [(be, bn - 2.0), (280.0, 305.0), (300.0, 322.0), ANCHORS['ag']],
              w, 'walk', records, mode='ramp')
    emit_path(m, GRAVEL, 'path to oak',
              [(court_e, court_n + 5.5), (court_e + 1.0, court_n + 14.0), ANCHORS['oak']],
              w, 'walk', records, start_z=COURT_Z, mode='stair')
    emit_path(m, GRAVEL, 'path court link',
              [SPAWN_EN, (320.0, 260.0), (350.0, 272.0), (court_e, court_n)],
              w, 'walk', records, start_z=SPAWN_Z, end_z=COURT_Z, mode='ramp')

    se, sn = SPAWN_EN
    rect_pad(m, GRAVEL, 'arrival', se - 3.0, sn - 3.0, se + 3.0, sn + 3.0, SPAWN_Z)

    stats = stair_stats_summary()
    extras = {
        'params': PARAMS,
        'authority': 'proposal',
        'origin_note': 'pack spawn',
        'spawn_elev_m': round(SPAWN_Z, 2),
        'paths': records,
        'stair_stats': stats,
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
    return m, extras, failed_before, stats


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/site-grounds.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, extras, failed_before, stats = build()
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
        'total_risers': stats['total_risers'],
        'riser_min': stats['riser_min'],
        'riser_max': stats['riser_max'],
        'longest_run_without_landing': stats['longest_run_without_landing'],
        'flights': stats['flights'],
    }))
