"""
The Oak Leaf — massing of the house proposed for Sulphur Mountain, at real size.

  Same building as before: five leaves around the river-stone chimney (the origin), lower suites
  into the south bank, pool north-west, fire terrace, oak lounge, sacred gardens east.
  What changed in C4 is *how* it is generated — parametric mesh density, open walk rings,
  under ~20k triangles uncompressed. The footprint, massing, roof line and siting are unchanged.

  C8 water contract (pool + hot tub — same as the creek):
    Water is visual only — never a walk floor.
    The BED is the walkable floor (you wade / stand on the bottom).
    No solid fills the water column. Bed sits below surrounding DEM — verified at build.
    Fire terrace is lowered to sit on the north bank terrain (not floating at main-floor y).

  Design numbers (owner / prior massing — do not casually edit):
    see PARAMS['design']

  Mesh density (C4 — edit these to regenerate denser/sparser without redesign):
    see PARAMS['mesh']

    python scripts/oak-leaf.py models/oak-leaf-massing.glb
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

sys.path.insert(0, str(Path(__file__).parent))
from glb import Model, circle, rect, inside, surface  # noqa: E402
from terrain import elevation_en, lnglat_to_en  # noqa: E402

OAK_LL = (-119.155333, 34.433118)

# ---- pack materials (never hardcode RGB) ----------------------------------------------------
GREEN = surface('living_roof')
TIMBER = surface('timber')
RIB = surface('timber_rib')
GLASS = surface('glass')
BRONZE = surface('bronze')
STONE_FLOOR = surface('stone')
RIVER_STONE = surface('river_stone')
CONCRETE = surface('concrete')
WATER = surface('water')
POOL_FLOOR = surface('pool_floor')
DECK = surface('timber', name='timber deck')
DARK_STONE = surface('dark_stone')

# ---- parameters: design is the house; mesh is how densely we sample it ----------------------
PARAMS = {
    'design': {
        'levels_m': {'court': -3.5, 'lower': -3.3, 'main': 0.0, 'loft': 3.7, 'ridge': 9.8},
        'central': {
            'tip': (0, -15), 'base': (0, 11), 'width': 13, 'widest': 0.62,
            'ridge': [(0, 5.8), (0.3, 7.6), (0.62, 9.8), (0.85, 8.4), (1.0, 5.6)],
        },
        'kitchen_wing': {
            'tip': (16.5, 10.5), 'base': (4.0, 2.0), 'width': 9.0, 'widest': 0.62,
            'ridge': [(0, 5.6), (0.35, 6.2), (0.75, 7.0), (1.0, 6.4)],
        },
        'master_wing': {
            'tip': (-14.5, 9.5), 'base': (-4.0, 2.0), 'width': 9.0, 'widest': 0.62,
            'ridge': [(0, 5.6), (0.35, 6.2), (0.75, 7.0), (1.0, 6.4)],
        },
        'lounge_wing': {
            'tip': (15.5, -10.0), 'base': (4.0, -2.0), 'width': 8.6, 'widest': 0.62,
            'ridge': [(0, 5.4), (0.35, 6.0), (0.75, 6.6), (1.0, 6.0)],
        },
        'suites_wing': {
            'tip': (-15.0, -10.5), 'base': (-4.0, -2.0), 'width': 8.6, 'widest': 0.62,
            'ridge': [(0, 5.4), (0.35, 6.0), (0.75, 6.6), (1.0, 6.0)],
        },
        'lower': {'LX0': -14.0, 'LX1': 2.0, 'LN0': -12.0, 'LN1': -3.0},
        'pool_deck': {'DX0': -25.0, 'DX1': -7.0, 'DN0': 13.0, 'DN1': 24.0},
        'pool_centre': (-16.0, 18.5), 'pool_rx': 5.2, 'pool_ry': 3.1,
        'fire': (3.5, 20.0, 0.0), 'oak_lounge': (13.0, -19.5, -1.3),
        'garden_x': 26.0,
    },
    'mesh': {
        # Was nt=56, nv=25 → ~13k living-roof tris alone. Sparse sampling keeps the leaf shape.
        'shell_nt': 10,
        'shell_nv': 5,
        'outline_n': 12,
        'wall_step_m': 3.2,          # was 1.8 — fewer glass bays, same door gaps
        'rib_cross': 3,              # cross-ribs per leaf (was ~L/2.4 dense sweeps)
        'rib_path_n': 5,
        'pool_n': 16,                # was 40
        'circle_n': 12,              # chimneys, terraces (was 24–36)
        'garden_stones': 8,          # was 26
        'garden_circle_n': 8,
        'fire_seats': 6,             # was 8
        'loft_outline_n': 8,         # was 16
        'suite_bays': 6,             # was 12 glass bays on the south face
        'balustrade_posts': 4,
        'shell_thick': 0.32,
    },
}


def P(e, n, y=0.0):
    return (float(e), float(y), float(-n))


def ring_xz(pts):
    return [(float(e), float(-n)) for e, n in pts]


def open_ring(pts):
    """Drop a coincident closing tip so walk rings stay open (consumer closes them)."""
    if len(pts) < 3:
        return [tuple(p) for p in pts]
    a, b = pts[0], pts[-1]
    if abs(float(a[0]) - float(b[0])) < 1e-6 and abs(float(a[1]) - float(b[1])) < 1e-6:
        return [tuple(p) for p in pts[:-1]]
    return [tuple(p) for p in pts]


class Leaf:
    def __init__(self, name, tip, base, width, ridge, eave=None, wall=0.85, fold=1.35, widest=0.6):
        self.name = name
        self.tip = np.array(tip, float); self.base = np.array(base, float)
        d = self.base - self.tip; self.L = float(np.linalg.norm(d)); self.a = d / self.L
        self.n = np.array([-self.a[1], self.a[0]])
        self.W = width; self.wall = wall; self.fold = fold; self.widest = widest
        self.ridge = PchipInterpolator([p[0] for p in ridge], [p[1] for p in ridge])
        eave = eave or [(0, 4.6), (0.25, 3.1), (0.6, 2.9), (0.85, 3.1), (1, 3.9)]
        self.eave_curve = PchipInterpolator([p[0] for p in eave], [p[1] for p in eave])

    def half(self, t):
        tm = self.widest
        if t <= tm:
            return self.W / 2 * math.sin(math.pi / 2 * t / tm) ** 0.8
        u = (t - tm) / (1 - tm)
        return self.W / 2 * math.sqrt(max(0.0, 1 - u * u))

    def eave(self, t):
        return float(self.eave_curve(t))

    def plan(self, t, v):
        return self.tip + self.a * (t * self.L) + self.n * (v * self.half(t))

    def top(self, t, v):
        e = self.eave(t); r = float(self.ridge(t))
        return e + (r - e) * (1 - abs(v) ** self.fold)

    def outline(self, v=None, n=None):
        v = self.wall if v is None else v
        n = PARAMS['mesh']['outline_n'] if n is None else n
        ts = np.linspace(0, 1, n)
        left = [self.plan(t, v) for t in ts]
        right = [self.plan(t, -v) for t in ts[::-1]]
        # tip appears at both ends of a teardrop — keep it once so the walk ring stays open
        return open_ring([tuple(p) for p in left + right])


def leaf_shell(m, leaf):
    """Living-roof shell + soffit at mesh density — same Leaf math, sparse grid, sparse ribs."""
    nt = PARAMS['mesh']['shell_nt']
    nv = PARAMS['mesh']['shell_nv']
    thick = PARAMS['mesh']['shell_thick']
    ts = np.linspace(0, 1, nt); vs = np.linspace(-1, 1, nv)
    top = np.zeros((nt, nv, 3)); sof = np.zeros((nt, nv, 3))
    for i, t in enumerate(ts):
        for j, v in enumerate(vs):
            e, n = leaf.plan(t, v); y = leaf.top(t, v)
            top[i, j] = P(e, n, y); sof[i, j] = P(e, n, y - thick)
    m.grid(GREEN, top, up=True)
    m.grid(TIMBER, sof, up=False)
    for side in (0, nv - 1):
        for i in range(nt - 1):
            a, b = top[i, side], top[i + 1, side]
            c, d = sof[i + 1, side], sof[i, side]
            if side == 0:
                m.quad(TIMBER, a, b, c, d)
            else:
                m.quad(TIMBER, d, c, b, a)

    # Midrib — one thin sweep with few path points (not 30× dense)
    pn = PARAMS['mesh']['rib_path_n']
    path = [P(*leaf.plan(t, 0), leaf.top(t, 0) - thick - 0.25) for t in np.linspace(0.06, 0.98, pn)]
    m.sweep(RIB, path, 0.28, 0.45)
    path = [P(*leaf.plan(t, 0), leaf.top(t, 0) + 0.1) for t in np.linspace(0.02, 0.99, pn)]
    m.sweep(RIB, path, 0.22, 0.28)

    # Cross ribs — fixed count, not every 2.4 m
    for t in np.linspace(0.2, 0.85, PARAMS['mesh']['rib_cross']):
        path = [P(*leaf.plan(t, v), leaf.top(t, v) - thick - 0.18) for v in np.linspace(-1, 1, pn)]
        m.sweep(RIB, path, 0.14, 0.32)


def leaf_walls(m, leaf, doors, skip_inside=(), floor=0.0):
    step = PARAMS['mesh']['wall_step_m']
    nb = max(2, int(round(leaf.L / step)))
    ts = np.linspace(0, 1, nb + 1)
    v = leaf.wall
    for side in (1, -1):
        for i in range(nb):
            t0, t1 = ts[i], ts[i + 1]; tm = (t0 + t1) / 2
            if any(a <= tm <= b for a, b in doors):
                continue
            em, nm = leaf.plan(tm, side * v)
            if any(inside(em, -nm, r) for r in skip_inside):
                continue
            e0, n0 = leaf.plan(t0, side * v); e1, n1 = leaf.plan(t1, side * v)
            y0 = leaf.top(t0, v) - PARAMS['mesh']['shell_thick']
            y1 = leaf.top(t1, v) - PARAMS['mesh']['shell_thick']
            m.grid(GLASS, [[P(e0, n0, floor), P(e1, n1, floor)], [P(e0, n0, y0), P(e1, n1, y1)]], up=True)
            ne = leaf.n * side * 0.08
            ring = [(e0 - ne[0], n0 - ne[1]), (e1 - ne[0], n1 - ne[1]),
                    (e1 + ne[0], n1 + ne[1]), (e0 + ne[0], n0 + ne[1])]
            m.solid(ring_xz(ring), floor, max(y0, y1), f'{leaf.name} wall')
        for t in ts:
            if any(a <= t <= b for a, b in doors):
                continue
            e, n = leaf.plan(t, side * v)
            if any(inside(e, -n, r) for r in skip_inside):
                continue
            post = rect(e - 0.07, -n - 0.07, e + 0.07, -n + 0.07)
            m.extrude(BRONZE, post, floor, leaf.top(t, v) - PARAMS['mesh']['shell_thick'])


def stair(m, mat, x0, z0, dx, dz, w, rise, n, y0, name):
    across = np.array([-dz, dx], float)
    across = across / max(np.linalg.norm(across), 1e-9) * w / 2
    for i in range(1, n + 1):
        a = np.array([x0 + dx * (i - 1), z0 + dz * (i - 1)])
        b = np.array([x0 + dx * i, z0 + dz * i])
        ring = [tuple(a - across), tuple(b - across), tuple(b + across), tuple(a + across)]
        top = y0 + rise * i
        m.extrude(mat, ring, y0 - 0.05, top)
        m.floor(ring, top, f'{name} step {i}')


def balustrade(m, pts, y, h=1.05):
    for i in range(len(pts) - 1):
        (x0, z0), (x1, z1) = pts[i], pts[i + 1]
        m.grid(GLASS, [[(x0, y, z0), (x1, y, z1)], [(x0, y + h, z0), (x1, y + h, z1)]], up=True)
        m.sweep(BRONZE, [(x0, y + h, z0), (x1, y + h, z1)], 0.06, 0.06)


def _leaf_from(name, key):
    d = PARAMS['design'][key]
    return Leaf(name, tip=d['tip'], base=d['base'], width=d['width'], ridge=d['ridge'], widest=d['widest'])


def build():
    m = Model('The Oak Leaf — massing')
    mesh = PARAMS['mesh']
    cn = mesh['circle_n']

    central = _leaf_from('central', 'central')
    NE = _leaf_from('kitchen wing', 'kitchen_wing')
    NW = _leaf_from('master wing', 'master_wing')
    SE = _leaf_from('lounge wing', 'lounge_wing')
    SW = _leaf_from('suites wing', 'suites_wing')
    wings = [NE, NW, SE, SW]
    leaves = [central] + wings
    for leaf in leaves:
        leaf_shell(m, leaf)

    c_ring = central.outline()
    c_xz = ring_xz(c_ring)
    wing_rings = {w.name: w.outline() for w in wings}
    wing_xz = {w.name: ring_xz(wing_rings[w.name]) for w in wings}

    for leaf in leaves:
        xz = c_xz if leaf is central else wing_xz[leaf.name]
        m.extrude(STONE_FLOOR, ring_xz(leaf.outline(v=0.92)), -0.4, 0.0)
        m.floor(xz, 0.0, f'{leaf.name} floor')

    leaf_walls(m, central, doors=[(0, 0.1), (0.27, 0.36), (0.92, 1.0)], skip_inside=tuple(wing_xz.values()))
    for w in wings:
        leaf_walls(m, w, doors=[(0, 0.12), (0.84, 1.0)], skip_inside=(c_xz,))

    chim = circle(0, 0, 1.1, cn)
    m.extrude(RIVER_STONE, chim, -0.5, 11.2)
    m.solid(chim, -0.5, 11.2, 'chimney')
    hearth = rect(-1.6, 0.9, 1.6, 2.4)
    m.extrude(DARK_STONE, hearth, 0, 0.45)
    m.floor(hearth, 0.45, 'hearth')

    ln = mesh['loft_outline_n']
    ts = np.linspace(0.58, 0.9, ln)
    loft = open_ring([tuple(central.plan(t, 0.78)) for t in ts] + [tuple(central.plan(t, -0.78)) for t in ts[::-1]])
    m.extrude(STONE_FLOOR, ring_xz(loft), 3.4, 3.7)
    m.floor(ring_xz(loft), 3.7, 'loft')
    edge = [P(*central.plan(0.58, v), 3.7) for v in np.linspace(-0.78, 0.78, mesh['balustrade_posts'])]
    balustrade(m, [(p[0], p[2]) for p in edge], 3.7)
    stair(m, TIMBER, 2.2, 4.6, 0, -0.6, 1.1, 3.7 / 9, 9, 0.0, 'loft stair')

    L = PARAMS['design']['lower']
    LX0, LX1, LN0, LN1 = L['LX0'], L['LX1'], L['LN0'], L['LN1']
    box = ring_xz([(LX0, LN0), (LX1, LN0), (LX1, LN1), (LX0, LN1)])
    m.extrude(CONCRETE, box, -3.6, -3.3)
    m.floor(box, -3.3, 'lower floor')
    for wall in (rect(LX0 - 0.4, -LN1, LX1 + 0.4, -LN1 + 0.4),
                 rect(LX0 - 0.4, -LN1, LX0, -LN0), rect(LX1, -LN1, LX1 + 0.4, -LN0)):
        m.extrude(RIVER_STONE, wall, -3.6, -0.4)
        m.solid(wall, -3.6, -0.4, 'lower wall')
    for e in (-8.7, -3.3):
        part = rect(e - 0.08, -(-5.5), e + 0.08, -LN0)
        m.extrude(STONE_FLOOR, part, -3.3, -0.4)
        m.solid(part, -3.3, -0.4, 'partition')

    doors = [(-12.0, -10.6), (-6.7, -5.3), (-1.35, 0.05)]
    xs = np.linspace(LX0, LX1, mesh['suite_bays'] + 1)
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]; xm = (x0 + x1) / 2
        if any(a <= xm <= b for a, b in doors):
            continue
        m.grid(GLASS, [[P(x0, LN0, -3.3), P(x1, LN0, -3.3)], [P(x0, LN0, -0.4), P(x1, LN0, -0.4)]], up=True)
        bay = rect(x0, -LN0 - 0.08, x1, -LN0 + 0.08)
        m.solid(bay, -3.3, -0.4, 'suite front')
    for x in xs:
        m.extrude(BRONZE, rect(x - 0.07, -LN0 - 0.07, x + 0.07, -LN0 + 0.07), -3.3, -0.4)

    for cx in (-11.3, -6.0, -0.65):
        top = rect(cx - 2.6, -(-12.6), cx + 2.6, -(-18.2))
        m.extrude(TIMBER, top, -1.1, -0.85)
        for px, pn in ((cx - 2.4, -12.9), (cx + 2.4, -12.9), (cx - 2.4, -17.9), (cx + 2.4, -17.9)):
            m.extrude(BRONZE, rect(px - 0.1, -pn - 0.1, px + 0.1, -pn + 0.1), -3.5, -1.1)

    stair(m, STONE_FLOOR, -8.0, 3.85, 0.6, 0, 1.1, 3.3 / 8, 8, -3.3, 'lower stair')
    terr = ring_xz([(LX0, LN0), (-5.0, LN0), (-5.0, LN1), (LX0, LN1)])
    m.extrude(GREEN, terr, -0.4, 0.0)
    m.floor(terr, 0.0, 'roof terrace')
    balustrade(m, [(LX0, -LN1), (LX0, -LN0), (-5.0, -LN0)], 0.0)

    stair(m, RIVER_STONE, 0, 20.9, 0, -0.72, 2.6, 3.5 / 9, 9, -3.5, 'front steps')
    apron = ring_xz([(-15.5, -12.2), (3.5, -12.2), (3.5, -19.5), (-15.5, -19.5)])
    m.extrude(CONCRETE, apron, -3.55, -3.48)

    terrace = ring_xz([(-7, 9.5), (7, 9.5), (7, 14), (-7, 14)])
    m.extrude(STONE_FLOOR, terrace, -0.25, 0.0)
    m.floor(terrace, 0.0, 'north terrace')

    # --- C8: pool / fire sit on north-bank DEM; water is not a floor ---
    oak_en = lnglat_to_en(*OAK_LL)
    oak_z = elevation_en(*oak_en)
    pcx, pcn = PARAMS['design']['pool_centre']
    prx, pry = PARAMS['design']['pool_rx'], PARAMS['design']['pool_ry']
    pool_terrain_dy = elevation_en(oak_en[0] + pcx, oak_en[1] + pcn) - oak_z
    # deck slightly above local terrain; bed cut well below it
    deck_y = pool_terrain_dy + 0.08
    water_y = deck_y - 0.35
    bed_y = water_y - 1.45
    # verify bed below surrounding terrain at deck corners + centre
    D = PARAMS['design']['pool_deck']
    DX0, DX1, DN0, DN1 = D['DX0'], D['DX1'], D['DN0'], D['DN1']
    bank_dys = [
        elevation_en(oak_en[0] + e, oak_en[1] + n) - oak_z
        for e, n in ((DX0, DN0), (DX1, DN0), (DX1, DN1), (DX0, DN1), (pcx, pcn))
    ]
    assert bed_y < min(bank_dys) - 0.2, (
        f'pool bed not below terrain: bed_y={bed_y:.3f} min_bank_dy={min(bank_dys):.3f}'
    )

    # stairs from north terrace (y=0) down to pool deck
    n_pool_steps = max(1, int(math.ceil(abs(deck_y) / 0.17)))
    rise = abs(deck_y) / n_pool_steps
    stair(m, STONE_FLOOR, -7.5, -13.5, 0.0, -0.35, 4.0, rise, n_pool_steps, deck_y, 'pool step')

    # deck collar — four pads around the pool so the bed floor is not covered by a higher floor
    pool = [(pcx + prx * math.cos(a), pcn + pry * math.sin(a))
            for a in np.linspace(0, 2 * math.pi, mesh['pool_n'], endpoint=False)]
    pool_xz = ring_xz(pool)
    pads = [
        ('pool deck S', [(DX0, DN0), (DX1, DN0), (DX1, pcn - pry - 0.15), (DX0, pcn - pry - 0.15)]),
        ('pool deck N', [(DX0, pcn + pry + 0.15), (DX1, pcn + pry + 0.15), (DX1, DN1), (DX0, DN1)]),
        ('pool deck W', [(DX0, pcn - pry), (pcx - prx - 0.15, pcn - pry),
                         (pcx - prx - 0.15, pcn + pry), (DX0, pcn + pry)]),
        ('pool deck E', [(pcx + prx + 0.15, pcn - pry), (DX1, pcn - pry),
                         (DX1, pcn + pry), (pcx + prx + 0.15, pcn + pry)]),
    ]
    for name, pts in pads:
        ring = ring_xz(pts)
        m.extrude(DECK, ring, deck_y - 0.25, deck_y, lid=True)
        m.floor(ring, deck_y, name)

    # bed walkable; water visual only; no solid filling the column
    m.extrude(POOL_FLOOR, pool_xz, bed_y - 0.1, bed_y, lid=True)
    m.floor(pool_xz, bed_y, 'pool bed')
    m.cap(WATER, pool_xz, water_y, up=True)
    # entry steps from south deck into the pool (reachability + wade)
    drop = deck_y - bed_y
    n_in = max(2, int(math.ceil(drop / 0.28)))
    in_rise = drop / n_in
    stair(m, STONE_FLOOR, pcx - 1.2, -(pcn - pry + 0.4), 0.0, 0.4, 2.4, in_rise, n_in, bed_y, 'pool entry')
    # low rim curb (segments) — stops a fall at the lip without blocking the bed
    for i in range(len(pool)):
        a, b = pool[i], pool[(i + 1) % len(pool)]
        # outward offset ~0.2 m
        mx, my = 0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1])
        vx, vy = mx - pcx, my - pcn
        L = math.hypot(vx, vy) or 1.0
        ox, oy = 0.22 * vx / L, 0.22 * vy / L
        curb = ring_xz([(a[0], a[1]), (b[0], b[1]), (b[0] + ox, b[1] + oy), (a[0] + ox, a[1] + oy)])
        m.extrude(STONE_FLOOR, curb, deck_y, deck_y + 0.12)
        m.solid(curb, deck_y, deck_y + 0.12, f'pool rim {i}')
    # hot tub — same contract, on local terrain
    tub_e, tub_n = -8.8, 15.0
    tub_dy = elevation_en(oak_en[0] + tub_e, oak_en[1] + tub_n) - oak_z
    tub_rim = tub_dy + 0.12
    tub_water = tub_rim - 0.15
    tub_bed = tub_water - 0.85
    assert tub_bed < tub_dy - 0.2
    tub = circle(tub_e, -tub_n, 1.6, cn)
    m.extrude(POOL_FLOOR, tub, tub_bed - 0.05, tub_bed, lid=True)
    m.floor(tub, tub_bed, 'hot tub bed')
    m.cap(WATER, tub, tub_water, up=True)
    # rim ring as a low solid collar (approximate with outer circle solid band via seats-style)
    tub_outer = circle(tub_e, -tub_n, 1.85, cn)
    # solid only on the rim annulus is hard; use a low wall band at rim height covering outer lip
    for i in range(0, len(tub_outer), 2):
        a = tub_outer[i]
        b = tub_outer[(i + 1) % len(tub_outer)]
        c = tub[(i + 1) % len(tub)]
        d = tub[i % len(tub)]
        lip = [a, b, c, d]
        m.extrude(STONE_FLOOR, lip, tub_bed, tub_rim)
        m.solid(lip, tub_bed, tub_rim, f'hot tub rim {i}')

    # fire terrace on north-bank terrain; oak lounge plan y unchanged (south)
    fire_cx, fire_cn, _ = PARAMS['design']['fire']
    fire_y = elevation_en(oak_en[0] + fire_cx, oak_en[1] + fire_cn) - oak_z + 0.05
    # link north terrace down to fire
    n_fire_steps = max(1, int(math.ceil(abs(fire_y) / 0.17)))
    fire_rise = abs(fire_y) / n_fire_steps
    stair(m, STONE_FLOOR, 2.0, -14.0, 0.15, -0.4, 2.2, fire_rise, n_fire_steps, fire_y, 'fire step')

    for (cx, cnorth, y, mat, name) in (
        (fire_cx, fire_cn, fire_y, STONE_FLOOR, 'fire terrace'),
        (*PARAMS['design']['oak_lounge'], DECK, 'oak lounge'),
    ):
        ring = circle(cx, -cnorth, 5.2, cn)
        m.extrude(mat, ring, y - 0.2, y)
        m.floor(ring, y, name)
        pit = circle(cx, -cnorth, 1.1, max(8, cn // 2))
        m.extrude(DARK_STONE, pit, y, y + 0.45)
        m.solid(pit, y, y + 0.45, name + ' fire')
        nseat = mesh['fire_seats']
        for k in range(nseat):
            a = 2 * math.pi * k / nseat
            if 1.5 < a < 2.2:
                continue
            sx, sz = cx + 3.6 * math.cos(a), -cnorth + 3.6 * math.sin(a)
            ux, uz = math.cos(a), math.sin(a); vx, vz = -uz, ux
            seat = [(sx - 0.25 * ux - 0.9 * vx, sz - 0.25 * uz - 0.9 * vz),
                    (sx + 0.25 * ux - 0.9 * vx, sz + 0.25 * uz - 0.9 * vz),
                    (sx + 0.25 * ux + 0.9 * vx, sz + 0.25 * uz + 0.9 * vz),
                    (sx - 0.25 * ux + 0.9 * vx, sz - 0.25 * uz + 0.9 * vz)]
            m.extrude(DARK_STONE, seat, y, y + 0.45)
            m.solid(seat, y, y + 0.45, name + ' seat')
    GX = PARAMS['design']['garden_x']
    for k, n in enumerate(np.linspace(-15, 15, mesh['garden_stones'])):
        e = GX + 1.8 * math.sin(n / 6.0) + (0.45 if k % 2 else -0.45)
        pad = circle(e, -n, 0.62, mesh['garden_circle_n'])
        m.extrude(STONE_FLOOR, pad, -0.1, 0.06)
        m.floor(pad, 0.06, 'garden stone')
    for k, n in enumerate(np.linspace(-11, 11, 5)):
        e = GX + 1.8 * math.sin(n / 6.0) + (2.6 if k % 2 else -2.6)
        st = circle(e, -n, 0.42, mesh['garden_circle_n'])
        h = 1.2 + 0.3 * (k % 3)
        m.extrude(RIVER_STONE, st, 0.0, h)
        m.solid(st, 0.0, h, 'standing stone')

    drive = ring_xz([(-22.0, -13.0), (-15.5, -13.0), (-15.5, -19.5), (-22.0, -19.5)])
    m.extrude(CONCRETE, drive, -3.55, -3.46)
    m.floor(drive, -3.46, 'drive')

    out = {'central': c_ring, 'pool': pool, 'lower': [(LX0, LN0), (LX1, LN0), (LX1, LN1), (LX0, LN1)]}
    out.update(wing_rings)
    water_info = {
        'contract': 'bed walkable; water visual only; no solid in water column',
        'pool': {
            'deck_y': round(deck_y, 3),
            'water_y': round(water_y, 3),
            'bed_y': round(bed_y, 3),
            'terrain_dy_at_centre': round(pool_terrain_dy, 3),
            'bed_below_terrain_m': round(min(bank_dys) - bed_y, 3),
        },
        'fire_terrace_y': round(fire_y, 3),
    }
    return m, out, water_info


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'models/oak-leaf-massing.glb'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    m, rings, water_info = build()
    info = m.write(out, extras={
        'levels_m': PARAMS['design']['levels_m'],
        'params': PARAMS,
        'authority': 'proposal',
        'origin_note': 'river-stone chimney of the standing house',
        'water': water_info,
    })
    info['floors'] = len(m.walk['floors'])
    info['solids'] = len(m.walk['solids'])
    print(json.dumps({'bytes': info['bytes'], 'triangles': info['triangles'], 'meshes': info['meshes'],
                      'floors': info['floors'], 'solids': info['solids'], 'water': water_info}))
    if len(sys.argv) > 2:
        json.dump({k: [[round(float(e), 2), round(float(n), 2)] for e, n in v]
                   for k, v in rings.items()}, open(sys.argv[2], 'w'))
