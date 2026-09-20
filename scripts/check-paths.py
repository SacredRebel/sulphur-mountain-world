"""
Path movement-contract checker.

  Asserts, for every path centreline in a grounds GLB extras.paths and every adjacent
  floor-to-floor joint in extras.walk:

    · walk segments: |Δy| / run ≤ 1.2  (~50°)
    · drive segments: |Δy| / run ≤ drive abs grade (default 0.20)
    · drive corners: approximate radius ≥ min_radius_m (default 7.5)
    · adjacent floors whose rings nearly touch: |Δtop| ≤ 0.55 m
      (a larger jump is a WALL — needs steps, not scenery)

  Failures print and exit non-zero. Paths are long and thin; one bad 4 m stretch is
  invisible in a screenshot and fatal to anyone walking it.

    python scripts/check-paths.py models/site-grounds.glb
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

MAX_WALK_SLOPE = 1.2
MAX_STEP_M = 0.55
DEFAULT_DRIVE_ABS = 0.20
DEFAULT_DRIVE_RADIUS = 7.5
TOUCH_M = 0.55  # edge-to-edge — only true meetings, not near-miss parallels


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


def ring_centroid(ring):
    return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))


def ring_touch(a, b, tol=TOUCH_M):
    """True if any vertex of a is within tol of any edge of b (or vice versa) — cheap."""
    for x, z in a:
        for i in range(len(b)):
            x0, z0 = b[i]
            x1, z1 = b[(i + 1) % len(b)]
            # point–segment distance
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
    """'path to barn 12' → ('path to barn', 12); 'arrival' → ('arrival', None)."""
    parts = name.rsplit(' ', 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1])
    if name.startswith('path ') and ' step ' in name:
        base = name.split(' step ')[0]
        return base, None  # stairs handled as sequential by proximity
    return name, None


def check(path: Path):
    doc = read_glb(path)
    ex = extras_of(doc)
    walk = ex.get('walk') or {}
    paths = ex.get('paths') or []
    drive_spec = ex.get('drive_spec') or {}
    abs_grade = float(drive_spec.get('abs_grade', DEFAULT_DRIVE_ABS))
    min_r = float(drive_spec.get('min_radius_m', DEFAULT_DRIVE_RADIUS))
    params = ex.get('params') or {}
    max_walk = float((params.get('walk') or {}).get('max_slope', MAX_WALK_SLOPE))
    max_step = float((params.get('walk') or {}).get('max_step_m', MAX_STEP_M))

    errors = []
    stats = {
        'path_length_m': 0.0,
        'steepest_walk': 0.0,
        'steepest_drive': 0.0,
        'largest_step': 0.0,
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
            else:
                stats['steepest_walk'] = max(stats['steepest_walk'], grade)
                if grade > max_walk + 1e-9:
                    errors.append(
                        f"walk '{p['name']}' seg {i}: slope {grade:.3f} > {max_walk}"
                    )
        if kind == 'drive' and len(cl) >= 3:
            # Evaluate turns on a thinned polyline so densify chords do not fake sharp corners
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
    for i, (a, a_base, a_idx) in enumerate(parsed):
        for j in range(i + 1, len(parsed)):
            b, b_base, b_idx = parsed[j]
            # Same ribbon: only consecutive slab indices are walkable joints
            if a_base == b_base and a_idx is not None and b_idx is not None:
                if abs(a_idx - b_idx) != 1:
                    continue
            elif a_base == b_base and a_idx is None and b_idx is None:
                pass  # pads / stairs — use proximity
            elif a_base == b_base:
                continue
            # Different ribbons / pads: proximity
            if not ring_touch(a['ring'], b['ring']):
                continue
            step = abs(float(a['top']) - float(b['top']))
            stats['n_floor_joints'] += 1
            stats['largest_step'] = max(stats['largest_step'], step)
            if step > max_step + 1e-9:
                errors.append(
                    f"floor joint '{a.get('name','')}' ↔ '{b.get('name','')}': "
                    f"Δtop {step:.2f}m > {max_step}m (WALL, not a step)"
                )

    stats['path_length_m'] = round(stats['path_length_m'], 1)
    stats['steepest_walk'] = round(stats['steepest_walk'], 4)
    stats['steepest_drive'] = round(stats['steepest_drive'], 4)
    stats['largest_step'] = round(stats['largest_step'], 3)
    return errors, stats


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else 'models/site-grounds.glb')
    errors, stats = check(path)
    report = {'path': str(path), 'ok': not errors, 'stats': stats, 'errors': errors}
    print(json.dumps(report, indent=2))
    sys.exit(0 if not errors else 1)


if __name__ == '__main__':
    main()
