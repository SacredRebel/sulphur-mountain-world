/**
 * Batch SunCalc helper for C26 cross-check.
 * stdin: JSON array of {id, lat, lng, year, month, day}
 * stdout: JSON array with sunrise/sunset (ISO, az from north cw, alt)
 *
 * mourner/suncalc — BSD-2-Clause
 */
const SunCalc = require('./suncalc.js');

let buf = '';
process.stdin.on('data', (d) => { buf += d; });
process.stdin.on('end', () => {
  const reqs = JSON.parse(buf);
  const out = reqs.map(({ id, lat, lng, year, month, day }) => {
    const d = new Date(Date.UTC(year, month - 1, day, 12));
    const t = SunCalc.getTimes(d, lat, lng);
    function pack(date) {
      if (!date || Number.isNaN(+date)) return null;
      const pos = SunCalc.getPosition(date, lat, lng);
      // suncalc azimuth is from south; convert to north-clockwise degrees
      const azNorth = ((pos.azimuth * 180) / Math.PI + 180) % 360;
      return {
        ms: +date,
        iso: date.toISOString(),
        az_north_deg: azNorth,
        alt_deg: (pos.altitude * 180) / Math.PI,
      };
    }
    return { id, sunrise: pack(t.sunrise), sunset: pack(t.sunset) };
  });
  process.stdout.write(JSON.stringify(out));
});
