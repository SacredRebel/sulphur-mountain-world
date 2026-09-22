"""
C16.1 — sky events against the real horizon (astronomy-engine).

  For each viewpoint in horizon.json and years 2026-2030:
    - June/December solstices and both equinoxes: az + local time when the
      sun first clears / last touches the real horizon
    - Moon rise/set extremes at next minor standstill and 2024-25 major standstill
  Cross-quarter days marked evidence=traditional only.

    python scripts/sky_events.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import astronomy

ROOT = Path(__file__).resolve().parents[1]
HORIZON = ROOT / 'horizon.json'
OUT = ROOT / 'sky-events.json'
TZ_OFFSET_H = -7  # America/Los_Angeles PDT approx for summer; report as UTC-7 label


def local_iso(t: astronomy.Time) -> str:
    from datetime import datetime, timedelta, timezone
    # astronomy Time.Utc() returns a tuple (year, month, day, hour, minute, second)
    ut = t.Utc()
    if isinstance(ut, tuple):
        y, mo, d, h, mi, s = ut[:6]
        dt = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), tzinfo=timezone.utc)
    elif hasattr(ut, 'year'):
        dt = datetime(ut.year, ut.month, ut.day, ut.hour, ut.minute, int(ut.second), tzinfo=timezone.utc)
    else:
        return str(t)
    local = dt + timedelta(hours=TZ_OFFSET_H)
    return local.strftime('%Y-%m-%dT%H:%M:%S') + ' UTC-7'


def horizon_alt(profile: dict, az_deg: float) -> float:
    azs = profile['azimuth_deg']
    alts = profile['altitude_deg']
    # wrap
    az = az_deg % 360.0
    # nearest
    step = azs[1] - azs[0] if len(azs) > 1 else 0.5
    idx = int(round(az / step)) % len(azs)
    return float(alts[idx])


def sun_alt_az(observer, t):
    eq = astronomy.Equator(astronomy.Body.Sun, t, observer, True, True)
    hor = astronomy.Horizon(t, observer, eq.ra, eq.dec, astronomy.Refraction.Normal)
    return float(hor.altitude), float(hor.azimuth)


def moon_alt_az(observer, t):
    eq = astronomy.Equator(astronomy.Body.Moon, t, observer, True, True)
    hor = astronomy.Horizon(t, observer, eq.ra, eq.dec, astronomy.Refraction.Normal)
    return float(hor.altitude), float(hor.azimuth)


def find_clear_time(observer, profile, t0: astronomy.Time, direction=+1, hours=18):
    """Scan for when sun altitude first exceeds (direction=+1) or last drops below (-1) horizon."""
    # Sample every 1 minute
    best = None
    prev_above = None
    for m in range(0, int(hours * 60)):
        t = t0.AddDays(m / (24.0 * 60.0) * direction)
        # always forward from t0 for rise; for set start afternoon
        if direction < 0:
            t = t0.AddDays(-m / (24.0 * 60.0))
        alt, az = sun_alt_az(observer, t)
        h = horizon_alt(profile, az)
        above = alt >= h
        if prev_above is None:
            prev_above = above
            continue
        if direction > 0 and (not prev_above) and above:
            return {
                'time_local': local_iso(t),
                'azimuth_deg': round(az, 2),
                'sun_alt_deg': round(alt, 2),
                'horizon_alt_deg': round(h, 2),
            }
        if direction < 0 and prev_above and (not above):
            # scanning backward from evening — first crossing is last touch
            best = {
                'time_local': local_iso(t),
                'azimuth_deg': round(az, 2),
                'sun_alt_deg': round(alt, 2),
                'horizon_alt_deg': round(h, 2),
            }
            # keep going to find the earliest backward = last evening contact when scanning from night
        prev_above = above
    if direction < 0 and best:
        return best
    # forward set scan: start midday, find last above→below
    if direction < 0:
        t_mid = t0
        prev = None
        last = None
        for m in range(0, int(hours * 60)):
            t = t_mid.AddDays(m / (24.0 * 60.0))
            alt, az = sun_alt_az(observer, t)
            h = horizon_alt(profile, az)
            above = alt >= h
            if prev is True and not above:
                last = {
                    'time_local': local_iso(t),
                    'azimuth_deg': round(az, 2),
                    'sun_alt_deg': round(alt, 2),
                    'horizon_alt_deg': round(h, 2),
                }
            prev = above
        return last
    return None


def flat_rise_time(observer, t_day: astronomy.Time):
    rise = astronomy.SearchRiseSet(astronomy.Body.Sun, observer, astronomy.Direction.Rise, t_day, 1)
    return rise


def season_day(year: int, kind: str) -> astronomy.Time:
    # Approximate calendar dates; refine with astronomy Seasons
    seasons = astronomy.Seasons(year)
    if kind == 'march_equinox':
        return seasons.mar_equinox
    if kind == 'june_solstice':
        return seasons.jun_solstice
    if kind == 'september_equinox':
        return seasons.sep_equinox
    if kind == 'december_solstice':
        return seasons.dec_solstice
    raise KeyError(kind)


def delay_minutes(observer, profile, season_t: astronomy.Time) -> float | None:
    """Minutes ridges delay sunrise vs flat astronomical horizon."""
    ut = season_t.Utc()
    t0 = astronomy.Time.Make(ut.year, ut.month, ut.day, 0, 0, 0)
    flat = astronomy.SearchRiseSet(
        astronomy.Body.Sun, observer, astronomy.Direction.Rise, t0, 1,
    )
    if flat is None:
        return None
    # Scan from flat rise onward up to 4 hours (ridges can delay a lot in winter)
    for m in range(0, 240):
        t = flat.AddDays(m / (24.0 * 60.0))
        alt, az = sun_alt_az(observer, t)
        if alt >= horizon_alt(profile, az):
            return round((t.ut - flat.ut) * 24 * 60, 1)
    return None


def moon_standstill_extremes(observer, profile, label: str, center: astronomy.Time):
    """Sample moon rise/set az over ~1 month around center; report min/max rise az."""
    rises, sets = [], []
    for d in range(-20, 21):
        t0 = center.AddDays(d)
        ut = t0.Utc()
        t_day = astronomy.Time.Make(ut.year, ut.month, ut.day, 0, 0, 0)
        for kind, sign, bucket in (('rise', +1, rises), ('set', -1, sets)):
            ev = astronomy.SearchRiseSet(astronomy.Body.Moon, observer, astronomy.Direction.Rise if sign>0 else astronomy.Direction.Set, t_day, 1)
            if ev is None:
                continue
            alt, az = moon_alt_az(observer, ev)
            h = horizon_alt(profile, az)
            # if moon clears real horizon near this time, keep az
            bucket.append({'azimuth_deg': round(az, 2), 'time_local': local_iso(ev), 'horizon_alt_deg': round(h, 2)})
    def extremes(bucket):
        if not bucket:
            return None
        azs = [b['azimuth_deg'] for b in bucket]
        return {
            'min_az': min(bucket, key=lambda b: b['azimuth_deg']),
            'max_az': max(bucket, key=lambda b: b['azimuth_deg']),
            'n': len(bucket),
        }
    return {'label': label, 'rise': extremes(rises), 'set': extremes(sets)}


def traditional_cross_quarters(year: int):
    # Approximate midpoints — evidence traditional only
    return [
        {'name': 'imbolc', 'approx_date': f'{year}-02-01', 'evidence': 'traditional'},
        {'name': 'beltane', 'approx_date': f'{year}-05-01', 'evidence': 'traditional'},
        {'name': 'lunasa', 'approx_date': f'{year}-08-01', 'evidence': 'traditional'},
        {'name': 'samhain', 'approx_date': f'{year}-11-01', 'evidence': 'traditional'},
    ]


def main():
    if not HORIZON.exists():
        raise SystemExit('run scripts/horizon.py first')
    hz = json.loads(HORIZON.read_text(encoding='utf-8'))
    years = list(range(2026, 2031))
    out_vps = {}
    delays = {}

    for name, profile in hz['viewpoints'].items():
        observer = astronomy.Observer(profile['lat'], profile['lng'], profile.get('ground_m', 0) + profile.get('eye_m', 1.6))
        seasons_out = {}
        for year in years:
            for kind in ('march_equinox', 'june_solstice', 'september_equinox', 'december_solstice'):
                st = season_day(year, kind)
                ut = st.Utc()
                t_morn = astronomy.Time.Make(ut.year, ut.month, ut.day, 5, 0, 0)
                t_noon = astronomy.Time.Make(ut.year, ut.month, ut.day, 19, 0, 0)
                rise = find_clear_time(observer, profile, t_morn, +1, 10)
                # set: scan forward from afternoon
                set_ = None
                prev = None
                for m in range(0, 600):
                    t = t_noon.AddDays(m / (24.0 * 60.0))
                    alt, az = sun_alt_az(observer, t)
                    h = horizon_alt(profile, az)
                    above = alt >= h
                    if prev is True and not above:
                        set_ = {
                            'time_local': local_iso(t),
                            'azimuth_deg': round(az, 2),
                            'sun_alt_deg': round(alt, 2),
                            'horizon_alt_deg': round(h, 2),
                        }
                        break
                    prev = above
                seasons_out.setdefault(str(year), {})[kind] = {
                    'evidence': 'measured',
                    'sunrise': rise,
                    'sunset': set_,
                }
                if year == 2026 and kind in ('june_solstice', 'december_solstice'):
                    dly = delay_minutes(observer, profile, st)
                    delays[f'{name}:{kind}'] = dly

        # Moon standstills: major ~2024-25, next minor ~2034 — brief asks next minor and 2024-25 major
        major = moon_standstill_extremes(
            observer, profile, 'major_standstill_2024_25',
            astronomy.Time.Make(2025, 3, 15, 0, 0, 0),
        )
        minor = moon_standstill_extremes(
            observer, profile, 'next_minor_standstill_approx_2034',
            astronomy.Time.Make(2034, 3, 15, 0, 0, 0),
        )
        out_vps[name] = {
            'lng': profile['lng'],
            'lat': profile['lat'],
            'seasons': seasons_out,
            'moon_standstills': {'major_2024_25': major, 'minor_next': minor},
            'cross_quarters_traditional': traditional_cross_quarters(2026),
        }
        print(f'{name}: delays { {k: delays[k] for k in delays if k.startswith(name)} }')

    doc = {
        'authority': 'derived',
        'evidence': 'measured',
        'method': (
            'astronomy-engine sun/moon positions vs horizon.json altitude profile; '
            'local times as UTC-7; cross-quarters traditional only'
        ),
        'inputs': ['horizon.json', 'astronomy-engine (MIT)'],
        'timezone_display': 'UTC-7',
        'ridge_delay_sunrise_minutes_2026': delays,
        'viewpoints': out_vps,
    }
    OUT.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    print(f'wrote {OUT}')


if __name__ == '__main__':
    main()
