#!/usr/bin/env python3
"""Measure real rotation against commanded rotation, using the OTOS gyro.

RUN THIS ON THE FLOOR (--radio). On the bench stand the wheels turn in
the air and the body never rotates, so every answer is zero.

Why it exists: the lever-arm run on 2026-08-20 showed each commanded
45 deg pivot producing about 42 deg of real rotation -- a consistent 7%
UNDER-rotation. That points the opposite way from the AprilCam
calibration baked into the firmware (rotationScrub 1.040, from a pivot
measured at 369.2 deg physical for 359.5 believed, i.e. OVER-rotation).
Both cannot be right. This measures it directly, over a full turn where
a small per-pivot error is easy to see.

The robot's own odometry heading rides the same telemetry frames, so
each run compares three numbers: what was commanded, what the wheels
believe, and what the gyro saw.

Usage:
  python3 tools/rotation_check.py --radio [--reps 2]
"""
import argparse
import sys
import time

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from robotlink import open_link
from field import wrap
import tlm

# Commanded rotation [deg]. RUN:pivot:<deg> takes the angle directly,
# so this no longer needs to pair each one with a numeric RUN verb.
PIVOTS = [360.0, 180.0, -180.0]


def fix(link, tries=3):
    """Take one live OTOS fix -> (x_mm, y_mm, heading_deg) or None."""
    for _ in range(tries):
        seen = link.send_until('RUN:fix', 'OCAL:now', tries=1, wait=5.0,
                               echo=False)
        for s in seen:
            if s.startswith('OCAL:now'):
                p = s.split(':')
                return int(p[2]) / 10.0, int(p[3]) / 10.0, int(p[4]) / 100.0
    return None


def encoder_heading(link, stream, wait=2.0):
    """Latest encoder-odometry heading [deg] decoded during THIS wait
    window on `stream` (the same tools/tlm.py TlmStream the caller keeps
    feeding across the whole run, already primed by require_stream()) --
    or None if no `t` frame decodes within `wait`. Never falls back to
    an older frame already in `stream.frames`: the caller must treat
    None as "abort this measurement," not a stale/fabricated heading.
    """
    latest = None
    for s in link.lines(wait):
        row = stream.feed(s)
        if row is not None:
            latest = row
    if latest is None:
        return None
    return tlm.pose_cm(latest)['h']


def send_pivot(link, deg):
    """Command a relative pivot of `deg` and wait for it to finish."""
    return link.send_until(f'RUN:pivot:{int(deg)}', 'GAP:', tries=2,
                           wait=abs(deg) / 45.0 + 12.0, echo=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', nargs='?', default=None)
    ap.add_argument('--radio', action='store_true')
    ap.add_argument('--reps', type=int, default=1)
    a = ap.parse_args()

    link = open_link(a.port, radio=a.radio)
    # --- fail loud: a dead instrument must not cost a run (SUC-001) ---
    try:
        stream = tlm.require_stream(link, timeout=3.0)
    except tlm.DeadTelemetryError as e:
        raise SystemExit(str(e))
    print(f"{'commanded':>10} {'wheels':>9} {'gyro':>9} {'gyro/cmd':>9}"
          f" {'drift mm':>9}")
    ratios = []
    for _ in range(a.reps):
        for commanded in PIVOTS:
            before = fix(link)
            enc0 = encoder_heading(link, stream)
            if before is None or enc0 is None:
                print('  no fix -- skipping')
                continue
            # A full turn at 45 deg/s is 8 s; allow generous headroom.
            send_pivot(link, commanded)
            time.sleep(1.5)
            after = fix(link)
            enc1 = encoder_heading(link, stream)
            if after is None or enc1 is None:
                print('  no fix after pivot -- skipping')
                continue

            # Total turn, recovering full revolutions the wrapped
            # heading cannot show: trust the commanded magnitude to
            # pick the revolution, measure the remainder.
            revs = round(commanded / 360.0)
            gyro = revs * 360.0 + wrap(after[2] - before[2] - revs * 360.0)
            wheels = '%9.1f' % wrap(enc1 - enc0)
            drift = ((after[0] - before[0]) ** 2
                     + (after[1] - before[1]) ** 2) ** 0.5
            ratio = gyro / commanded
            ratios.append(ratio)
            print(f"{commanded:10.1f} {wheels} {gyro:9.1f} {ratio:9.3f}"
                  f" {drift:9.1f}")

    link.close()
    if ratios:
        mean = sum(ratios) / len(ratios)
        print(f"\nmean gyro/commanded = {mean:.3f} over {len(ratios)} pivots")
        print(f"firmware rotationScrub is 1.040; this run implies "
              f"{1.040 * mean:.3f}")
        print("(drift mm is how far the CENTRE moved during a pivot that "
              "should hold it still -- a residual lever-arm error.)")


if __name__ == '__main__':
    main()
