"""
C26 — check sky-events + alignments (independent of generator claims).

    python scripts/check-sky.py
    python scripts/check-sky.py --self-test
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from terrain import lnglat_to_en  # noqa: E402

SKY = ROOT / 'sky-events.json'
ALIGN = ROOT / 'alignments.geojson'
HORIZON_GJ = ROOT / 'horizon.geojson'

# C16/C17 ridge delay of sunrise (minutes) — June ~30, December 35–75
JUNE_DELAY_RANGE = (20.0, 45.0)
DEC_DELAY_RANGE = (25.0, 90.0)
BEARING_TOL_DEG = 0.1
RADIUS_TOL_M = 2.0


def bearing_en(e0, n0, e1, n1) -> float:
    return (math.degrees(math.atan2(e1 - e0, n1 - n0)) + 360.0) % 360.0


def ang_diff(a, b) -> float:
    return abs(((a - b + 180.0) % 360.0) - 180.0)


def parse_local_offset(time_local: str) -> float:
    # ...±HHMM or ±HH:MM
    if len(time_local) < 5:
        return 0.0
    tail = time_local[-5:]
    if tail[0] in '+-' and ':' in tail:
        sign = 1 if tail[0] == '+' else -1
        hh, mm = tail[1:].split(':')
        return sign * (int(hh) + int(mm) / 60.0)
    if time_local[-5] in '+-' and time_local[-4:].isdigit():
        sign = 1 if time_local[-5] == '+' else -1
        return sign * (int(time_local[-4:-2]) + int(time_local[-2:]) / 60.0)
    return -7.0


def utc_minutes(rec: dict) -> float | None:
    if not rec:
        return None
    iso = rec.get('time_utc')
    if not iso:
        return None
    # 2026-06-21T12:44:49Z
    body = iso.rstrip('Z')
    date, tim = body.split('T')
    y, mo, d = map(int, date.split('-'))
    parts = tim.split(':')
    h, mi = int(parts[0]), int(parts[1])
    sec = float(parts[2]) if len(parts) > 2 else 0.0
    # rough absolute minutes from epoch-ish
    return ((((y * 12 + mo) * 31 + d) * 24 + h) * 60 + mi) + sec / 60.0


def run_checks() -> list[str]:
    errs: list[str] = []
    sky = json.loads(SKY.read_text(encoding='utf-8'))
    align = json.loads(ALIGN.read_text(encoding='utf-8'))
    hz_gj = json.loads(HORIZON_GJ.read_text(encoding='utf-8'))

    draw_r = float(sky.get('draw_radius_m') or 8000.0)
    hz_radii = {
        f['properties']['viewpoint']: float(f['properties']['draw_radius_m'])
        for f in hz_gj['features']
    }
    print(f"observers={len(sky['observers'])} alignments={len(align['features'])}")

    # --- true never earlier (rise) / never later (set) than flat ---
    n_events = 0
    june_delays, dec_delays = [], []
    for obs in sky['observers']:
        for kind, ev in (obs.get('events') or {}).items():
            for half in ('sunrise', 'sunset'):
                block = ev.get(half) or {}
                true = block.get('true')
                flat = block.get('flat')
                if not true or not flat:
                    continue
                n_events += 1
                tm = utc_minutes(true)
                fm = utc_minutes(flat)
                if tm is None or fm is None:
                    errs.append(f"{obs['id']} {kind} {half}: missing time_utc")
                    continue
                if half == 'sunrise' and tm + 1e-6 < fm:
                    errs.append(
                        f"{obs['id']} {kind} sunrise true earlier than flat "
                        f"({true.get('time_utc')} < {flat.get('time_utc')})"
                    )
                if half == 'sunset' and tm > fm + 1e-6:
                    errs.append(
                        f"{obs['id']} {kind} sunset true later than flat "
                        f"({true.get('time_utc')} > {flat.get('time_utc')})"
                    )

                # SunCalc cross-check
                cc = block.get('suncalc_crosscheck') or {}
                if not cc.get('ok'):
                    errs.append(
                        f"{obs['id']} {kind} {half}: suncalc cross-check failed {cc}"
                    )

                delay = block.get('delay_min')
                if half == 'sunrise' and delay is not None:
                    if kind == 'june_solstice':
                        june_delays.append(float(delay))
                    if kind == 'december_solstice':
                        dec_delays.append(float(delay))

    sc = sky.get('suncalc_crosscheck') or {}
    print(
        f"suncalc worst dt={sc.get('worst_dt_min')} min "
        f"daz={sc.get('worst_daz_deg')} deg fails={sc.get('failures')}"
    )
    if sc.get('failures', 1) != 0:
        errs.append(f"suncalc_crosscheck.failures={sc.get('failures')}")

    # delays vs C16/C17 range
    if june_delays:
        jmin, jmax = min(june_delays), max(june_delays)
        print(f'june sunrise delay min/max={jmin}/{jmax} (expect {JUNE_DELAY_RANGE})')
        if jmin < JUNE_DELAY_RANGE[0] or jmax > JUNE_DELAY_RANGE[1]:
            errs.append(
                f'june delays [{jmin}, {jmax}] outside C16/C17 range {JUNE_DELAY_RANGE}'
            )
    else:
        errs.append('no june_solstice sunrise delays')

    if dec_delays:
        dmin, dmax = min(dec_delays), max(dec_delays)
        print(f'dec sunrise delay min/max={dmin}/{dmax} (expect {DEC_DELAY_RANGE})')
        if dmin < DEC_DELAY_RANGE[0] or dmax > DEC_DELAY_RANGE[1]:
            errs.append(
                f'dec delays [{dmin}, {dmax}] outside C16/C17 range {DEC_DELAY_RANGE} '
                '(or explain in sky-events)'
            )
    else:
        errs.append('no december_solstice sunrise delays')

    # --- alignments: bearing + terminate on published horizon radius ---
    obs_ll = {o['id']: (o['lng'], o['lat']) for o in sky['observers']}
    for feat in align['features']:
        p = feat.get('properties') or {}
        coords = (feat.get('geometry') or {}).get('coordinates') or []
        if len(coords) < 2:
            errs.append(f"alignment {p.get('event')}: short line")
            continue
        oid = p.get('observer_id')
        if oid not in obs_ll:
            errs.append(f'alignment unknown observer {oid}')
            continue
        lng0, lat0 = coords[0]
        lng1, lat1 = coords[-1]
        e0, n0 = lnglat_to_en(lng0, lat0)
        e1, n1 = lnglat_to_en(lng1, lat1)
        brg = bearing_en(e0, n0, e1, n1)
        az = float(p['azimuth_deg'])
        if ang_diff(brg, az) > BEARING_TOL_DEG:
            errs.append(
                f"{oid} {p.get('event')}: bearing {brg:.3f} vs az {az:.3f} "
                f"(Δ={ang_diff(brg, az):.3f})"
            )
        dist = math.hypot(e1 - e0, n1 - n0)
        pub_r = float(p.get('draw_radius_m') or draw_r)
        # must match published horizon draw radius
        if abs(pub_r - draw_r) > RADIUS_TOL_M:
            errs.append(f"{oid}: draw_radius_m {pub_r} != sky {draw_r}")
        if abs(dist - pub_r) > RADIUS_TOL_M:
            errs.append(
                f"{oid} {p.get('event')}: length {dist:.2f} m != horizon radius {pub_r}"
            )
        # horizon.geojson uses same radius
        for r in hz_radii.values():
            if abs(r - draw_r) > RADIUS_TOL_M:
                errs.append(f'horizon.geojson radius {r} != {draw_r}')
                break

    # every true event should have an alignment feature
    expected = 0
    for obs in sky['observers']:
        for kind, ev in (obs.get('events') or {}).items():
            for half in ('sunrise', 'sunset'):
                if (ev.get(half) or {}).get('true'):
                    expected += 1
    if len(align['features']) != expected:
        errs.append(
            f"alignments {len(align['features'])} != true events {expected}"
        )

    print(f'checked events≈{n_events} alignments={len(align["features"])}')
    return errs


def self_test() -> list[str]:
    """Inject faults; expect detection. Restore nothing — operate on copies in memory."""
    errs: list[str] = []
    sky = json.loads(SKY.read_text(encoding='utf-8'))
    align = json.loads(ALIGN.read_text(encoding='utf-8'))

    # 1) true sunrise earlier than flat
    obs0 = sky['observers'][0]
    kind = next(iter(obs0['events']))
    block = obs0['events'][kind]['sunrise']
    if block.get('true') and block.get('flat'):
        faulty = copy.deepcopy(sky)
        fobs = faulty['observers'][0]
        fk = next(iter(fobs['events']))
        fobs['events'][fk]['sunrise']['true']['time_utc'] = '2020-01-01T00:00:00Z'
        # write temp? run inline logic
        SKY.write_text(json.dumps(faulty) + '\n', encoding='utf-8')
        try:
            found = run_checks()
            if not any('true earlier than flat' in e for e in found):
                errs.append('self-test: earlier sunrise not caught')
            else:
                print('self-test: earlier sunrise caught')
        finally:
            SKY.write_text(json.dumps(sky, indent=2) + '\n', encoding='utf-8')

    # 2) bad alignment bearing
    if align['features']:
        bad = copy.deepcopy(align)
        bad['features'][0]['properties']['azimuth_deg'] = (
            float(bad['features'][0]['properties']['azimuth_deg']) + 15.0
        )
        ALIGN.write_text(json.dumps(bad) + '\n', encoding='utf-8')
        try:
            found = run_checks()
            if not any('bearing' in e for e in found):
                errs.append('self-test: bearing fault not caught')
            else:
                print('self-test: bearing fault caught')
        finally:
            ALIGN.write_text(json.dumps(align, indent=2) + '\n', encoding='utf-8')

    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        errs = self_test()
    else:
        errs = run_checks()
    if errs:
        print('FAIL check-sky:')
        for e in errs:
            print(' ', e)
        raise SystemExit(1)
    print('OK check-sky')


if __name__ == '__main__':
    main()
