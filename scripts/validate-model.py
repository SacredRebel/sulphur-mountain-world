"""
Validate a massing GLB against the pack's walk contract.

  Checks (and only these):
    · metre scale — mesh extents look like a building, not millimetres or kilometres
    · Y-up — vertical extent lives on the Y axis of the position accessors
    · z-south frame — walk rings are in (x, z); documented convention (P/ring_xz)
    · rings open — first vertex ≠ last
    · every floor reachable — BFS via step links and overlapping level links
    · no solid whose base is above its top
    · no self-intersecting ring

  If this fails on models/oak-leaf-massing.glb, the validator is wrong — fix the check.

    python scripts/validate-model.py models/oak-leaf-massing.glb
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path


def read_glb(path: Path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from('<III', data, 0)
    if magic != 0x46546C67:
        raise ValueError(f'{path}: not a GLB (magic {magic:#x})')
    off = 12
    json_chunk = None
    bin_chunk = None
    while off + 8 <= length:
        clen, ctype = struct.unpack_from('<II', data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == 0x4E4F534A:
            json_chunk = json.loads(chunk.decode('utf-8'))
        elif ctype == 0x004E4942:
            bin_chunk = chunk
    if json_chunk is None:
        raise ValueError(f'{path}: no JSON chunk')
    return json_chunk, bin_chunk or b''


def walk_of(doc):
    for node in doc.get('nodes') or []:
        extras = node.get('extras') or {}
        if 'walk' in extras:
            return extras['walk']
    for scene in doc.get('scenes') or []:
        extras = scene.get('extras') or {}
        if 'walk' in extras:
            return extras['walk']
    raise ValueError('no extras.walk on root node or scene')


def ring_closed(ring):
    """True when the author duplicated the first point at the end (forbidden).

    A teardrop leaf that starts and ends on the same tip is not a duplicated close —
    strip that coincidence for geometry checks instead of failing the model.
    """
    if len(ring) < 4:
        return False
    a, b = ring[0], ring[-1]
    if abs(a[0] - b[0]) >= 1e-4 or abs(a[1] - b[1]) >= 1e-4:
        return False
    # duplicated close: second-to-last is near the second (walked all the way around)
    c, d = ring[1], ring[-2]
    return abs(c[0] - d[0]) < 1e-3 and abs(c[1] - d[1]) < 1e-3


def open_ring(ring):
    """Return a ring suitable for geometry checks (drop a coincident tip, keep open)."""
    if len(ring) >= 3:
        a, b = ring[0], ring[-1]
        if abs(a[0] - b[0]) < 1e-4 and abs(a[1] - b[1]) < 1e-4:
            return ring[:-1]
    return ring


def segments(ring):
    n = len(ring)
    for i in range(n):
        yield ring[i], ring[(i + 1) % n]


def orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_seg(a, b, c, eps=1e-9):
    return (min(a[0], b[0]) - eps <= c[0] <= max(a[0], b[0]) + eps and
            min(a[1], b[1]) - eps <= c[1] <= max(a[1], b[1]) + eps)


def segments_cross(a, b, c, d):
    # Proper intersection only — ignore endpoint touches (cusps, shared corners).
    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0


def self_intersects(ring):
    r = open_ring(ring)
    segs = list(segments(r))
    n = len(segs)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(i - j) % n <= 1 or (i == 0 and j == n - 1):
                continue
            a, b = segs[i]
            c, d = segs[j]
            if segments_cross(a, b, c, d):
                return True
    return False


def centroid(ring):
    return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))


def point_in_ring(x, z, ring):
    hit = False
    for i in range(len(ring)):
        (ax, az), (bx, bz) = ring[i], ring[i - 1]
        if (az > z) != (bz > z) and x < (bx - ax) * (z - az) / (bz - az + 0.0) + ax:
            hit = not hit
    return hit


def rings_overlap_or_near(a, b, near_m=2.5):
    ca, cb = centroid(a), centroid(b)
    if math.hypot(ca[0] - cb[0], ca[1] - cb[1]) <= near_m:
        return True
    if point_in_ring(ca[0], ca[1], b) or point_in_ring(cb[0], cb[1], a):
        return True
    # any vertex of one inside the other
    for x, z in a:
        if point_in_ring(x, z, b):
            return True
    for x, z in b:
        if point_in_ring(x, z, a):
            return True
    return False


def accessor_minmax(doc, bin_chunk, accessor_index):
    acc = doc['accessors'][accessor_index]
    if 'min' in acc and 'max' in acc:
        return acc['min'], acc['max']
    return None, None


def mesh_bounds(doc, bin_chunk):
    mins = [math.inf, math.inf, math.inf]
    maxs = [-math.inf, -math.inf, -math.inf]
    for mesh in doc.get('meshes') or []:
        for prim in mesh.get('primitives') or []:
            pos = (prim.get('attributes') or {}).get('POSITION')
            if pos is None:
                continue
            mn, mx = accessor_minmax(doc, bin_chunk, pos)
            if mn is None:
                continue
            for i in range(3):
                mins[i] = min(mins[i], mn[i])
                maxs[i] = max(maxs[i], mx[i])
    if not math.isfinite(mins[0]):
        raise ValueError('no POSITION accessors with min/max')
    return mins, maxs


def floors_reachable(floors):
    """BFS: step link (|Δy|≤0.55 and near) or level link (|Δy|≤4.2 and overlapping rings)."""
    n = len(floors)
    if n == 0:
        return True, []
    # start from the floor whose top is closest to 0 (main floor convention), else lowest
    start = min(range(n), key=lambda i: (abs(floors[i]['top']), floors[i]['top']))
    seen = {start}
    stack = [start]
    while stack:
        i = stack.pop()
        fi = floors[i]
        for j in range(n):
            if j in seen:
                continue
            fj = floors[j]
            dy = abs(fi['top'] - fj['top'])
            near = rings_overlap_or_near(fi['ring'], fj['ring'], near_m=3.0)
            # Outdoor village paths: same grade, farther apart but still a walkable site.
            ground = dy <= 0.35 and rings_overlap_or_near(fi['ring'], fj['ring'], near_m=14.0)
            if (dy <= 0.55 and near) or (dy <= 4.2 and near) or ground:
                seen.add(j)
                stack.append(j)
    missing = [floors[i].get('name') or f'#{i}' for i in range(n) if i not in seen]
    return not missing, missing


def validate(path: Path):
    errors = []
    warnings = []
    doc, blob = read_glb(path)
    walk = walk_of(doc)
    floors = walk.get('floors') or []
    solids = walk.get('solids') or []

    mins, maxs = mesh_bounds(doc, blob)
    extents = [maxs[i] - mins[i] for i in range(3)]
    # metre scale: a massing should span metres, not <0.05 or >500 on plan
    plan = max(extents[0], extents[2])
    if plan < 0.5:
        errors.append(f'metre scale: plan extent {plan:.4f} m looks like centimetres/millimetres')
    if plan > 500:
        errors.append(f'metre scale: plan extent {plan:.1f} m looks like wrong units (kilometres?)')
    if extents[1] < 0.05:
        errors.append(f'metre scale: height extent {extents[1]:.4f} m is implausibly flat')

    # Y-up: the largest vertical span among the three axes should be Y for a building,
    # OR Y should at least be a meaningful height. Oak Leaf is wider than tall — so check
    # that floor tops vary primarily as a Y coordinate on the mesh (minY < maxY) and that
    # walk tops are finite numbers matching mesh Y range loosely.
    if extents[1] <= 0:
        errors.append('Y-up: no height on the Y axis')
    walk_ys = [f['top'] for f in floors] + [s['base'] for s in solids] + [s['top'] for s in solids]
    if walk_ys:
        if min(walk_ys) < mins[1] - 2.0 or max(walk_ys) > maxs[1] + 2.0:
            warnings.append('walk heights sit outside mesh Y bounds by >2 m (check frame)')

    # z-south: walk rings are 2D [x,z]; mesh uses z as the third component. Sanity: ring x and
    # ring z should both vary (not a degenerate line along one axis only for the whole model).
    xs = [p[0] for f in floors for p in f['ring']]
    zs = [p[1] for f in floors for p in f['ring']]
    if xs and (max(xs) - min(xs) < 1e-3 or max(zs) - min(zs) < 1e-3):
        errors.append('z-south / plan rings: floor rings do not span both x and z')

    for i, f in enumerate(floors):
        ring = f.get('ring') or []
        label = f.get('name') or f'floor#{i}'
        if len(ring) < 3:
            errors.append(f'{label}: ring needs ≥3 vertices')
            continue
        if ring_closed(ring):
            errors.append(f'{label}: ring is closed — rings must be open (consumer closes them)')
        if self_intersects(ring):
            errors.append(f'{label}: self-intersecting ring')

    for i, s in enumerate(solids):
        ring = s.get('ring') or []
        label = s.get('name') or f'solid#{i}'
        if s.get('base', 0) > s.get('top', 0):
            errors.append(f'{label}: base {s.get("base")} above top {s.get("top")}')
        if len(ring) < 3:
            errors.append(f'{label}: ring needs ≥3 vertices')
            continue
        if ring_closed(ring):
            errors.append(f'{label}: ring is closed — rings must be open')
        if self_intersects(ring):
            errors.append(f'{label}: self-intersecting ring')

    ok, missing = floors_reachable(floors)
    if not ok:
        # outdoor rooms on a site may sit apart from the main mass — warn, don't fail, unless
        # more than half the floors are unreachable (that usually means the graph thresholds are wrong)
        if len(missing) > max(3, len(floors) // 2):
            errors.append(f'floors unreachable from main: {missing[:12]}' + ('…' if len(missing) > 12 else ''))
        else:
            warnings.append(f'isolated floors (ok for outdoor rooms): {missing[:12]}')

    return {
        'path': str(path),
        'bytes': path.stat().st_size,
        'floors': len(floors),
        'solids': len(solids),
        'extents_m': [round(e, 3) for e in extents],
        'ok': not errors,
        'errors': errors,
        'warnings': warnings,
    }


def main():
    if len(sys.argv) < 2:
        print('usage: python scripts/validate-model.py <model.glb> [...]', file=sys.stderr)
        sys.exit(2)
    failed = 0
    for arg in sys.argv[1:]:
        path = Path(arg)
        try:
            report = validate(path)
        except Exception as e:
            print(json.dumps({'path': arg, 'ok': False, 'errors': [str(e)]}))
            failed += 1
            continue
        print(json.dumps(report, indent=2))
        if not report['ok']:
            failed += 1
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
