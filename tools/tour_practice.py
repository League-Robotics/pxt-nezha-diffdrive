#!/usr/bin/env python3
"""Run tours from the start dot, camera-scored, and chart each one.

For every run: reposition onto the NE orange dot facing west (verified
by the overhead camera, not assumed), start the tour, record telemetry
and camera continuously, then chart and score it.

Scoring is done by the CAMERA throughout. The robot's own sensors are
recorded alongside for comparison, but a tour that navigates by the
OTOS cannot be graded by the OTOS -- it would be marking its own
homework.

Wheel speeds are DERIVED from the encoder-odometry pose stream rather
than polled: a request/reply round-trip inside a move over the wireless
link is measured to collapse a 197.5 mm leg to 0.3 mm.

  python3 tools/tour_practice.py [--tours robot world] [--runs 2]
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
from reposition import Repositioner, wrap

VENV = '/Volumes/Proj/proj/RobotProjects/AprilTags/.venv/bin/python3'
CAMLINK = os.path.dirname(os.path.abspath(__file__)) + '/camlink.py'

DOTS = {'NW': (-50.0, 30.0), 'NE': (50.0, 30.0),
        'SE': (50.0, -30.0), 'SW': (-50.0, -30.0)}
# Visit order from the NE dot, counter-clockwise.
ORDER = ['NW', 'SW', 'SE', 'NE']
RECT = [DOTS['NE'], DOTS['NW'], DOTS['SW'], DOTS['SE'], DOTS['NE']]
START = (50.0, 30.0, 180.0)
TRACK_CM = 12.0          # effective track (114.2 mm / 0.952 scrub)

TITLES = {'robot': 'Tour A — robot-relative (encoder only)',
          'world': 'Tour B — world goToWorld (OTOS-guided)',
          'wheels': 'Tour A+B — wheels (open loop)'}


class CamProc:
    """Overhead camera in its own process, timestamped samples."""

    def __init__(self, hz=20.0):
        self.p = subprocess.Popen([VENV, CAMLINK, '--hz', str(hz)],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True,
                                  bufsize=1)
        self.samples = []
        self.latest = None
        self.err = None
        self.lock = threading.Lock()
        threading.Thread(target=self._pump, daemon=True).start()
        # The camera subprocess has to spawn python, import aprilcam and
        # open a gRPC channel before its first sample -- a fixed 1.5 s
        # was sometimes short, and reported as "no tag" when the tag was
        # in plain view.
        deadline = time.time() + 15.0
        while time.time() < deadline:
            if self.latest is not None or self.err:
                break
            time.sleep(0.2)

    def _pump(self):
        for line in self.p.stdout:
            line = line.strip()
            with self.lock:
                if line.startswith('ERR'):
                    self.err = line
                    return
                if line == 'NOTAG':
                    continue
                try:
                    yaw, x, y = (float(v) for v in line.split())
                except ValueError:
                    continue
                self.latest = (yaw, x, y)
                self.samples.append((time.time(), x, y, yaw))

    def read(self, tag=53):
        with self.lock:
            return self.latest

    def since(self, t0):
        with self.lock:
            return [s for s in self.samples if s[0] >= t0]

    def close(self):
        self.p.terminate()


def record_tour(link, cam, name, timeout=120):
    """Trigger a tour and record until it ends."""
    t0 = time.time()
    link.send(f'RUN:tour:{name}')
    pose, fixes = [], []
    started = False
    end = time.time() + timeout
    while time.time() < end:
        for s in link.lines(1.0):
            if s.startswith('DBG:tour='):
                started = True
                t0 = time.time()
            elif s.startswith('TLM:') and started:
                f = s[4:].split(':')
                if len(f) >= 7:
                    try:
                        # f[0] is the DEVICE timestamp [ms] -- use it for
                        # dt, not host arrival, which jitters badly over
                        # the wireless link and fabricates speed spikes.
                        pose.append((time.time(), int(f[1]) / 10.0,
                                     int(f[2]) / 10.0, int(f[3]) / 100.0,
                                     int(f[4]) / 10.0, int(f[5]) / 10.0,
                                     int(f[6]) / 100.0, int(f[0]),
                                     int(f[7]) / 10.0 if len(f) > 8 else 0.0,
                                     int(f[8]) / 10.0 if len(f) > 8 else 0.0))
                    except ValueError:
                        pass
            elif s.startswith('OCAL:c') and started:
                fixes.append(s)
            elif s.startswith('TOUR:end') and started:
                return t0, pose, fixes, True
        if started and time.time() - t0 > timeout:
            break
    return t0, pose, fixes, started


def wheel_speeds(pose):
    """Left/right wheel speed [cm/s] derived from the encoder pose
    stream -- v +- omega*track/2. Telemetry is not polled during a run,
    so this is the honest way to get them."""
    out = []
    for a, b in zip(pose, pose[1:]):
        dt = b[0] - a[0]
        if dt <= 0.001:
            continue
        ds = math.hypot(b[1] - a[1], b[2] - a[2])
        # sign of travel: project onto the heading
        h = math.radians(a[3])
        fwd = (b[1] - a[1]) * math.cos(h) + (b[2] - a[2]) * math.sin(h)
        if fwd < 0:
            ds = -ds
        dw = math.radians(wrap(b[3] - a[3]))
        v = ds / dt
        om = dw / dt
        out.append((b[0], v - om * TRACK_CM / 2, v + om * TRACK_CM / 2))
    return out


def score(camrows):
    """Closest approach to each dot, in visit order, plus closure."""
    if not camrows:
        return None
    res = {}
    used = 0
    for tag in ORDER:
        dx, dy = DOTS[tag]
        best, besti = None, used
        for i in range(used, len(camrows)):
            d = math.hypot(camrows[i][1] - dx, camrows[i][2] - dy)
            if best is None or d < best:
                best, besti = d, i
        res[tag] = best
        used = besti
    sx, sy = camrows[0][1], camrows[0][2]
    ex, ey = camrows[-1][1], camrows[-1][2]
    res['closure'] = math.hypot(ex - sx, ey - sy)
    res['end_heading_err'] = wrap(camrows[-1][3] - START[2])
    return res


def write_csv(path, header, rows):
    with open(path, 'w') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def chart(name, run, pose, camrows, sc, path, stem):
    """Chart in a subprocess: the system matplotlib is broken here, so
    plotting runs under uv while this process keeps pyserial."""
    write_csv(stem + '_cam.csv', ['t', 'x_cm', 'y_cm', 'yaw_deg'],
              [[round(c[0], 3), round(c[1], 2), round(c[2], 2),
                round(c[3], 2)] for c in camrows])
    write_csv(stem + '_pose.csv',
              ['t', 'enc_x', 'enc_y', 'enc_h', 'otos_x', 'otos_y', 'otos_h',
               'dev_ms', 'vl_cms', 'vr_cms'],
              [[round(p[0], 3)] + [round(v, 2) for v in p[1:7]]
               + [p[7] if len(p) > 7 else 0]
               + [round(p[8], 1) if len(p) > 8 else 0,
                  round(p[9], 1) if len(p) > 9 else 0] for p in pose])
    subprocess.run(['uv', 'run', '--with', 'numpy', '--with', 'matplotlib',
                    'python3',
                    os.path.dirname(os.path.abspath(__file__))
                    + '/practice_chart.py',
                    name, str(run), stem + '_cam.csv', stem + '_pose.csv',
                    path], check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tours', nargs='+', default=['robot', 'world'])
    ap.add_argument('--runs', type=int, default=2)
    ap.add_argument('--outdir', default='.tmp/practice')
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    cam = CamProc()
    if cam.err or cam.latest is None:
        raise SystemExit(f'camera not usable: {cam.err or "no tag"}')
    link = open_link(radio=True)
    rep = Repositioner(link, cam)

    results = []
    for run in range(1, a.runs + 1):
        for name in a.tours:
            print(f'\n=== {name} tour, run {run} ===')
            if name == 'world':
                # No repositioning: seed the TRUE pose from the camera
                # and let the robot drive to the first dot from
                # wherever it happens to be. That is the whole point of
                # a world-frame tour.
                p = rep.fix()
                if p is None:
                    print('  camera lost the robot; skipping')
                    continue
                link.send(f'RUN:seedxy:{p[0]:.1f}:{p[1]:.1f}:{p[2]:.1f}')
                for s2 in link.lines(6):
                    if s2.startswith('OCAL:seeded'):
                        break
                print(f'  seeded at ({p[0]:.1f}, {p[1]:.1f}) '
                      f'{p[2]:.1f} deg -- starting from here')
            else:
                # The robot-relative tour has no world frame, so it must
                # physically start on the dot facing west.
                print('  repositioning to the NE dot:')
                start = rep.go(*START)
                if start is None:
                    print('  camera lost the robot; skipping')
                    continue
            time.sleep(1.0)
            t0, pose, fixes, ok = record_tour(link, cam, name)
            camrows = cam.since(t0)
            if not ok or not camrows:
                print(f'  tour did not report an end ({len(pose)} tlm, '
                      f'{len(camrows)} cam) -- skipping')
                continue
            sc = score(camrows)
            stem = f'{a.outdir}/{name}-run{run}'
            png = stem + '.png'
            chart(name, run, pose, camrows, sc, png, stem)
            results.append((name, run, sc))
            print(f'  corners: ' + '  '.join(
                f'{t} {sc[t]:.1f}cm' for t in ORDER))
            print(f'  closure {sc["closure"]:.1f} cm, end heading '
                  f'{sc["end_heading_err"]:+.1f} deg, '
                  f'{len(pose)} tlm / {len(camrows)} cam samples')
            print(f'  -> {png}')
            subprocess.run(['open', png])

    link.close()
    cam.close()

    if results:
        print('\n===== summary (camera-scored) =====')
        print(f"{'tour':8} {'run':>3} " + ' '.join(f'{t:>7}' for t in ORDER)
              + f" {'closure':>8} {'endhdg':>7}")
        for name, run, sc in results:
            print(f'{name:8} {run:>3} '
                  + ' '.join(f'{sc[t]:7.1f}' for t in ORDER)
                  + f' {sc["closure"]:8.1f} {sc["end_heading_err"]:+7.1f}')


if __name__ == '__main__':
    main()
