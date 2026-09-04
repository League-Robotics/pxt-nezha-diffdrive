#!/usr/bin/env python3
"""OTOS lever-arm calibration -- drives test.ts RUN:cal and fits the arm.

RUN THIS OVER RADIO, WITH THE ROBOT ON THE FLOOR (--radio). The USB
cable only reaches the bench stand, where the wheels spin in the air:
the body never rotates, the gyro correctly reports nothing, and the fit
degenerates to a zero-length arm from nine identical fixes.

With the sensor offsets zeroed, a pure in-place pivot sweeps the SENSOR
around the robot's centre of rotation, so the sensor's reported track is
a circle: centre = the robot's centre, radius = the lever arm. Each fix
i satisfies

    x_i = cx + cos(h_i)*ox - sin(h_i)*oy
    y_i = cy + sin(h_i)*ox + cos(h_i)*oy

which is LINEAR in the four unknowns (cx, cy, ox, oy), so eight fixes
around a full turn give a plain least-squares solve -- no circle-fit
iteration, and the headings come from the gyro rather than from the
commanded angles (so pivot inexactness does not bias the fit).

The straight leg that follows gives the mounting yaw: the sensor's
reported displacement direction minus the heading it reported while
driving it.

Usage:
  python3 tools/otos_levercal.py --radio [--timeout 150]
  python3 tools/otos_levercal.py PORT [--timeout 150]      (USB)
"""
import argparse
import math
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from robotlink import open_link


