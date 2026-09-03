#!/usr/bin/env python3
"""Ground-truth a pivot: overhead camera vs OTOS gyro vs wheel odometry.

Every rotation number measured so far came from the OTOS itself, which
cannot say whether the ROBOT under-rotates or the SENSOR under-reads --
the sensor is grading its own homework. The camera is independent, so
it settles it.

Rotation needs no world calibration: the AprilTag's yaw is an angle in
the image plane, and the CHANGE in that angle across a pivot is the
rotation. (Position would need calibration; this deliberately measures
only rotation.)

Usage:
  python3 tools/truth_check.py [--cam arducam-ov9782-usb-camera]
                               [--pivots 180 -180 360]
"""
import argparse
import json
import math
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from robotlink import open_link
from field import wrap
import tlm

# The CLI talks to whichever daemon these point at. The playfield
# daemon runs on TCP 5280 here (mDNS discovery does not find it, and
# the local unix socket belongs to a different instance).
CAM_ENV = dict(os.environ, APRILCAM_DAEMON_HOST='127.0.0.1',
               APRILCAM_DAEMON_PORT='5280')


def cam_read(cam, tag=53, samples=5):
    """Median (yaw_rad, x_cm, y_cm) for `tag` over a few frames, or None.

    Position is world-calibrated, so this grounds BOTH rotation and
    displacement -- unlike the uncalibrated first attempt, which could
    only do rotation.
    """
    yaws, xs, ys = [], [], []
    for _ in range(samples):
        out = subprocess.run(['aprilcam', 'tool', 'get_tags',
                              f'source_id={cam}'],
                             capture_output=True, text=True, timeout=20,
                             env=CAM_ENV)
        try:
            d = json.loads(out.stdout)
        except json.JSONDecodeError:
            continue
        for t in d.get('tags', []):
            if t['id'] == tag:
                yaws.append(t['orientation_yaw'])
                w = t.get('world_xy') or [None, None]
                if w[0] is not None:
                    xs.append(w[0])
                    ys.append(w[1])
        if samples > 1:
            time.sleep(0.15)
    if not yaws:
        return None
    med = lambda v: sorted(v)[len(v) // 2]
    return (med(yaws), med(xs) if xs else float('nan'),
            med(ys) if ys else float('nan'))


def cam_yaw(cam, tag=53, samples=5):
    r = cam_read(cam, tag, samples)
    return None if r is None else r[0]


def otos_fix(link):
    """Live OTOS fix -> (x_mm, y_mm, heading_deg) or None."""
    for s in link.send_until('RUN:fix', 'OCAL:now', tries=2, wait=5.0,
                             echo=False):
        if s.startswith('OCAL:now'):
            p = s.split(':')
            return int(p[2]) / 10.0, int(p[3]) / 10.0, int(p[4]) / 100.0
    return None


def send_pivot(link, deg):
    """Command a relative pivot of `deg` and wait for it to finish.

    RUN:pivot:<deg> takes an arbitrary signed degree value directly --
    unlike the old dead numeric PIVOT_VERB table, every commanded angle
    (not just 180/-180/360) now has a real verb.
    """
    return link.send_until(f'RUN:pivot:{int(deg)}', 'GAP:', tries=1,
                           wait=abs(deg) / 45.0 + 12.0, echo=False)


def enc_heading(link, stream, wait=2.0):
    """Latest encoder-odometry heading [deg] decoded during THIS wait
    window on `stream` (the same tools/tlm.py TlmStream the caller keeps
    feeding across the whole run, already primed by require_stream()) --
    or None if no `t` frame decodes within `wait`.

    Deliberately does NOT fall back to an older frame already sitting in
    `stream.frames` from a previous call: a stale heading read as fresh
    is exactly the fabricated-value failure mode this retrofit removes.
    The caller must treat None as "abort this measurement," not
    substitute a cached or zero value.
    """
    latest = None
    for s in link.lines(wait):
        row = stream.feed(s)
        if row is not None:
            latest = row
    if latest is None:
        return None
    return tlm.pose_cm(latest)['h']


def total_turn(before, after, commanded):
    """Recover the full turn, using the commanded value to pick the
    revolution and measuring only the remainder."""
    revs = round(commanded / 360.0)
    return revs * 360.0 + wrap(after - before - revs * 360.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wifi', metavar='NAME|IP', default=None,
        help="drive the robot over its WiFi TCP server instead of the "
             "radio relay (the default carrier since 2026-09-02)")
    ap.add_argument('--cam', default='arducam-ov9782-usb-camera')
    ap.add_argument('--tag', type=int, default=53)
    ap.add_argument('--pivots', type=float, nargs='+',
                    default=[180.0, -180.0, 360.0])
    a = ap.parse_args()

    if cam_yaw(a.cam, a.tag) is None:
        raise SystemExit(f'camera cannot see tag {a.tag} -- is the robot '
                         'inside the field of view?')

    link = open_link(radio=not a.wifi, wifi=a.wifi)
    # --- fail loud: a dead instrument must not cost a run (SUC-001) ---
    try:
        stream = tlm.require_stream(link, timeout=3.0)
    except tlm.DeadTelemetryError as e:
        raise SystemExit(str(e)) from e
    print(f"{'commanded':>10} {'CAMERA':>9} {'gyro':>9} {'wheels':>9}"
          f" {'cam/cmd':>8} {'gyro/cam':>9}")
    rows = []
    for commanded in a.pivots:
        c0 = cam_yaw(a.cam, a.tag)
        o0 = otos_fix(link)
        e0 = enc_heading(link, stream)
        if c0 is None or o0 is None or e0 is None:
            print('  lost a reading before the pivot -- skipping')
            continue

        # Sample the camera THROUGHOUT the pivot and unwrap
        # incrementally. A single before/after pair cannot resolve a
        # 180 deg turn at all -- it lands exactly on the wrap boundary,
        # where +180 and -180 are the same reading. Consecutive samples
        # are ~10 deg apart, so each step is unambiguous and the total
        # is just their sum.
        cam_total = [0.0]
        stop = threading.Event()

        def sampler(prev=math.degrees(c0)):  # noqa: B008 -- c0 is loop-fresh per pivot, not shared mutable state
            while not stop.is_set():  # noqa: B023 -- stop/cam_total are redefined each iteration, but th.join() below always completes (or times out) before the next iteration reassigns them, so this closure never sees a stale binding
                y = cam_yaw(a.cam, a.tag, samples=1)
                if y is not None:
                    now = math.degrees(y)
                    cam_total[0] += wrap(now - prev)  # noqa: B023 -- same as above: joined before cam_total is rebound
                    prev = now

        th = threading.Thread(target=sampler, daemon=True)
        th.start()
        send_pivot(link, commanded)
        time.sleep(2.0)
        stop.set()
        th.join(timeout=5.0)

        o1 = otos_fix(link)
        e1 = enc_heading(link, stream)
        if o1 is None or e1 is None:
            print('  lost the robot reading after the pivot -- skipping')
            continue

        cam = cam_total[0]
        gyro = total_turn(o0[2], o1[2], commanded)
        wheels = total_turn(e0, e1, commanded)
        rows.append((commanded, cam, gyro))
        print(f"{commanded:10.1f} {cam:9.1f} {gyro:9.1f} {wheels:9.1f}"
              f" {cam / commanded:8.3f} {gyro / cam:9.3f}")

    link.close()
    if rows:
        cc = sum(c / k for k, c, _ in rows) / len(rows)
        gc = sum(g / c for _, c, g in rows) / len(rows)
        print(f"\ncamera/commanded = {cc:.3f}  -> the ROBOT turns this "
              f"fraction of what is asked")
        print(f"gyro/camera      = {gc:.3f}  -> the SENSOR reports this "
              f"fraction of the truth")
        print("\nIf camera/commanded is ~1.0, the robot is fine and the "
              "OTOS under-reads.")
        print("If gyro/camera is ~1.0, the sensor is fine and the robot "
              "really under-rotates.")


if __name__ == '__main__':
    main()
