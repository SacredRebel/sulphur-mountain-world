"""
C25.1 — species archetypes + instance table fitted to trees.csv.

  Builds a handful of low-poly trunk+crown GLBs whose height and crown radius
  match k-means centres of the measured trees. Each tree is an instance:
  position, yaw, uniform scale, archetype id.

  Badge: meshes are authority=generated / evidence=modelled. Positions and
  dimensions they are fitted to are measured (trees.csv).

  ez-tree (@dgreenheck/ez-tree, MIT) is the preferred procedural generator when
  the Node toolchain is available; this script is the pack-local fitted
  fallback that ships the same contract (archetypes + instances + error bound).

    python scripts/build-tree-instances.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from glb import Model, surface  # noqa: E402
from terrain import en_to_lnglat  # noqa: E402

N_ARCHETYPES = 16
OUT_DIR = ROOT / 'models' / 'trees'
INSTANCES = ROOT / 'trees-instances.json'
ERROR_BOUND_M = 4.0  # published worst-case bound; printed by check-budget


def load_trees():
    rows = []
    with (ROOT / 'trees.csv').open(encoding='utf-8', newline='') as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            h = float(row['height_dm']) / 10.0
            r = float(row.get('crown_radius_dm') or 30) / 10.0
            if h < 0.5:
                h = 0.5
            if r < 0.5:
                r = 0.5
            rows.append({
                'id': i,
                'e': float(row['x_east_dm']) / 10.0,
                'n': float(row['y_north_dm']) / 10.0,
                'z': float(row.get('ground_dm') or 0) / 10.0,
                'height_m': h,
                'crown_radius_m': r,
            })
    return rows


def kmeans(X: np.ndarray, k: int, seed: int = 25, iters: int = 40):
    rng = np.random.default_rng(seed)
    # init: quantile picks
    centres = X[rng.choice(len(X), size=k, replace=False)].copy()
    labels = np.zeros(len(X), dtype=int)
    for _ in range(iters):
        d = ((X[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        labels = d.argmin(axis=1)
        for j in range(k):
            pts = X[labels == j]
            if len(pts):
                centres[j] = pts.mean(axis=0)
    return labels, centres


def build_archetype_glb(path: Path, height_m: float, crown_r: float, seed: int):
    """Unit-ish tree: trunk to ~0.55*H, crown ellipsoid of radius crown_r at height."""
    m = Model(path.stem)
    bark = surface('timber')
    leaf = surface('living_roof')
    trunk_h = max(0.4, height_m * 0.55)
    trunk_r = max(0.08, crown_r * 0.12)
    # trunk as 8-sided prism
    ring0, ring1 = [], []
    for i in range(8):
        a = 2 * math.pi * i / 8
        ring0.append((trunk_r * math.cos(a), trunk_r * math.sin(a)))
        ring1.append((trunk_r * 0.7 * math.cos(a), trunk_r * 0.7 * math.sin(a)))
    m.extrude(bark, ring0, 0.0, trunk_h, lid=True, bottom=True)
    # crown: icosphere-ish stacked rings
    cx, cy, cz = 0.0, trunk_h + crown_r * 0.35, 0.0
    n_lat, n_lon = 6, 10
    pts = []
    for i in range(n_lat + 1):
        v = math.pi * i / n_lat
        y = cy + crown_r * math.cos(v) * 0.85  # slightly flattened
        rad = crown_r * math.sin(v)
        row = []
        for j in range(n_lon):
            u = 2 * math.pi * j / n_lon
            row.append((cx + rad * math.cos(u), y, cz + rad * math.sin(u)))
        pts.append(row)
    # quads between rows
    for i in range(n_lat):
        for j in range(n_lon):
            a = pts[i][j]
            b = pts[i][(j + 1) % n_lon]
            c = pts[i + 1][(j + 1) % n_lon]
            d = pts[i + 1][j]
            m.quad(leaf, a, b, c, d)
    path.parent.mkdir(parents=True, exist_ok=True)
    m.write(path)
    # triangle estimate from parts
    tris = sum(len(idx) // 3 for _, (_, _, idx) in m.parts.items())
    return tris


def main():
    trees = load_trees()
    X = np.array([
        [t['height_m'], t['crown_radius_m'], t['height_m'] / max(t['crown_radius_m'], 0.5)]
        for t in trees
    ], dtype=float)
    # normalize features for k-means
    mu, sig = X.mean(axis=0), X.std(axis=0)
    sig = np.where(sig < 1e-6, 1.0, sig)
    Xn = (X - mu) / sig
    labels, centres_n = kmeans(Xn, N_ARCHETYPES)
    centres = centres_n * sig + mu
    centres = centres[:, :2]  # height, crown only for mesh build
    # sort archetypes by height
    order = np.argsort(centres[:, 0])
    remap = {int(old): int(new) for new, old in enumerate(order)}
    centres = centres[order]
    labels = np.array([remap[int(L)] for L in labels])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    archetypes = []
    for i, (h, r) in enumerate(centres):
        name = f'oak-arch-{i}'
        path = OUT_DIR / f'{name}.glb'
        tris = build_archetype_glb(path, float(h), float(r), seed=100 + i)
        archetypes.append({
            'id': name,
            'path': f'models/trees/{name}.glb',
            'height_m': round(float(h), 2),
            'crown_radius_m': round(float(r), 2),
            'triangles': tris,
            'authority': 'generated',
            'evidence': 'modelled',
            'licence': 'own-work',
            'source': 'own-work',
            'generator': 'scripts/build-tree-instances.py',
            'note': 'Fitted parametric oak; ez-tree MIT preferred when Node toolchain available',
        })

    instances = []
    err_h, err_r = [], []
    for t, lab in zip(trees, labels):
        arch = archetypes[int(lab)]
        # uniform scale chosen to minimise max(height err, crown err)
        ah, ar = arch['height_m'], arch['crown_radius_m']
        # candidate scales
        cands = []
        if ah > 0.1:
            cands.append(t['height_m'] / ah)
        if ar > 0.1:
            cands.append(t['crown_radius_m'] / ar)
        cands.append(0.5 * (t['height_m'] / max(ah, 0.1) + t['crown_radius_m'] / max(ar, 0.1)))
        best_s, best_e = 1.0, 1e9
        for s in cands:
            eh = abs(s * ah - t['height_m'])
            er = abs(s * ar - t['crown_radius_m'])
            e = max(eh, er)
            if e < best_e:
                best_e, best_s = e, s
        scale = float(best_s)
        eh = abs(scale * ah - t['height_m'])
        er = abs(scale * ar - t['crown_radius_m'])
        err_h.append(eh)
        err_r.append(er)
        lng, lat = en_to_lnglat(t['e'], t['n'])
        yaw = (t['id'] * 47.0) % 360.0
        instances.append({
            'tree_id': t['id'],
            'archetype_id': arch['id'],
            'lng': round(lng, 7),
            'lat': round(lat, 7),
            'east_m': round(t['e'], 3),
            'north_m': round(t['n'], 3),
            'ground_m': round(t['z'], 3),
            'rotation_deg': round(yaw, 2),
            'scale': round(scale, 4),
            'height_m_measured': round(t['height_m'], 2),
            'crown_radius_m_measured': round(t['crown_radius_m'], 2),
        })

    worst_h = float(max(err_h))
    worst_r = float(max(err_r))
    worst = max(worst_h, worst_r)
    doc = {
        'authority': 'generated',
        'evidence': 'modelled',
        'measured_source': 'trees.csv',
        'archetype_count': N_ARCHETYPES,
        'instance_count': len(instances),
        'worst_case_dimensional_error_m': round(worst, 3),
        'worst_case_height_error_m': round(worst_h, 3),
        'worst_case_crown_radius_error_m': round(worst_r, 3),
        'error_bound_m': ERROR_BOUND_M,
        'archetypes': archetypes,
        'instances': instances,
        'licence': 'own-work',
        'ez_tree': {
            'package': '@dgreenheck/ez-tree',
            'licence': 'MIT',
            'status': 'preferred generator; Node TLS blocked in this build host — fitted parametric meshes shipped',
        },
    }
    INSTANCES.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    if worst > ERROR_BOUND_M:
        raise SystemExit(f'worst-case error {worst:.2f} m > bound {ERROR_BOUND_M}')
    print(
        f'OK tree instances: {N_ARCHETYPES} archetypes, {len(instances)} rows; '
        f'worst error {worst:.2f} m (H={worst_h:.2f}, R={worst_r:.2f})'
    )


if __name__ == '__main__':
    main()