def solve_lstsq(rows, rhs):
    """Least squares via normal equations; no numpy dependency.

    rows: list of coefficient lists (each len n). rhs: list of values.
    """
    n = len(rows[0])
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(n)]
           for i in range(n)]
    atb = [sum(r[i] * b for r, b in zip(rows, rhs)) for i in range(n)]
    # Gauss-Jordan with partial pivoting.
    m = [ata[i] + [atb[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise SystemExit('singular fit -- did the robot actually pivot?')
        m[col], m[piv] = m[piv], m[col]
        p = m[col][col]
        m[col] = [v / p for v in m[col]]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col]
            if f:
                m[r] = [a - f * b for a, b in zip(m[r], m[col])]
    return [m[i][n] for i in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', nargs='?', default=None,
                    help='serial port; omit with --radio for the zavaz default')
    ap.add_argument('--wifi', metavar='NAME|IP', default=None,
        help='drive the robot over its WiFi TCP server (default carrier since 2026-09-02)')
    ap.add_argument('--radio', action='store_true',
                    help='drive the robot over the zavaz relay (playfield). '
                         'REQUIRED for real calibration -- on the bench '
                         'stand the wheels are off the ground, so the robot '
                         'never physically turns and every fix is identical.')
    ap.add_argument('--robot', default='vevov',
                    help="board name -- resolves the zavaz relay's "
                         "channel/group for --radio; ignored otherwise")
    ap.add_argument('--verify', action='store_true',
                    help='run RUN:cal:1 instead: the same sweep with the '
                         'MEASURED arm applied. A correct arm collapses '
                         'the circle to a point, so the fitted arm here '
                         'should come back near ZERO -- that is the '
                         'residual error, not the arm.')
    ap.add_argument('--timeout', type=float, default=120.0)
    a = ap.parse_args()

    link = open_link(a.port, radio=a.radio, wifi=a.wifi, robot=a.robot)
    # OCAL:begin is the delivery receipt -- resend only if it never
    # arrives, never blindly (a duplicate RUN:cal runs the whole
    # calibration again).
    verb = 'RUN:cal:1' if a.verify else 'RUN:cal'
    started = link.send_until(verb, 'OCAL:begin', tries=3, wait=6.0)
    if not any(s.startswith('OCAL:begin') for s in started):
        raise SystemExit(f'robot never acknowledged {verb} -- is it awake '
                         'and on the right channel?')

    fixes = {}          # tag -> (x_mm, y_mm, h_rad)
    for s in link.lines(a.timeout, until='OCAL:end'):
        if not s.startswith('OCAL:'):
            continue
        print(s)
        body = s[5:]
        if body == 'end':
            continue
        parts = body.split(':')
        if len(parts) != 4:
            continue
        try:
            tag = parts[0]
            x01, y01, hcd = (int(v) for v in parts[1:])
        except ValueError:
            continue
        fixes[tag] = (x01 / 10.0, y01 / 10.0, math.radians(hcd / 100.0))
    link.close()

    # p0 is the SEEDED pose read straight back, not a measurement: it is
    # whatever seedPose() just wrote, taken before the robot has turned
    # at all and before the gyro's fresh bias calibration has been
    # exercised. Measured on vevov 2026-08-20 it was the single bad
    # point -- including it tripled the fit residual (rms 4.05 mm vs
    # 1.34 mm, max 10.28 vs 2.91) while moving the answer only 0.3 mm.
    # The circle is defined by the points that actually moved.
    pivots = [fixes[k] for k in sorted(fixes)
              if k.startswith('p') and k != 'p0']
    if len(pivots) < 4:
        raise SystemExit(f'only {len(pivots)} pivot fixes -- need >= 4')

    rows, rhs = [], []
    for x, y, h in pivots:
        c, s = math.cos(h), math.sin(h)
        rows.append([1.0, 0.0, c, -s])   # x equation
        rhs.append(x)
        rows.append([0.0, 1.0, s, c])    # y equation
        rhs.append(y)
    cx, cy, ox, oy = solve_lstsq(rows, rhs)

    resid = []
    for x, y, h in pivots:
        c, s = math.cos(h), math.sin(h)
        resid.append(math.hypot(x - (cx + c * ox - s * oy),
                                y - (cy + s * ox + c * oy)))
    rms = math.sqrt(sum(r * r for r in resid) / len(resid))

    print()
    print(f'pivot fixes used: {len(pivots)}')
    print(f'centre of rotation (sensor frame): ({cx:.1f}, {cy:.1f}) mm')
    print(f'LEVER ARM  offset_x = {ox:.1f} mm   offset_y = {oy:.1f} mm'
          f'   (|arm| = {math.hypot(ox, oy):.1f} mm)')
    print(f'fit residual rms {rms:.2f} mm, max {max(resid):.2f} mm')

    yaw_deg = 0.0
    if 's1' in fixes:
        x0, y0, h0 = pivots[-1]
        x1, y1, _ = fixes['s1']
        dist = math.hypot(x1 - x0, y1 - y0)
        if dist > 20.0:
            course = math.atan2(y1 - y0, x1 - x0)
            yaw = math.atan2(math.sin(course - h0), math.cos(course - h0))
            yaw_deg = math.degrees(yaw)
            print(f'straight leg {dist:.1f} mm, course '
                  f'{math.degrees(course):.1f} deg vs heading '
                  f'{math.degrees(h0):.1f} deg')
            print(f'MOUNTING YAW  offset_yaw = {yaw:.4f} rad'
                  f' ({yaw_deg:.2f} deg)')
        else:
            print(f'straight leg only {dist:.1f} mm -- yaw not estimated')
    else:
        print('no straight-leg fix -- mounting yaw not estimated')

    if a.verify:
        print()
        print('VERIFY RUN: the arm was already applied, so the numbers '
              'above are RESIDUAL error.')
        print(f'  residual arm {math.hypot(ox, oy):.1f} mm '
              f'(was 38.2 mm uncorrected)')
        print('  reference project measured 42.7 mm when the arm was '
              'double-corrected; near zero is correct.')
        return

    print()
    print('bake into test.ts startup:')
    print(f'  diffDrive.setWorldSensorOffset({ox/10:.2f}, {oy/10:.2f}, '
          f'{yaw_deg:.2f})   // cm, cm, deg')


if __name__ == '__main__':
    main()
