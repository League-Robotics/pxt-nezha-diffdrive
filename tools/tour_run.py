#!/usr/bin/env python3
"""Run a tour the way it is meant to run: the robot drives it alone.

The overhead camera is a DIAGNOSTIC here, not a control input. It is
used exactly twice -- once at the start to seed the world pose, once at
the end to score -- and never in between. The robot drives all four
legs on its own sensors, because in real use there is no camera
overhead.

That also means no radio round trips inside the tour. The earlier
camera-in-the-loop version left the robot STATIONARY 73% of a 44 s run,
because every leg waited on a fix, a seed, and two acks.

The camera keeps RECORDING throughout -- recording is diagnostics.
Nothing it records reaches the robot.

  python3 tools/tour_run.py [--tour world|robot|wheels] [--runs 1]
"""
import argparse
import csv
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robotlink import open_link
from camlink import Cam, CamDown
from field import (ORDER, PathRefused, clears_margin, path_deviation,
                   score_corners, usable_half_extent, wrap)
from reposition import Repositioner
import tlm

# The start dot and the heading a tour begins from: NE, facing west.
START = (50.0, 30.0, 180.0)


def analyse(cam_rows):
    """Score the PATH, not just the endpoints -- a tour can hit every
    corner and still be a disaster to watch."""
    if len(cam_rows) < 20:
        return None
    t0 = cam_rows[0][0]
    span = cam_rows[-1][0] - t0
    # DEDUPLICATE first. `Cam` publishes one sample per REAL frame now,
    # so this is a belt-and-braces guard rather than the load-bearing
    # fix it was when a 20 Hz poll over a ~4 Hz camera made ~70% of rows
    # exact repeats. Left in, every repeat scores as a stationary sample
    # and the duty cycle reports the CAMERA's frame rate rather than the
    # robot's motion -- a genuinely good run read as "moving 24% of the
    # time, median speed 0 cm/s" while its own encoders said 197 mm/s.
    fresh = [cam_rows[0]]
    for r in cam_rows[1:]:
        if math.hypot(r[1] - fresh[-1][1], r[2] - fresh[-1][2]) > 1e-9:
            fresh.append(r)
    cam_rows = fresh
    # duty cycle: how much of the run was actually spent moving
    moving = 0
    total = 0
    speeds = []
    for a, b in zip(cam_rows, cam_rows[1:]):
        dt = b[0] - a[0]
        if not (0.02 < dt < 0.5):
            continue
        v = math.hypot(b[1] - a[1], b[2] - a[2]) / dt
        if v > 200:            # camera glitch, not a robot
            continue
        total += 1
        speeds.append(v)
        if v > 3:
            moving += 1
    # closest approach to each dot, in visit order (tools/field.py --
    # the ONE corner-scoring algorithm every tour/ground-truth tool
    # calls now, so this console report and a chart drawn from the
    # same run cannot disagree the way they used to)
    corners = score_corners(cam_rows)
    # how far the path strays from the ideal rectangle
    devs = path_deviation(cam_rows)
    return {'span': span, 'duty': 100.0 * moving / total if total else 0,
            'vmed': sorted(speeds)[len(speeds) // 2] if speeds else 0,
            'corners': corners,
            'dev_med': devs[len(devs) // 2],
            'dev_90': devs[int(len(devs) * 0.9)], 'dev_max': devs[-1]}


def make_repositioner(link, cam) -> Repositioner:
    """The repositioner a tour run stages with.

    There is ONE repositioning loop in this repo and it lives in
    `reposition.Repositioner` (sprint 034 ticket 009). This module used
    to carry a second one, `place()`, whose ordering -- position first,
    then heading, never a re-checking loop -- was the correct one and
    is the ordering `Repositioner.go()` now has; the "98 and 94 degrees
    instead of west" measurement that justifies it moved into
    `Repositioner.go()`'s docstring with the code. `place()` is gone.

    The tolerances are this caller's, not the class defaults: **1.5
    deg, not 4** -- an open-loop tour turns start heading error
    straight into corner error (leg x sin theta), so 4 deg on a 100 cm
    leg is already 7 cm.
    """
    return Repositioner(link, cam, tol_cm=2.5, tol_deg=1.5)


def report_start_pose(rep: Repositioner, pose, target) -> None:
    """Print where the repositioner actually left the robot, flagging a
    result outside twice its own tolerances -- a staging error is a
    silent corner error later, so it belongs on the console."""
    if not pose:
        return
    x, y, h = target
    derr = math.hypot(pose[0] - x, pose[1] - y)
    herr = abs(wrap(pose[2] - h))
    flag = ('' if (derr <= rep.tol_cm * 2 and herr <= rep.tol_deg * 2)
            else '  <-- OFF')
    print(f'    start: ({pose[0]:.1f},{pose[1]:.1f}) {pose[2]:.0f} deg  '
          f'({derr:.1f} cm, {herr:.1f} deg off){flag}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wifi', metavar='NAME|IP', default=None,
        help="drive the robot over its WiFi TCP server instead of the "
             "radio relay (the default carrier since 2026-09-02)")
    ap.add_argument('--robot', default='vevov',
        help="board name -- resolves the zavaz relay's channel/group "
             "(field_calibration.json's override, else derived from the "
             "name) when driving over --radio; ignored for --wifi")
    ap.add_argument('--tour', default='world')
    ap.add_argument('--runs', type=int, default=1)
    ap.add_argument('--out', default='.tmp/runs')
    ap.add_argument('--reposition', action='store_true',
                    help='drive back to the NE dot before each run')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    try:
        cam = Cam()
    except CamDown as e:
        raise SystemExit(f'camera not usable: {e}') from e
    if cam.latest is None:
        raise SystemExit('camera cannot see the robot')
    link = open_link(radio=not a.wifi, wifi=a.wifi, robot=a.robot)

    for run in range(1, a.runs + 1):
        print(f'\n=== {a.tour} tour, run {run} ===')
        # --- fail loud: a dead instrument must not cost a run (SUC-001).
        # Checked before reposition/seed too, not just before RUN:tour: --
        # reposition already drives the robot, so a dead telemetry link
        # should stop the run before THAT cost is spent either. ---
        try:
            stream = tlm.require_stream(link, timeout=3.0)
        except tlm.DeadTelemetryError as e:
            print(f'  {e}')
            break
        if a.reposition:
            print('  repositioning onto the NE dot (setup, not the tour)')
            rep = make_repositioner(link, cam)
            try:
                start = rep.go(*START)
            except PathRefused as e:
                print(f'  {e}')
                break
            if start is None:
                print('    camera cannot see the robot')
                break
            report_start_pose(rep, start, START)
        # --- camera use #1 of 2: seed the world pose, once ---
        p = cam.fix()
        if p is None:
            print('  camera lost the robot before the start'); break
        link.send(f'RUN seedxy {p[0]:.1f} {p[1]:.1f} {p[2]:.1f}')
        for s in link.lines(6):
            if s.startswith('OCAL:seeded'):
                break
        print(f'  seeded ({p[0]:.1f}, {p[1]:.1f}) {p[2]:.1f} deg')

        # --- the robot drives the whole tour alone from here ---
        t0 = time.time()
        link.send(f'RUN tour {a.tour}')
        ended = False
        fixes = []      # the robot's own corner fixes (OCAL:cN)
        for s in link.lines(120):
            if s.startswith('TOUR:end'):
                ended = True
                break
            if s.startswith('OCAL:c'):
                p2 = s.split(':')
                if len(p2) == 5:
                    try:
                        fixes.append((time.time() - t0, p2[1],
                                      int(p2[2]) / 100.0, int(p2[3]) / 100.0,
                                      int(p2[4]) / 100.0))
                    except ValueError:
                        pass
                continue
            # thdr/t telemetry decodes into `stream`; ack/nack/anything
            # else tlm.py doesn't recognize is silently ignored by feed().
            stream.feed(s)
        # Let the CAMERA catch up before scoring. The daemon updates at
        # ~4 Hz and the detection pipeline lags behind the world, so
        # cutting the record at TOUR:end freezes it roughly 0.7 s in the
        # past -- and at 20 cm/s that invents ~14 cm of error on the
        # final corner, which is exactly how a good run first scored
        # "NE 14.4 cm" while the robot's own fix said 1.4.
        time.sleep(2.0)
        cam_rows = cam.since(t0)
        # --- camera use #2 of 2: score it ---
        r = analyse(cam_rows)
        if not r:
            print('  too few camera samples to score'); continue
        print(f'  {"completed" if ended else "DID NOT REPORT AN END"} in '
              f'{r["span"]:.0f}s, moving {r["duty"]:.0f}% of it, '
              f'median speed {r["vmed"]:.0f} cm/s')
        print('  corners: ' + '  '.join(
            (f'{t} {r["corners"][t]:.1f}cm' if r['corners'][t] is not None
             else f'{t} unobserved') for t in ORDER))
        print(f'  path deviation from the rectangle: median '
              f'{r["dev_med"]:.1f} cm, 90th {r["dev_90"]:.1f}, '
              f'max {r["dev_max"]:.1f}')
        # The geofence, scored after the fact on the rows the recorder
        # already holds: the pre-flight check refuses a bad PLAN, this
        # says whether the run as driven stayed inside the margin.
        hx, hy = usable_half_extent()
        print(f'  geofence: '
              f'{"clear" if clears_margin(cam_rows) else "LEFT THE MARGIN"}'
              f' (usable +/-{hx:.2f} x +/-{hy:.2f} cm)')
        # Achieved wheel speed, from the robot's own encoders. This is
        # the number that says whether a leg ran at its commanded rate
        # or sat on the taper floor -- the fault that used to make the
        # tour stop a third of the way to each corner.
        wheel_pairs = [tlm.wheels_mms(row) for row in stream.frames]
        fwd = sorted((w['vl'] + w['vr']) / 2.0 for w in wheel_pairs
                     if abs(w['vl']) + abs(w['vr']) > 20)
        if fwd:
            print(f'  wheel speed while moving: median '
                  f'{fwd[len(fwd) // 2]:.0f} mm/s, p90 '
                  f'{fwd[int(len(fwd) * 0.9)]:.0f}, max {fwd[-1]:.0f}')
        # What did the robot believe at each corner, vs the camera?
        if fixes:
            print('  robot corner fixes vs camera at the same moment:')
            for ft, tag, fx, fy, _fh in fixes:
                near = min(cam_rows, key=lambda c: abs(c[0] - t0 - ft))
                d = math.hypot(fx - near[1], fy - near[2])
                print(f'    {tag}: robot ({fx:6.1f},{fy:6.1f}) '
                      f'camera ({near[1]:6.1f},{near[2]:6.1f})  '
                      f'disagree {d:5.1f} cm')
        stem = f'{a.out}/{a.tour}-{run}'
        with open(stem + '_cam.csv', 'w') as f:
            w = csv.writer(f)
            w.writerow(['t', 'x_cm', 'y_cm', 'yaw_deg'])
            w.writerows([[round(c[0] - t0, 3), round(c[1], 2),
                          round(c[2], 2), round(c[3], 2)] for c in cam_rows])
        # write_tlm_csv() writes stem + '_tlm.csv' (raw wire units: mm,
        # cdeg) plus the stem + '_tlm.meta.json' sidecar, and returns the
        # same dict it wrote -- surface the loss report here rather than
        # leaving it decoration only the sidecar carries (SUC-003).
        meta = tlm.write_tlm_csv(stream, stem + '_tlm.csv')
        print(f'  telemetry: {meta["frames"]} frames, '
              f'{meta["dropped"]} dropped ({meta["loss_pct"]:.1f}% loss)')
        time.sleep(1.5)

    link.close()
    cam.close()


if __name__ == '__main__':
    main()
