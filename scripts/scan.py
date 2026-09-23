"""
C14.2 — place a phone Gaussian splat on the pack DEM.

  Input: PLY (or SPZ via @playcanvas/splat-transform), zone id, and >=3
  ground-control pairs: scan-local xyz ↔ pack-frame east/north (height from DEM).

  Privacy: writes binary scan data only under scans/ (git-ignored). The repo
  keeps scans.json placement rows with url: null until private storage is filled in.

  Placement convention (must match the world):
    centre on mid of 2nd–98th percentile (x, z);
    rest base (2nd percentile of y) on the DEM;
    turn clockwise by turn_deg; scale; then add lift_m.

    python scripts/scan.py --file path.ply --zone z001 \\
        --gcp 0,0,0,200,250 --gcp 10,0,0,210,250 --gcp 0,0,10,200,260

    python scripts/scan.py --synthetic --zone z-synth   # C14.3 helper
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
from plyfile import PlyData, PlyElement
from shapely.geometry import Point, Polygon, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from terrain import elevation_en, en_to_lnglat, lnglat_to_en  # noqa: E402

SCANS_DIR = ROOT / 'scans'
SCANS_JSON = ROOT / 'scans.json'
PLAN = ROOT / 'capture-plan.geojson'


# ---------- I/O ----------

def ensure_ply(path: Path) -> Path:
    """Return a PLY path; convert SPZ via npx @playcanvas/splat-transform if needed."""
    if path.suffix.lower() == '.ply':
        return path
    if path.suffix.lower() != '.spz':
        raise SystemExit(f'unsupported scan format: {path.suffix} (want .ply or .spz)')
    out = path.with_suffix('.ply')
    cmd = ['npx', '-y', '@playcanvas/splat-transform', str(path), str(out)]
    print('converting SPZ -> PLY:', ' '.join(cmd))
    subprocess.run(cmd, check=True)
    return out


def read_ply_xyz(path: Path) -> tuple[np.ndarray, np.ndarray | None]:
    """Return (N,3) xyz and optional opacity (N,)."""
    ply = PlyData.read(str(path))
    v = ply['vertex']
    names = set(v.data.dtype.names)
    x = np.asarray(v['x'], dtype=np.float64)
    y = np.asarray(v['y'], dtype=np.float64)
    z = np.asarray(v['z'], dtype=np.float64)
    xyz = np.column_stack([x, y, z])
    opac = None
    for key in ('opacity', 'alpha', 'a'):
        if key in names:
            opac = np.asarray(v[key], dtype=np.float64)
            break
    return xyz, opac


def write_ply_xyz(path: Path, xyz: np.ndarray, opac: np.ndarray | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    n = xyz.shape[0]
    if opac is None:
        dtype = [('x', 'f4'), ('y', 'f4'), ('z', 'f4')]
        arr = np.empty(n, dtype=dtype)
        arr['x'], arr['y'], arr['z'] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    else:
        dtype = [('x', 'f4'), ('y', 'f4'), ('z', 'f4'), ('opacity', 'f4')]
        arr = npempty(n, dtype=dtype)
        arr['x'], arr['y'], arr['z'] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
        arr['opacity'] = opac
    PlyData([PlyElement.describe(arr, 'vertex')], text=False).write(str(path))


# ---------- transforms ----------

def stand_upright(xyz: np.ndarray) -> np.ndarray:
    """Phone captures are often y-down; flip so +y is up if the cloud looks inverted."""
    # Heuristic: if the majority of the vertical span is below the median of x/z
    # and y decreases "up the hill", leave alone. Brief: "stand it upright (y-down)".
    # Always map capture y-down → y-up by negating y when the cloud's y mean of
    # upper half is lower than lower half in value order.
    out = xyz.copy()
    out[:, 1] *= -1.0
    return out


def umeyama(src: np.ndarray, dst: np.ndarray, with_scale: bool = True):
    """Similarity transform mapping src (N,3) → dst (N,3). Returns R, t, s, rms."""
    assert src.shape == dst.shape and src.shape[0] >= 3
    mu_s = src.mean(axis=0)
    mu_d = dst.mean(axis=0)
    X = src - mu_s
    Y = dst - mu_d
    var_s = (X ** 2).sum() / src.shape[0]
    cov = (Y.T @ X) / src.shape[0]
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1
    R = U @ S @ Vt
    s = 1.0 if not with_scale else float(np.trace(np.diag(D) @ S) / var_s)
    t = mu_d - s * R @ mu_s
    fitted = (s * (R @ src.T)).T + t
    rms = float(np.sqrt(((fitted - dst) ** 2).sum(axis=1).mean()))
    return R, t, s, rms


def apply_sim(xyz: np.ndarray, R, t, s) -> np.ndarray:
    return (s * (R @ xyz.T)).T + t


def icp_to_dem(xyz_en: np.ndarray, max_iter: int = 12, max_dist: float = 2.0):
    """Refine vertical + small horizontal shift by matching ground points to DEM."""
    pts = xyz_en.copy()
    # ground candidates: lowest 15% of y in local neighbourhood — use global low band
    y = pts[:, 1]
    thr = np.percentile(y, 20)
    ground = pts[y <= thr]
    if ground.shape[0] < 20:
        ground = pts
    total_shift = np.zeros(3)
    for _ in range(max_iter):
        dem_z = np.array([elevation_en(float(p[0]), float(p[2])) for p in ground])
        # our frame: x=east, y=up, z=south? Pack EN uses east, north.
        # After placement we use x=east, y=up, z=north (right-handed, north = +z).
        dy = dem_z - ground[:, 1]
        # reject outliers
        ok = np.abs(dy) < max_dist
        if ok.sum() < 10:
            break
        shift = np.array([0.0, float(np.median(dy[ok])), 0.0])
        if abs(shift[1]) < 0.005:
            break
        pts += shift
        ground = ground + shift
        total_shift += shift
    return pts, total_shift


# ---------- zone / placement ----------

def zone_polygon(zone_id: str) -> Polygon:
    if not PLAN.exists():
        raise SystemExit('missing capture-plan.geojson — run scripts/capture-plan.py first')
    doc = json.loads(PLAN.read_text(encoding='utf-8'))
    for f in doc['features']:
        if f['properties']['id'] == zone_id:
            return Polygon([lnglat_to_en(a, b) for a, b in f['geometry']['coordinates'][0]])
    raise SystemExit(f'zone {zone_id} not in capture-plan.geojson')


def placement_params(xyz_eny: np.ndarray) -> dict:
    """Compute turn/scale/lift defaults from a cloud already in pack EN (x east, y up, z north)."""
    x, y, z = xyz_eny[:, 0], xyz_eny[:, 1], xyz_eny[:, 2]
    x0, x1 = np.percentile(x, [2, 98])
    z0, z1 = np.percentile(z, [2, 98])
    y_base = float(np.percentile(y, 2))
    cx, cz = 0.5 * (x0 + x1), 0.5 * (z0 + z1)
    # ground at centre
    ground = elevation_en(cx, cz)
    return {
        'centre_e': float(cx),
        'centre_n': float(cz),
        'base_y': y_base,
        'ground_m': float(ground),
        'lift_m': float(ground - y_base),
    }


def crop_and_clean(xyz: np.ndarray, opac, poly: Polygon, buffer_m: float = 2.0):
    """Keep points inside zone+buffer; drop floaters far from DEM / low opacity."""
    keep = []
    for i, p in enumerate(xyz):
        if not poly.buffer(buffer_m).contains(Point(p[0], p[2])):
            continue
        try:
            dem = elevation_en(float(p[0]), float(p[2]))
        except FileNotFoundError:
            continue
        if p[1] > dem + 25.0 or p[1] < dem - 3.0:
            continue
        if opac is not None and opac[i] < 0.05:
            continue
        keep.append(i)
    idx = np.array(keep, dtype=int)
    if idx.size == 0:
        raise SystemExit('no points left after crop/clean')
    out_o = opac[idx] if opac is not None else None
    return xyz[idx], out_o


def load_or_init_scans() -> dict:
    if SCANS_JSON.exists():
        return json.loads(SCANS_JSON.read_text(encoding='utf-8'))
    return {
        'authority': 'derived',
        'evidence': 'measured',
        'note': 'Placement rows only. Binary scans live in private storage; scans/ is git-ignored.',
        'placement': (
            'centre on mid of 2nd–98th pct (x,z); rest base (2nd pct y) on DEM; '
            'turn clockwise turn_deg; scale; add lift_m'
        ),
        'scans': [],
    }


def upsert_row(doc: dict, row: dict):
    rows = doc.setdefault('scans', [])
    for i, r in enumerate(rows):
        if r.get('zone') == row['zone']:
            rows[i] = row
            break
    else:
        rows.append(row)
    SCANS_JSON.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')


# ---------- synthetic (C14.3) ----------

def build_synthetic(zone_id: str = 'z-synth') -> tuple[Path, list, dict]:
    """Sample DEM into a local y-down cloud with a known similarity; return path + gcps + truth."""
    # use a fixed 20 m patch near parcel centre
    e_c, n_c = 300.0, 250.0
    half = 8.0
    xs = np.linspace(e_c - half, e_c + half, 40)
    zs = np.linspace(n_c - half, n_c + half, 40)
    EE, NN = np.meshgrid(xs, zs)
    YY = np.array([elevation_en(float(e), float(n)) for e, n in zip(EE.ravel(), NN.ravel())])
    # pack EN cloud (x east, y up, z north)
    cloud = np.column_stack([EE.ravel(), YY, NN.ravel()])
    # known transform to "scan local" (then we invert): scale 1.05, yaw 15°, shift
    ang = math.radians(15.0)
    R = np.array([
        [math.cos(ang), 0, math.sin(ang)],
        [0, 1, 0],
        [-math.sin(ang), 0, math.cos(ang)],
    ])
    s_true = 1.05
    t_true = np.array([12.0, -3.0, -8.0])
    # local = inv(sim) * world; for y-down capture, negate y after
    # world = s R local_up + t  => local_up = R.T (world - t) / s
    local_up = (R.T @ (cloud - t_true).T).T / s_true
    local = local_up.copy()
    local[:, 1] *= -1.0  # y-down

    SCANS_DIR.mkdir(parents=True, exist_ok=True)
    path = SCANS_DIR / f'{zone_id}.ply'
    write_ply_xyz(path, local)

    # three GCPs on the ground corners (scan local after stand-up = local_up)
    corners_w = np.array([
        [e_c - half, elevation_en(e_c - half, n_c - half), n_c - half],
        [e_c + half, elevation_en(e_c + half, n_c - half), n_c - half],
        [e_c - half, elevation_en(e_c - half, n_c + half), n_c + half],
        [e_c + half, elevation_en(e_c + half, n_c + half), n_c + half],
    ])
    corners_local_up = (R.T @ (corners_w - t_true).T).T / s_true
    # GCP pairs: scan-local (y-down) xyz, pack e,n  (height from DEM in fit)
    gcps = []
    for loc, w in zip(corners_local_up[:3], corners_w[:3]):
        scan_ydown = np.array([loc[0], -loc[1], loc[2]])
        gcps.append((float(scan_ydown[0]), float(scan_ydown[1]), float(scan_ydown[2]),
                     float(w[0]), float(w[2])))
    truth = {'R': R.tolist(), 't': t_true.tolist(), 's': s_true, 'centre_en': [e_c, n_c]}
    return path, gcps, truth


def place(path: Path, zone_id: str, gcps: list[tuple], synthetic_truth=None) -> dict:
    ply = ensure_ply(path)
    xyz, opac = read_ply_xyz(ply)
    xyz = stand_upright(xyz)

    # GCP: scan local (after stand-up) → pack (e, elev, n)
    src = []
    dst = []
    for sx, sy, sz, e, n in gcps:
        # stand_upright already negated y on the cloud; GCPs were given in capture
        # (y-down) coords — apply same flip
        src.append([sx, -sy, sz])
        elev = elevation_en(e, n)
        dst.append([e, elev, n])
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    R, t, s, rms = umeyama(src, dst, with_scale=True)
    xyz_w = apply_sim(xyz, R, t, s)
    xyz_w, shift = icp_to_dem(xyz_w)
    t = t + shift
    # recompute rms on GCPs after ICP vertical
    fitted = apply_sim(src, R, t, s)
    rms = float(np.sqrt(((fitted - dst) ** 2).sum(axis=1).mean()))

    # zone crop — synthetic zone may not be in plan; use bbox of cloud
    if zone_id.startswith('z-synth') or zone_id == 'z-synth':
        x0, x1 = np.percentile(xyz_w[:, 0], [1, 99])
        z0, z1 = np.percentile(xyz_w[:, 2], [1, 99])
        poly = Polygon([(x0 - 2, z0 - 2), (x1 + 2, z0 - 2), (x1 + 2, z1 + 2), (x0 - 2, z1 + 2)])
    else:
        poly = zone_polygon(zone_id)

    xyz_w, opac = crop_and_clean(xyz_w, opac, poly)
    params = placement_params(xyz_w)

    # write cleaned cloud in scan-local centred form for the world loader:
    # subtract centre, subtract base_y so base sits at 0; world applies turn/scale/lift
    centred = xyz_w.copy()
    centred[:, 0] -= params['centre_e']
    centred[:, 2] -= params['centre_n']
    centred[:, 1] -= params['base_y']

    out_ply = SCANS_DIR / f'{zone_id}.ply'
    write_ply_xyz(out_ply, centred, opac)
    # optional SPZ — skip if tool missing
    out_spz = SCANS_DIR / f'{zone_id}.spz'
    try:
        subprocess.run(
            ['npx', '-y', '@playcanvas/splat-transform', str(out_ply), str(out_spz)],
            check=True, capture_output=True,
        )
        bytes_out = out_spz.stat().st_size
        file_hint = str(out_spz.relative_to(ROOT)).replace('\\', '/')
    except Exception:
        bytes_out = out_ply.stat().st_size
        file_hint = str(out_ply.relative_to(ROOT)).replace('\\', '/')

    lng, lat = en_to_lnglat(params['centre_e'], params['centre_n'])
    # turn from R: clockwise compass degrees about vertical
    # R maps local to world; yaw about y: atan2(R[0,2], R[0,0]) etc.
    yaw = math.degrees(math.atan2(R[0, 2], R[0, 0]))  # CCW from +x
    turn_deg = (-yaw) % 360.0  # clockwise

    row = {
        'zone': zone_id,
        'lng': round(lng, 7),
        'lat': round(lat, 7),
        'turn_deg': round(turn_deg, 3),
        'scale': round(float(s), 6),
        'lift_m': round(params['lift_m'], 4),
        'rms_m': round(rms, 4),
        'splats': int(centred.shape[0]),
        'bytes': int(bytes_out),
        'url': None,
        'local_file': file_hint,
    }
    if synthetic_truth is not None:
        row['synthetic'] = True
        row['truth_s'] = synthetic_truth['s']

    doc = load_or_init_scans()
    upsert_row(doc, row)
    print(f'OK scan {zone_id}: rms={rms:.4f} m  splats={row["splats"]}  lift={row["lift_m"]}')
    return row


def parse_gcp(s: str):
    parts = [float(x) for x in s.split(',')]
    if len(parts) != 5:
        raise argparse.ArgumentTypeError('GCP must be sx,sy,sz,east,north')
    return tuple(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--file', type=Path, help='PLY or SPZ scan')
    ap.add_argument('--zone', required=True, help='zone id from capture-plan (or z-synth)')
    ap.add_argument('--gcp', action='append', type=parse_gcp, default=[],
                    help='scan-local sx,sy,sz,east,north (repeat >=3)')
    ap.add_argument('--synthetic', action='store_true', help='build and place a DEM-based synthetic scan')
    args = ap.parse_args()

    if args.synthetic:
        path, gcps, truth = build_synthetic(args.zone)
        row = place(path, args.zone, gcps, synthetic_truth=truth)
        # also write truth for the check
        (SCANS_DIR / f'{args.zone}-truth.json').write_text(
            json.dumps(truth, indent=2) + '\n', encoding='utf-8',
        )
        return row

    if not args.file:
        raise SystemExit('--file is required unless --synthetic')
    if len(args.gcp) < 3:
        raise SystemExit('need at least 3 --gcp pairs')
    return place(args.file, args.zone, args.gcp)


if __name__ == '__main__':
    main()
