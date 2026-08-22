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

VENV = '/Volumes/Proj/proj/RobotProjects/AprilTags/.venv/bin/python3'
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tour', default='world')
    ap.add_argument('--runs', type=int, default=1)
    ap.add_argument('--out', default='.tmp/runs')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    cam = Cam()
    if cam.latest is None:
        raise SystemExit('camera cannot see the robot')
    link = open_link(radio=True)

    for run in range(1, a.runs + 1):
        print(f'\n=== {a.tour} tour, run {run} ===')
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
                if len(f2) >= 7:
                    try:
                        tlm.append((time.time() - t0, int(f2[1]) / 10.0,
                                    int(f2[2]) / 10.0, int(f2[3]) / 100.0,
                                    int(f2[4]) / 10.0, int(f2[5]) / 10.0,
                                    int(f2[6]) / 100.0))
                    except ValueError:
                        pass
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
                        'otos_x', 'otos_y', 'otos_h'])
            w.writerows([[round(v, 2) for v in row] for row in tlm])
        time.sleep(1.5)

    link.close()
    cam.close()


if __name__ == '__main__':
    main()
