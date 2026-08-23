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
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robotlink import open_link

VENV = '/Volumes/Cache/User-Eric/.local/pipx/venvs/aprilcam/bin/python'
CAMLINK = os.path.dirname(os.path.abspath(__file__)) + '/camlink.py'
DOTS = {'NW': (-50.0, 30.0), 'SW': (-50.0, -30.0),
        'SE': (50.0, -30.0), 'NE': (50.0, 30.0)}
ORDER = ['NW', 'SW', 'SE', 'NE']


def wrap(d):
    while d <= -180.0:
        d += 360.0
    while d > 180.0:
        d -= 360.0
    return d


class Cam(threading.Thread):
    def __init__(self, hz=20.0):
        super().__init__(daemon=True)
        self.p = subprocess.Popen([VENV, CAMLINK, '--hz', str(hz)],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True,
                                  bufsize=1)
        self.latest = None
        self.samples = []
        self.lock = threading.Lock()
        self.start()
        d = time.time() + 15
        while time.time() < d and self.latest is None:
            time.sleep(0.2)

    def run(self):
        for line in self.p.stdout:
            line = line.strip()
            if line in ('NOTAG', '') or line.startswith('ERR'):
                continue
            try:
                yaw, x, y = (float(v) for v in line.split())
            except ValueError:
                continue
            with self.lock:
                self.latest = (x, y, yaw)
                self.samples.append((time.time(), x, y, yaw))

    def fix(self, n=8):
        v = []
        for _ in range(n):
            with self.lock:
                r = self.latest
            if r:
                v.append(r)
            time.sleep(0.06)
        if not v:
            return None
        m = lambda i: sorted(q[i] for q in v)[len(v) // 2]
        return m(0), m(1), m(2)

    def since(self, t):
        with self.lock:
            return [s for s in self.samples if s[0] >= t]

    def close(self):
        self.p.terminate()


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
    # closest approach to each dot, in visit order
    corners = {}
    used = 0
    for tag in ORDER:
        dx, dy = DOTS[tag]
        best, besti = None, used
        for i in range(used, len(cam_rows)):
            d = math.hypot(cam_rows[i][1] - dx, cam_rows[i][2] - dy)
            if best is None or d < best:
                best, besti = d, i
        corners[tag] = best
        used = besti
    # how far the path strays from the ideal rectangle
    segs = [((50, 30), (-50, 30)), ((-50, 30), (-50, -30)),
            ((-50, -30), (50, -30)), ((50, -30), (50, 30))]
    devs = []
    for _, x, y, _ in cam_rows:
        best = 1e9
        for (x1, y1), (x2, y2) in segs:
            dx, dy = x2 - x1, y2 - y1
            L = dx * dx + dy * dy
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L))
            best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
        devs.append(best)
    devs.sort()
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
        tlm = []        # full telemetry
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
            elif s.startswith('TLM:'):
                f2 = s[4:].split(':')
                if len(f2) >= 9:
                    try:
                        tlm.append((time.time() - t0, int(f2[1]) / 10.0,
                                    int(f2[2]) / 10.0, int(f2[3]) / 100.0,
                                    int(f2[4]) / 10.0, int(f2[5]) / 10.0,
                                    int(f2[6]) / 100.0,
                                    # Fields 8/9: the kernel's own per-tick
                                    # encoder measurement, mm/s. Do NOT
                                    # substitute a pose difference here --
                                    # 24 ms ticks sampled every 56 ms alias
                                    # into a +-25% sawtooth.
                                    int(f2[7]), int(f2[8])))
                    except ValueError:
                        pass
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
            f'{t} {r["corners"][t]:.1f}cm' for t in ORDER))
        print(f'  path deviation from the rectangle: median '
              f'{r["dev_med"]:.1f} cm, 90th {r["dev_90"]:.1f}, '
              f'max {r["dev_max"]:.1f}')
        # Achieved wheel speed, from the robot's own encoders. This is
        # the number that says whether a leg ran at its commanded rate
        # or sat on the taper floor -- the fault that used to make the
        # tour stop a third of the way to each corner.
        fwd = sorted((v[7] + v[8]) / 2.0 for v in tlm
                     if abs(v[7]) + abs(v[8]) > 20)
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
        with open(stem + '_tlm.csv', 'w') as f:
            w = csv.writer(f)
            w.writerow(['t', 'enc_x', 'enc_y', 'enc_h',
                        'otos_x', 'otos_y', 'otos_h', 'vl_mms', 'vr_mms'])
            w.writerows([[round(v, 2) for v in row] for row in tlm])
        time.sleep(1.5)

    link.close()
    cam.close()


if __name__ == '__main__':
    main()
