"""
C26 — sky events against the real horizon, checked twice.

  Observers: gathering-band centroids + each structure in models.json
  (excluding site-grounds / creek). Horizon altitude from the nearest
  C16 viewpoint profile in horizon.json.

  Flat sunrise/sunset: astronomy-engine SearchRiseSet, cross-checked with
  mourner/suncalc (BSD). True events: sun vs mapped ridge altitude.

    python scripts/sky_events.py
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import astronomy
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from terrain import elevation_lnglat, en_to_lnglat, lnglat_to_en  # noqa: E402

HORIZON = ROOT / 'horizon.json'
OUT = ROOT / 'sky-events.json'
ALIGN = ROOT / 'alignments.geojson'
SUNCALC_CLI = ROOT / 'tools' / 'suncalc_cli.js'
TZ = ZoneInfo('America/Los_Angeles')
YEAR = 2026
DRAW_RADIUS_M = 8000.0
EYE_M = 1.6
# AE SearchRiseSet vs SunCalc civil (−0.833°) typically differ ~1–2 min here
SUNCALC_TIME_TOL_MIN = 2.5
SUNCALC_AZ_TOL_DEG = 0.5

STRUCTURE_SKIP = {'site-grounds', 'creek'}

SEASON_KINDS = (
    'march_equinox',
    'june_solstice',
    'september_equinox',
    'december_solstice',
)
CROSS_QUARTERS = (
    ('imbolc', 2, 1),
    ('beltane', 5, 1),
    ('lunasa', 8, 1),
    ('samhain', 11, 1),
)


def local_label(t: astronomy.Time) -> dict:
    """Local civil time in America/Los_Angeles with DST flag."""
    ut = t.Utc()
    dt = datetime(
        int(ut.year), int(ut.month), int(ut.day),
        int(ut.hour), int(ut.minute), int(ut.second),
        tzinfo=timezone.utc,
    )
    local = dt.astimezone(TZ)
    return {
        'time_local': local.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'time_utc': dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'tz': 'America/Los_Angeles',
        'dst': bool(local.dst()),
        'offset_hours': local.utcoffset().total_seconds() / 3600.0,
    }


def parse_iso_utc(iso: str) -> astronomy.Time:
    dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    jd = dt.timestamp() / 86400.0 + 2440587.5
    return astronomy.Time(jd - 2451545.0)


def horizon_alt(profile: dict, az_deg: float) -> float:
    azs = profile['azimuth_deg']
    alts = profile['altitude_deg']
    az = az_deg % 360.0
    step = azs[1] - azs[0] if len(azs) > 1 else 0.5
    idx = int(round(az / step)) % len(azs)
    return float(alts[idx])


def sun_alt_az(observer, t, refraction=astronomy.Refraction.Normal):
    eq = astronomy.Equator(astronomy.Body.Sun, t, observer, True, True)
    hor = astronomy.Horizon(t, observer, eq.ra, eq.dec, refraction)
    return float(hor.altitude), float(hor.azimuth)


def season_day(year: int, kind: str) -> astronomy.Time:
    seasons = astronomy.Seasons(year)
    return {
        'march_equinox': seasons.mar_equinox,
        'june_solstice': seasons.jun_solstice,
        'september_equinox': seasons.sep_equinox,
        'december_solstice': seasons.dec_solstice,
    }[kind]


def event_calendar_day(year: int, kind: str) -> tuple[int, int, int]:
    if kind in SEASON_KINDS:
        st = season_day(year, kind)
        ut = st.Utc()
        return int(ut.year), int(ut.month), int(ut.day)
    for name, mo, day in CROSS_QUARTERS:
        if name == kind:
            return year, mo, day
    raise KeyError(kind)


def find_ridge_event(observer, profile, t_day: astronomy.Time, rise: bool):
    """Minute scan for when sun clears (rise) or drops behind (set) mapped horizon."""
    ut = t_day.Utc()
    y, mo, d = int(ut.year), int(ut.month), int(ut.day)
    if rise:
        # Pacific morning is ~12–20 UTC; start before earliest winter rise
        t0 = astronomy.Time.Make(y, mo, d, 11, 0, 0)
        prev = None
        for m in range(0, 12 * 60):
            t = t0.AddDays(m / (24.0 * 60.0))
            alt, az = sun_alt_az(observer, t)
            h = horizon_alt(profile, az)
            above = alt >= h
            if prev is False and above:
                return {
                    **local_label(t),
                    'azimuth_deg': round(az, 2),
                    'sun_alt_deg': round(alt, 2),
                    'horizon_alt_deg': round(h, 2),
                }
            prev = above
        return None

    # Sunset: Pacific evening is ~00–04 UTC next day; start mid-afternoon UTC
    t0 = astronomy.Time.Make(y, mo, d, 18, 0, 0)
    prev = None
    for m in range(0, 14 * 60):
        t = t0.AddDays(m / (24.0 * 60.0))
        alt, az = sun_alt_az(observer, t)
        h = horizon_alt(profile, az)
        above = alt >= h
        if prev is True and not above:
            return {
                **local_label(t),
                'azimuth_deg': round(az, 2),
                'sun_alt_deg': round(alt, 2),
                'horizon_alt_deg': round(h, 2),
            }
        prev = above
    return None


def flat_ae(observer, y: int, mo: int, d: int):
    t0 = astronomy.Time.Make(y, mo, d, 0, 0, 0)
    rise = astronomy.SearchRiseSet(
        astronomy.Body.Sun, observer, astronomy.Direction.Rise, t0, 1,
    )
    # Set from noon UTC so we get the evening of the civil day, not previous
    t_noon = astronomy.Time.Make(y, mo, d, 12, 0, 0)
    sett = astronomy.SearchRiseSet(
        astronomy.Body.Sun, observer, astronomy.Direction.Set, t_noon, 1,
    )
    out = {}
    for key, ev in (('sunrise', rise), ('sunset', sett)):
        if ev is None:
            out[key] = None
            continue
        alt, az = sun_alt_az(observer, ev)
        out[key] = {
            **local_label(ev),
            'azimuth_deg': round(az, 2),
            'sun_alt_deg': round(alt, 2),
            '_t': ev,
        }
    return out


def delay_min(true_rec, flat_rec, rise: bool) -> float | None:
    if not true_rec or not flat_rec:
        return None
    t_true = parse_iso_utc(true_rec['time_utc'])
    t_flat = parse_iso_utc(flat_rec['time_utc'])
    # rise: true later → positive delay; set: true earlier → positive "shortening"
    minutes = (t_true.ut - t_flat.ut) * 24.0 * 60.0
    if rise:
        return round(minutes, 1)
    return round(-minutes, 1)


def suncalc_batch(reqs: list[dict]) -> dict[str, dict]:
    proc = subprocess.run(
        ['node', str(SUNCALC_CLI)],
        input=json.dumps(reqs),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f'suncalc_cli failed: {proc.stderr}')
    rows = json.loads(proc.stdout)
    return {r['id']: r for r in rows}


def build_observers(hz: dict) -> list[dict]:
    observers = []
    # gathering band centroids
    gdoc = json.loads((ROOT / 'gathering.geojson').read_text(encoding='utf-8'))
    by: dict[str, list] = defaultdict(list)
    for f in gdoc['features']:
        band = (f.get('properties') or {}).get('band')
        if not band:
            continue
        by[str(band)].append(shape(f['geometry']))
    for band, geoms in sorted(by.items()):
        u = unary_union(geoms)
        c = u.centroid
        observers.append({
            'id': f'gathering_{band}',
            'kind': 'gathering_band',
            'band': band,
            'lng': float(c.x),
            'lat': float(c.y),
        })

    man = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
    for m in man['models']:
        mid = m['id']
        if mid in STRUCTURE_SKIP:
            continue
        origin = m.get('origin')
        if not origin or len(origin) < 2:
            continue
        observers.append({
            'id': f'structure_{mid}',
            'kind': 'structure',
            'structure_id': mid,
            'name': m.get('name') or mid,
            'lng': float(origin[0]),
            'lat': float(origin[1]),
        })

    # assign nearest horizon profile
    vps = hz['viewpoints']
    for obs in observers:
        e, n = lnglat_to_en(obs['lng'], obs['lat'])
        best_name, best_d = None, 1e18
        for name, vp in vps.items():
            ve, vn = lnglat_to_en(vp['lng'], vp['lat'])
            d = math.hypot(e - ve, n - vn)
            if d < best_d:
                best_d, best_name = d, name
        obs['horizon_profile'] = best_name
        obs['horizon_profile_distance_m'] = round(best_d, 1)
        try:
            ground = float(elevation_lnglat(obs['lng'], obs['lat']))
        except Exception:
            ground = float(vps[best_name].get('ground_m') or 420.0)
        obs['ground_m'] = round(ground, 2)
        obs['eye_m'] = EYE_M
    return observers


def event_kinds() -> list[str]:
    return list(SEASON_KINDS) + [n for n, _, _ in CROSS_QUARTERS]


def bearing_en(e0, n0, e1, n1) -> float:
    return (math.degrees(math.atan2(e1 - e0, n1 - n0)) + 360.0) % 360.0


def alignment_line(lng, lat, az_deg, dist_m=DRAW_RADIUS_M):
    e0, n0 = lnglat_to_en(lng, lat)
    rad = math.radians(az_deg)
    e1 = e0 + dist_m * math.sin(rad)
    n1 = n0 + dist_m * math.cos(rad)
    return [list(en_to_lnglat(e0, n0)), list(en_to_lnglat(e1, n1))], dist_m


def main():
    if not HORIZON.exists():
        raise SystemExit('run scripts/horizon.py first')
    if not SUNCALC_CLI.exists():
        raise SystemExit('missing tools/suncalc_cli.js')
    hz = json.loads(HORIZON.read_text(encoding='utf-8'))
    observers = build_observers(hz)
    kinds = event_kinds()

    # SunCalc batch for every observer × event day
    sc_reqs = []
    for obs in observers:
        for kind in kinds:
            y, mo, d = event_calendar_day(YEAR, kind)
            sc_reqs.append({
                'id': f"{obs['id']}:{kind}",
                'lat': obs['lat'],
                'lng': obs['lng'],
                'year': y, 'month': mo, 'day': d,
            })
    print(f'suncalc batch {len(sc_reqs)} …')
    sc_map = suncalc_batch(sc_reqs)

    out_obs = []
    align_feats = []
    delays_summary = {}
    worst_dt = 0.0
    worst_daz = 0.0
    cross_fails = 0

    for obs in observers:
        profile = hz['viewpoints'][obs['horizon_profile']]
        ae_obs = astronomy.Observer(
            obs['lat'], obs['lng'], obs['ground_m'] + obs['eye_m'],
        )
        events = {}
        for kind in kinds:
            y, mo, d = event_calendar_day(YEAR, kind)
            flat = flat_ae(ae_obs, y, mo, d)
            t_day = astronomy.Time.Make(y, mo, d, 12, 0, 0)
            true_rise = find_ridge_event(ae_obs, profile, t_day, True)
            true_set = find_ridge_event(ae_obs, profile, t_day, False)

            sc = sc_map.get(f"{obs['id']}:{kind}") or {}
            cross = {}
            for half, sc_key in (('sunrise', 'sunrise'), ('sunset', 'sunset')):
                ae_rec = flat.get(half)
                sc_rec = sc.get(sc_key)
                if not ae_rec or not sc_rec:
                    cross[half] = {'ok': False, 'reason': 'missing'}
                    cross_fails += 1
                    continue
                # Δt
                t_ae = ae_rec['_t']
                sc_ut = sc_rec['ms'] / 86400000.0 + 2440587.5 - 2451545.0
                dt_min = abs((t_ae.ut - sc_ut) * 24.0 * 60.0)
                daz = ((ae_rec['azimuth_deg'] - sc_rec['az_north_deg'] + 180) % 360) - 180
                daz = abs(daz)
                worst_dt = max(worst_dt, dt_min)
                worst_daz = max(worst_daz, daz)
                ok = dt_min <= SUNCALC_TIME_TOL_MIN and daz <= SUNCALC_AZ_TOL_DEG
                if not ok:
                    cross_fails += 1
                cross[half] = {
                    'ok': ok,
                    'dt_min': round(dt_min, 3),
                    'daz_deg': round(daz, 3),
                    'suncalc_time_utc': sc_rec['iso'],
                    'suncalc_azimuth_deg': round(sc_rec['az_north_deg'], 2),
                }

            def strip(rec):
                if not rec:
                    return None
                return {k: v for k, v in rec.items() if k != '_t'}

            d_rise = (
                delay_min(true_rise, strip(flat.get('sunrise')), True)
                if flat.get('sunrise') and true_rise else None
            )
            d_set = (
                delay_min(true_set, strip(flat.get('sunset')), False)
                if flat.get('sunset') and true_set else None
            )

            entry = {
                'evidence': 'modelled',
                'calendar_day': f'{y:04d}-{mo:02d}-{d:02d}',
                'cross_quarter': kind not in SEASON_KINDS,
                'sunrise': {
                    'true': true_rise,
                    'flat': strip(flat.get('sunrise')),
                    'delay_min': d_rise,
                    'suncalc_crosscheck': cross.get('sunrise'),
                },
                'sunset': {
                    'true': true_set,
                    'flat': strip(flat.get('sunset')),
                    'delay_min': d_set,
                    'suncalc_crosscheck': cross.get('sunset'),
                },
            }
            events[kind] = entry

            if kind in ('june_solstice', 'december_solstice') and d_rise is not None:
                delays_summary[f"{obs['id']}:{kind}"] = d_rise

            for half, true_rec, delay in (
                ('sunrise', true_rise, d_rise),
                ('sunset', true_set, d_set),
            ):
                if not true_rec:
                    continue
                az = float(true_rec['azimuth_deg'])
                coords, dist = alignment_line(obs['lng'], obs['lat'], az)
                align_feats.append({
                    'type': 'Feature',
                    'properties': {
                        'observer_id': obs['id'],
                        'event': f'{kind}_{half}',
                        'azimuth_deg': az,
                        'delay_min': delay,
                        'true_time': true_rec['time_local'],
                        'draw_radius_m': dist,
                        'horizon_profile': obs['horizon_profile'],
                    },
                    'geometry': {'type': 'LineString', 'coordinates': coords},
                })

        out_obs.append({
            **{k: obs[k] for k in obs},
            'events': events,
        })
        print(f"  {obs['id']}: profile={obs['horizon_profile']} d={obs['horizon_profile_distance_m']}m")

    doc = {
        'authority': 'derived',
        'evidence': 'modelled',
        'method': (
            'astronomy-engine sun vs nearest horizon.json altitude profile; '
            'flat rise/set via SearchRiseSet; independent flat cross-check with '
            'mourner/suncalc (BSD); local times America/Los_Angeles (DST aware)'
        ),
        'inputs': [
            'horizon.json',
            'gathering.geojson',
            'models.json',
            'astronomy-engine (MIT)',
            'tools/suncalc.js (mourner/suncalc BSD-2-Clause)',
        ],
        'timezone': 'America/Los_Angeles',
        'timezone_note': (
            'time_local includes numeric offset; dst=true means Pacific Daylight Time, '
            'dst=false means Pacific Standard Time'
        ),
        'year': YEAR,
        'draw_radius_m': DRAW_RADIUS_M,
        'suncalc_crosscheck': {
            'time_tol_min': SUNCALC_TIME_TOL_MIN,
            'az_tol_deg': SUNCALC_AZ_TOL_DEG,
            'worst_dt_min': round(worst_dt, 3),
            'worst_daz_deg': round(worst_daz, 3),
            'failures': cross_fails,
            'note': (
                'AE SearchRiseSet and SunCalc civil sunrise (−0.833°) differ by about '
                '1–2 minutes systematically; azimuth at each library’s event agrees within 0.5°'
            ),
        },
        'ridge_delay_sunrise_minutes': delays_summary,
        'observers': out_obs,
    }
    OUT.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')

    align_doc = {
        'type': 'FeatureCollection',
        'name': 'alignments',
        'properties': {
            'authority': 'derived',
            'evidence': 'modelled',
            'generator': 'scripts/sky_events.py',
            'source': 'sky-events.json',
            'draw_radius_m': DRAW_RADIUS_M,
            'note': (
                'Each LineString runs from the observer along the true sunrise/sunset '
                f'azimuth to the published horizon draw radius ({DRAW_RADIUS_M:.0f} m), '
                'matching horizon.geojson convention.'
            ),
        },
        'features': align_feats,
    }
    ALIGN.write_text(json.dumps(align_doc, indent=2) + '\n', encoding='utf-8')
    print(f'wrote {OUT} observers={len(out_obs)} alignments={len(align_feats)}')
    print(f'suncalc worst dt={worst_dt:.3f} min daz={worst_daz:.3f} fails={cross_fails}')


if __name__ == '__main__':
    main()
