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
from camproc import Cam
from field import ORDER, wrap, score_corners, path_deviation
import tlm


def analyse(cam_rows):
    """Score the PATH, not just the endpoints -- a tour can hit every
    corner and still be a disaster to watch."""
    if len(cam_rows) < 20:
        return None
    t0 = cam_rows[0][0]
    span = cam_rows[-1][0] - t0
    # DEDUPLICATE first. camlink polls at 20 Hz but the daemon only
    # produces ~4 Hz, so ~70% of rows repeat the previous position
    # exactly. Left in, every repeat scores as a stationary sample and
    # the duty cycle reports the CAMERA's frame rate rather than the
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


def place(link, cam, x, y, h, tol_cm=2.5, tol_deg=4.0, tries=3):
    """Put the robot back on the start dot, camera-verified.

    This runs BETWEEN tours, never inside one. Repositioning is setup:
    it is the only way successive practice runs start from the same
    place and their scores mean the same thing.
    """
    # POSITION first, then heading, and never the other way round. An
    # in-place pivot walks the centre of rotation a centimetre or so,
    # which is enough to push the position error back over tolerance --
    # so a loop that re-checks both and picks one will answer a good
    # heading with another goto and undo it. Two runs started facing
    # 98 and 94 degrees instead of west that way.
    for _ in range(tries):
        p = cam.fix()
        if p is None:
            print('    camera cannot see the robot'); return False
        if math.hypot(p[0] - x, p[1] - y) <= tol_cm:
            break
        link.send_until(f'RUN:seedxy:{p[0]:.1f}:{p[1]:.1f}:{p[2]:.1f}',
                        'OCAL:seeded', tries=3, wait=5, echo=False)
        link.send_until(f'RUN:goto:{x:.0f}:{y:.0f}', 'GOTO:end',
                        tries=2, wait=30, echo=False)
        time.sleep(0.7)
    # Heading LAST, from a fresh seed, so nothing can disturb it after.
    for _ in range(tries):
        p = cam.fix()
        if p is None:
            print('    camera cannot see the robot'); return False
        if abs(wrap(p[2] - h)) <= tol_deg:
            break
        link.send_until(f'RUN:seedxy:{p[0]:.1f}:{p[1]:.1f}:{p[2]:.1f}',
                        'OCAL:seeded', tries=3, wait=5, echo=False)
        link.send_until(f'RUN:face:{h:.0f}', 'FACE:end',
                        tries=2, wait=30, echo=False)
        time.sleep(0.7)
    p = cam.fix()
    if p:
        derr = math.hypot(p[0] - x, p[1] - y)
        herr = abs(wrap(p[2] - h))
        flag = '' if (derr <= tol_cm * 2 and herr <= tol_deg * 2) else '  <-- OFF'
        print(f'    start: ({p[0]:.1f},{p[1]:.1f}) {p[2]:.0f} deg  '
              f'({derr:.1f} cm, {herr:.0f} deg off){flag}')
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tour', default='world')
    ap.add_argument('--runs', type=int, default=1)
    ap.add_argument('--out', default='.tmp/runs')
    ap.add_argument('--reposition', action='store_true',
                    help='drive back to the NE dot before each run')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    cam = Cam()
    if cam.latest is None:
        raise SystemExit('camera cannot see the robot')
    link = open_link(radio=True)

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
            # 1.5 deg, not 4: an open-loop tour turns start heading
            # error straight into corner error (leg x sin theta), so
            # 4 deg on a 100 cm leg is already 7 cm.
            if not place(link, cam, 50.0, 30.0, 180.0, tol_deg=1.5):
                break
        # --- camera use #1 of 2: seed the world pose, once ---
        p = cam.fix()
        if p is None:
            print('  camera lost the robot before the start'); break
        link.send(f'RUN:seedxy:{p[0]:.1f}:{p[1]:.1f}:{p[2]:.1f}')
        for s in link.lines(6):
            if s.startswith('OCAL:seeded'):
                break
        print(f'  seeded ({p[0]:.1f}, {p[1]:.1f}) {p[2]:.1f} deg')

        # --- the robot drives the whole tour alone from here ---
        t0 = time.time()
        link.send(f'RUN:tour:{a.tour}')
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
            for ft, tag, fx, fy, fh in fixes:
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
