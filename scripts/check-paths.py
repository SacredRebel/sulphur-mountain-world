"""
Path movement-contract checker.

  Asserts, for every path centreline in a grounds GLB extras.paths and every adjacent
  floor-to-floor joint in extras.walk:

    · building riser: adjacent floor Δtop ≤ max_riser_m (default 0.18)
    · engine backstop: adjacent floor Δtop ≤ engine_step_m (default 0.55)
    · ramp centreline: |Δy| / run ≤ ramp_grade (default 0.08)
    · stair centreline: slope grade check skipped (human stairs)
    · drive segments: |Δy| / run ≤ drive abs grade (default 0.20)
    · drive corners: approximate radius ≥ min_radius_m (default 7.5)

  Failures print and exit non-zero.

    python scripts/check-paths.py models/site-grounds.glb
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

MAX_WALK_SLOPE = 1.2
DEFAULT_MAX_RISER = 0.18
DEFAULT_ENGINE_STEP = 0.55
DEFAULT_RAMP_GRADE = 0.08
DEFAULT_DRIVE_ABS = 0.20
DEFAULT_DRIVE_RADIUS = 7.5
TOUCH_M = 0.55


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


def extras_of(doc):
    for node in doc.get('nodes') or []:
        ex = node.get('extras') or {}
        if 'walk' in ex or 'paths' in ex:
            return ex
    for scene in doc.get('scenes') or []:
        ex = scene.get('extras') or {}
        if 'walk' in ex or 'paths' in ex:
            return ex
    raise ValueError('no extras.walk / extras.paths')


def ring_touch(a, b, tol=TOUCH_M):
    for x, z in a:
        for i in range(len(b)):
            x0, z0 = b[i]
            x1, z1 = b[(i + 1) % len(b)]
            dx, dz = x1 - x0, z1 - z0
            L2 = dx * dx + dz * dz
            if L2 < 1e-12:
                d = math.hypot(x - x0, z - z0)
            else:
                t = max(0.0, min(1.0, ((x - x0) * dx + (z - z0) * dz) / L2))
                d = math.hypot(x - (x0 + t * dx), z - (z0 + t * dz))
            if d <= tol:
                return True
    return False


def turn_radius(a, b, c):
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    cx, cy = c[0], c[1]
    abx, aby = bx - ax, by - ay
    bcx, bcy = cx - bx, cy - by
    la = math.hypot(abx, aby)
    lb = math.hypot(bcx, bcy)
    if la < 1e-6 or lb < 1e-6:
        return 1e9
    cos_t = max(-1.0, min(1.0, (abx * bcx + aby * bcy) / (la * lb)))
    turn = math.acos(cos_t)
    if turn < 1e-3:
        return 1e9
    chord = math.hypot(cx - ax, cy - ay)
    return chord / (2 * math.sin(turn / 2))


def parse_slab_name(name: str):
    if ' step ' in name:
        base, num = name.rsplit(' step ', 1)
        if num.isdigit():
            return base, ('step', int(num))
    if ' landing ' in name:
        base, num = name.rsplit(' landing ', 1)
        if num.isdigit():
            return base, ('landing', int(num))
    parts = name.rsplit(' ', 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], ('slab', int(parts[1]))
    return name, ('slab', None)


def is_drive_base(base: str) -> bool:
    return base == 'drive' or base == 'drive to court'


def stair_pair_adjacent(a_tag, b_tag) -> bool | None:
    """True if stair elements are consecutive; None if not a stair pair."""
    if not isinstance(a_tag, tuple) or not isinstance(b_tag, tuple):
        return None
    ta, na = a_tag
    tb, nb = b_tag
    if ta not in ('step', 'landing') or tb not in ('step', 'landing'):
        return None
    if ta == 'step' and tb == 'step':
        return nb == na + 1 or na == nb + 1
    if ta == 'step' and tb == 'landing':
        return na == nb
    if ta == 'landing' and tb == 'step':
        return nb == na + 1
    if ta == 'landing' and tb == 'landing':
        return False
    if ta == 'step' and tb == 'landing':
        return na == nb
    return False


def check(path: Path):
    doc = read_glb(path)
    ex = extras_of(doc)
    walk = ex.get('walk') or {}
    paths = ex.get('paths') or []
    drive_spec = ex.get('drive_spec') or {}
    abs_grade = float(drive_spec.get('abs_grade', DEFAULT_DRIVE_ABS))
    min_r = float(drive_spec.get('min_radius_m', DEFAULT_DRIVE_RADIUS))
    params = ex.get('params') or {}
    walk_p = params.get('walk') or {}
    stair_p = params.get('stair') or {}
    max_walk = float(walk_p.get('max_slope', MAX_WALK_SLOPE))
    max_riser = float(stair_p.get('max_riser_m', DEFAULT_MAX_RISER))
    engine_step = float(walk_p.get('engine_step_m', DEFAULT_ENGINE_STEP))
    ramp_grade = float(walk_p.get('ramp_grade', DEFAULT_RAMP_GRADE))

    errors = []
    stats = {
        'path_length_m': 0.0,
        'steepest_walk': 0.0,
        'steepest_ramp': 0.0,
        'steepest_drive': 0.0,
        'largest_step': 0.0,
        'largest_riser': 0.0,
        'n_path_segments': 0,
        'n_floor_joints': 0,
    }

    for p in paths:
        kind = p.get('kind', 'walk')
        cl = p.get('centreline_en') or []
        for i in range(len(cl) - 1):
            e0, n0, z0 = cl[i]
            e1, n1, z1 = cl[i + 1]
            run = math.hypot(e1 - e0, n1 - n0)
            if run < 1e-6:
                continue
            grade = abs(z1 - z0) / run
            stats['n_path_segments'] += 1
            stats['path_length_m'] += run
            if kind == 'drive':
                stats['steepest_drive'] = max(stats['steepest_drive'], grade)
                if grade > abs_grade + 1e-9:
                    errors.append(
                        f"drive '{p['name']}' seg {i}: grade {grade:.3f} > {abs_grade} "
                        f"(rise {abs(z1-z0):.2f} over {run:.1f}m)"
                    )
            elif kind == 'ramp':
                stats['steepest_ramp'] = max(stats['steepest_ramp'], grade)
                stats['steepest_walk'] = max(stats['steepest_walk'], grade)
                if grade > ramp_grade + 1e-9:
                    errors.append(
                        f"ramp '{p['name']}' seg {i}: grade {grade:.3f} > {ramp_grade} "
                        f"(rise {abs(z1-z0):.2f} over {run:.1f}m)"
                    )
            elif kind == 'stair':
                stats['steepest_walk'] = max(stats['steepest_walk'], grade)
            else:
                stats['steepest_walk'] = max(stats['steepest_walk'], grade)
                if grade > max_walk + 1e-9:
                    errors.append(
                        f"walk '{p['name']}' seg {i}: slope {grade:.3f} > {max_walk}"
                    )

        if kind == 'drive' and len(cl) >= 3:
            thin = [cl[0]]
            for pt in cl[1:]:
                if math.hypot(pt[0] - thin[-1][0], pt[1] - thin[-1][1]) >= min_r * 0.4:
                    thin.append(pt)
            if thin[-1] != cl[-1]:
                thin.append(cl[-1])
            for i in range(1, len(thin) - 1):
                a, b, c = thin[i - 1], thin[i], thin[i + 1]
                ab = (b[0] - a[0], b[1] - a[1])
                bc = (c[0] - b[0], c[1] - b[1])
                la = math.hypot(*ab)
                lb = math.hypot(*bc)
                if la < 1e-6 or lb < 1e-6:
                    continue
                cos_t = max(-1.0, min(1.0, (ab[0] * bc[0] + ab[1] * bc[1]) / (la * lb)))
                turn = math.acos(cos_t)
                if turn < math.radians(12):
                    continue
                r = turn_radius(a, b, c)
                if r < min_r - 0.05:
                    errors.append(
                        f"drive '{p['name']}' corner near ({b[0]:.0f},{b[1]:.0f}): "
                        f"radius {r:.1f}m < {min_r}m"
                    )

    floors = walk.get('floors') or []
    parsed = [(f, *parse_slab_name(f.get('name') or '')) for f in floors]
    for i, (a, a_base, a_tag) in enumerate(parsed):
        for j in range(i + 1, len(parsed)):
            b, b_base, b_tag = parsed[j]
            a_name = a.get('name') or ''
            b_name = b.get('name') or ''

            if a_base == b_base and isinstance(a_tag, tuple) and a_tag[0] == 'slab':
                a_idx, b_idx = a_tag[1], b_tag[1]
                if a_idx is not None and b_idx is not None and abs(a_idx - b_idx) != 1:
                    continue

            stair_adj = None
            if a_base == b_base:
                stair_adj = stair_pair_adjacent(a_tag, b_tag)
                if stair_adj is False:
                    continue

            if not ring_touch(a['ring'], b['ring']):
                continue
            step = abs(float(a['top']) - float(b['top']))
            stats['n_floor_joints'] += 1
            stats['largest_step'] = max(stats['largest_step'], step)
            both_drive = is_drive_base(str(a_base)) and is_drive_base(str(b_base))
            same_ribbon = a_base == b_base and isinstance(a_tag, tuple) and a_tag[0] == 'slab'
            consecutive = (
                same_ribbon and a_tag[1] is not None and b_tag[1] is not None
                and abs(a_tag[1] - b_tag[1]) == 1
            )
            check_riser = (
                not both_drive
                and (consecutive or stair_adj is True)
            )
            if check_riser:
                stats['largest_riser'] = max(stats['largest_riser'], step)
            if step > max_riser + 1e-9 and check_riser:
                errors.append(
                    f"floor joint '{a_name}' ↔ '{b_name}': "
                    f"Δtop {step:.2f}m > {max_riser}m (building riser)"
                )
            if step > engine_step + 1e-9:
                errors.append(
                    f"floor joint '{a_name}' ↔ '{b_name}': "
                    f"Δtop {step:.2f}m > {engine_step}m (engine backstop)"
                )

    stats['path_length_m'] = round(stats['path_length_m'], 1)
    stats['steepest_walk'] = round(stats['steepest_walk'], 4)
    stats['steepest_ramp'] = round(stats['steepest_ramp'], 4)
    stats['steepest_drive'] = round(stats['steepest_drive'], 4)
    stats['largest_step'] = round(stats['largest_step'], 3)
    stats['largest_riser'] = round(stats['largest_riser'], 3)
    return errors, stats


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else 'models/site-grounds.glb')
    errors, stats = check(path)
    report = {'path': str(path), 'ok': not errors, 'stats': stats, 'errors': errors}
    print(json.dumps(report, indent=2))
    sys.exit(0 if not errors else 1)


if __name__ == '__main__':
    main()
