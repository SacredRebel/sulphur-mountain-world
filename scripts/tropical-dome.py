"""
Tropical Dome Greenhouse — low-segment shell, not a tessellated sphere.

  Segment count is deliberate: AZ=12 meridians × BANDS=3 elevation bands.
  Glass panels = AZ × BANDS quads. One meridional bay at the base is omitted —
  that GAP is the door. Timber ribs follow the meridians (one quad strip each).

  Origin: centre of the door threshold on the south. Rings stay open.
  If the dome shell alone exceeds ~2,000 triangles, stop — do not compress.

    python scripts/tropical-dome.py models/tropical-dome.glb
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, surface  # noqa: E402

# ---- deliberate tessellation -------------------------------------------------
AZ = 12          # meridians around
BANDS = 3        # elevation bands from eave to apex (not a UV sphere)
RADIUS = 5.5     # metres clearspan
EAVE_Y = 0.35    # knee wall under the glass
APEX_Y = 5.8     # tip height above pad

STONE = surface('stone')
TIMBER = surface('timber')
GLASS = surface('glass')
CONCRETE = surface('concrete')


def P(e, n, y=0.0):
    return (float(e), float(y), float(-n))


def ring_xz(pts):
    return [(float(e), float(-n)) for e, n in pts]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(v):
    L = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (0.0, 1.0, 0.0) if L < 1e-9 else (v[0] / L, v[1] / L, v[2] / L)


def _dome_point(i, j):
    """i = meridian 0..AZ, j = band 0..BANDS (0=eave, BANDS=apex).
    Plan: centre at (0, RADIUS) so the south eave sits on n=0 (door line)."""
    # Skip wrapping: i in 0..AZ-1 for panels; apex is shared
    if j >= BANDS:
        return (0.0, RADIUS, APEX_Y)
    a = 2 * math.pi * i / AZ - math.pi / 2  # i=0 → south
    # fraction up the dome: j/BANDS; radius shrinks as cos-ish toward apex
    t = j / BANDS
    # hemispherical profile: r = R * cos(phi), y = R * sin(phi) remapped to eave..apex
    phi = t * (math.pi / 2)  # 0 at eave equator direction… use quarter-sphere from horizontal
    # Better massing: eave at full R, apex on axis
    rr = RADIUS * math.cos(phi)
    y = EAVE_Y + (APEX_Y - EAVE_Y) * math.sin(phi)
    e = rr * math.cos(a)
    n = RADIUS + rr * math.sin(a)  # centre at n=RADIUS; south point at n≈0 when sin=-1
    return (e, n, y)


def build():
    m = Model('Tropical Dome Greenhouse — low-segment shell')
    # Pad / floor — open AZ-gon (do not repeat first point)
    floor_pts = []
    for i in range(AZ):
        a = 2 * math.pi * i / AZ - math.pi / 2
        floor_pts.append((RADIUS * math.cos(a), RADIUS + RADIUS * math.sin(a)))
    m.extrude(CONCRETE, ring_xz(floor_pts), -0.1, 0.0)
    m.floor(ring_xz(floor_pts), 0.0, 'dome floor')

    # Knee wall — continuous solids with ONE bay omitted (door gap at i=0, south)
    door_i = 0
    for i in range(AZ):
        if i == door_i:
            continue
        a0 = 2 * math.pi * i / AZ - math.pi / 2
        a1 = 2 * math.pi * ((i + 1) % AZ) / AZ - math.pi / 2
        r0, r1 = RADIUS - 0.1, RADIUS
        ring = [
            (r0 * math.cos(a0), RADIUS + r0 * math.sin(a0)),
            (r1 * math.cos(a0), RADIUS + r1 * math.sin(a0)),
            (r1 * math.cos(a1), RADIUS + r1 * math.sin(a1)),
            (r0 * math.cos(a1), RADIUS + r0 * math.sin(a1)),
        ]
        xz = ring_xz(ring)
        m.extrude(STONE, xz, 0.0, EAVE_Y)
        m.solid(xz, 0.0, EAVE_Y, f'knee {i}')

    glass_quads = 0
    # Glass bands — skip door bay only on the lowest band
    for j in range(BANDS):
        for i in range(AZ):
            if j == 0 and i == door_i:
                continue
            p00 = _dome_point(i, j)
            p10 = _dome_point((i + 1) % AZ, j)
            p11 = _dome_point((i + 1) % AZ, j + 1)
            p01 = _dome_point(i, j + 1)
            # convert plan (e,n,y) → model
            A = P(p00[0], p00[1], p00[2])
            B = P(p10[0], p10[1], p10[2])
            C = P(p11[0], p11[1], p11[2])
            D = P(p01[0], p01[1], p01[2])
            if j + 1 >= BANDS:
                # triangle to apex
                tip = P(0.0, RADIUS, APEX_Y)
                nrm = _norm(_cross(_sub(B, A), _sub(tip, A)))
                m.tris(GLASS, [A, B, tip], [nrm, nrm, nrm], [0, 1, 2])
                glass_quads += 0.5  # half-quad accounting
            else:
                m.quad(GLASS, A, B, C, D)
                glass_quads += 1

    # Timber ribs — one quad strip per meridian (eave → near-apex), skip door meridian face
    rib_tris_est = 0
    for i in range(AZ):
        if i == door_i:
            continue
        pts = [_dome_point(i, j) for j in range(BANDS + 1)]
        # thin outward offset rib as a strip of quads along the meridian
        for j in range(len(pts) - 1):
            e0, n0, y0 = pts[j]
            e1, n1, y1 = pts[j + 1]
            # radial outward 8 cm
            a = 2 * math.pi * i / AZ - math.pi / 2
            ox, on = 0.08 * math.cos(a), 0.08 * math.sin(a)
            m.quad(TIMBER,
                   P(e0, n0, y0), P(e0 + ox, n0 + on, y0),
                   P(e1 + ox, n1 + on, y1), P(e1, n1, y1))
            rib_tris_est += 2

    # Door threshold marker (floor strip) — walkable approach into the gap
    door = [(-1.0, -0.4), (1.0, -0.4), (1.0, 0.3), (-1.0, 0.3)]
    m.extrude(STONE, ring_xz(door), -0.05, 0.02)
    m.floor(ring_xz(door), 0.02, 'door threshold')

    # Built footprint = pad circle AABB
    fp = [(-RADIUS - 0.2, -0.2), (RADIUS + 0.2, -0.2),
          (RADIUS + 0.2, 2 * RADIUS + 0.2), (-RADIUS - 0.2, 2 * RADIUS + 0.2)]

    meta = {
        'az_segments': AZ,
        'elevation_bands': BANDS,
        'radius_m': RADIUS,
        'glass_panels_approx': glass_quads,
        'rib_tris_approx': rib_tris_est,
        'note': f'low-segment dome: {AZ} meridians × {BANDS} bands; door = omitted bay {door_i}',
    }
    return m, fp, meta


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/tropical-dome.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, fp, meta = build()
    info = m.write(out, extras={
        'zone': 'tropical-dome-greenhouse',
        'origin_note': 'south door threshold centre',
        'authority': 'proposed',
        'footprint_en_m': [[round(e, 2), round(n, 2)] for e, n in fp],
        **meta,
    })
    info['floors'] = len(m.walk['floors'])
    info['solids'] = len(m.walk['solids'])
    info['dome'] = meta
    print(json.dumps(info))
