#!/usr/bin/env python3
"""Watch for button-triggered tours; record and chart each one.

Sits on the wireless link and waits. When the robot announces a tour
with `DBG:tour=<name>` (emitted the moment a button is pressed), this
starts recording telemetry and overhead-camera samples, stops at
`TOUR:end`, writes CSVs, renders the standard two-panel chart and
opens it. Then it goes back to waiting, so all three tours can be run
back to back without touching the host.

Deliberately passive: it never sends a motion command, so nothing here
can perturb a run. Telemetry is NOT polled either -- a request/reply
round-trip inside a move over the link is measured to collapse a
197.5 mm leg to 0.3 mm; TLM streams unprompted and the camera is an
independent process.

  python3 tools/tour_watch.py [--outdir .tmp/tours]
"""
import argparse
import csv
import math
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from robotlink import open_link

VENV = '/Volumes/Proj/proj/RobotProjects/AprilTags/.venv/bin/python3'
CAMLINK = __file__.rsplit('/', 1)[0] + '/camlink.py'

# The playfield's four orange dots (main-playfield, A1-centred, cm) --
# the rectangle every tour is trying to trace.
DOTS = {'NW': (-50.0, 30.0), 'NE': (50.0, 30.0),
        'SE': (50.0, -30.0), 'SW': (-50.0, -30.0)}
RECT = [DOTS['NE'], DOTS['NW'], DOTS['SW'], DOTS['SE'], DOTS['NE']]

TOUR_TITLE = {
    'robot': 'Tour A — robot-relative goTo (encoder only)',
    'world': 'Tour B — world goToWorld (OTOS-guided)',
    'worldarc': 'Tour B′ — world, arc computed in test code',
    'wheels': 'Tour A+B — wheels square (open loop)',
}


class Cam(threading.Thread):
    """Camera samples in the background, timestamped, always running."""

    def __init__(self, tag=53, hz=20.0):
        super().__init__(daemon=True)
        self.samples = []          # (t, x_cm, y_cm, yaw_deg)
        self.err = None
        self.lock = threading.Lock()
        self.p = subprocess.Popen(
            [VENV, CAMLINK, '--tag', str(tag), '--hz', str(hz)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            bufsize=1)
        self.start()

    def run(self):
        for line in self.p.stdout:
            line = line.strip()
            if line.startswith('ERR'):
                with self.lock:
                    self.err = line
                return
            if line == 'NOTAG':
                continue
            try:
                yaw, x, y = (float(v) for v in line.split())
            except ValueError:
                continue
            with self.lock:
                self.samples.append((time.time(), x, y, yaw))

    def since(self, t0):
        with self.lock:
            return [s for s in self.samples if s[0] >= t0]

    def close(self):
        self.p.terminate()


def chart(name, pose, vel, fixes, cam, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    S1, S2 = '#2a78d6', '#eb6834'
    INK, INK2, MUTED = '#0b0b0b', '#52514e', '#b9b7b0'
    BG = '#fcfcfb'

    fig = plt.figure(figsize=(12.5, 5.6), facecolor=BG)

    # ---- panel 1: the rectangle -------------------------------------
    ax = fig.add_subplot(1, 2, 1)
    ax.set_facecolor(BG)
    ax.plot([p[0] for p in RECT], [p[1] for p in RECT], ls='--', lw=1.2,
            color=MUTED, label='the four orange dots', zorder=1)
    for tag, (dx, dy) in DOTS.items():
        ax.plot([dx], [dy], 'o', ms=13, color='#f0a35e', mec='white',
                mew=1.5, zorder=2)
        ax.annotate(tag, (dx, dy), textcoords='offset points',
                    xytext=(0, 12), ha='center', color=INK2, fontsize=8)

    if cam:
        ax.plot([c[1] for c in cam], [c[2] for c in cam], lw=2,
                color=S2, label='camera (truth)', zorder=4)
    if pose:
        ax.plot([p['ox'] for p in pose], [p['oy'] for p in pose], lw=1.6,
                color=S1, label='robot-reported (OTOS)', zorder=3)

    closure = None
    if cam:
        sx, sy = cam[0][1], cam[0][2]
        ex, ey = cam[-1][1], cam[-1][2]
        closure = math.hypot(ex - sx, ey - sy)
        ax.plot([sx], [sy], 'o', ms=10, color=S2, mec='white', mew=1.5,
                zorder=6)
        ax.plot([ex], [ey], 's', ms=10, color=S2, mec='white', mew=1.5,
                zorder=6)
        ax.plot([sx, ex], [sy, ey], ls=':', lw=1.2, color=INK, zorder=5)
        ax.annotate(f'closure {closure:.1f} cm', ((sx+ex)/2, (sy+ey)/2),
                    textcoords='offset points', xytext=(10, 6),
                    color=INK, fontsize=10)

    ax.set_xlabel('x [cm]  (+east)', color=INK2)
    ax.set_ylabel('y [cm]  (+north)', color=INK2)
    ax.set_aspect('equal', adjustable='datalim')
    ax.margins(0.15)
    ax.grid(True, lw=0.5, color=MUTED, alpha=0.5)
    ax.tick_params(colors=INK2)
    for sp in ax.spines.values():
        sp.set_color(MUTED)
    ax.legend(loc='upper left', frameon=False, fontsize=9, labelcolor=INK2)
    ax.set_title('Path', color=INK, fontsize=11, loc='left')

    # ---- panel 2: wheel speeds --------------------------------------
    ax2 = fig.add_subplot(1, 2, 2)
    ax2.set_facecolor(BG)
    if vel:
        t0 = vel[0]['t']
        ax2.plot([v['t'] - t0 for v in vel], [v['l'] for v in vel], lw=1.8,
                 color=S1, label='left')
        ax2.plot([v['t'] - t0 for v in vel], [v['r'] for v in vel], lw=1.8,
                 color=S2, label='right')
        ax2.legend(loc='lower left', frameon=False, fontsize=9,
                   labelcolor=INK2)
    else:
        ax2.annotate('no wheel-speed samples\n(telemetry is not polled '
                     'during a run)', (0.5, 0.5), xycoords='axes fraction',
                     ha='center', color=INK2, fontsize=10)
    ax2.axhline(0, lw=1.2, color=MUTED)
    ax2.set_xlabel('time [s]', color=INK2)
    ax2.set_ylabel('wheel speed [cm/s]', color=INK2)
    ax2.grid(True, lw=0.5, color=MUTED, alpha=0.5)
    ax2.tick_params(colors=INK2)
    for sp in ax2.spines.values():
        sp.set_color(MUTED)
    ax2.set_title('Wheel speeds', color=INK, fontsize=11, loc='left')

    title = TOUR_TITLE.get(name, f'Tour {name}')
    sub = f'closure {closure:.1f} cm' if closure is not None else ''
    fig.suptitle(f'{title}   —   {sub}', color=INK, fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=160)
    return closure


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--outdir', default='.tmp/tours')
    ap.add_argument('--tag', type=int, default=53)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    cam = Cam(a.tag)
    time.sleep(1.5)
    if cam.err:
        raise SystemExit(f'camera not usable: {cam.err}')
    link = open_link(radio=True)
    print('watching for a tour -- press A, B or A+B on the robot '
          '(ctrl-C to stop)')

    run = 0
    while True:
        name = None
        pose, vel, fixes = [], [], []
        t0 = None
        for s in link.lines(3600):
            if s.startswith('DBG:tour='):
                name = s.split('=', 1)[1].strip()
                t0 = time.time()
                pose, vel, fixes = [], [], []
                print(f'\n>>> {name} started, recording...')
                continue
            if name is None:
                continue
            if s.startswith('TLM:'):
                f = s[4:].split(':')
                if len(f) == 7:
                    try:
                        pose.append({'t': time.time(), 'dev': int(f[0]),
                                     'x': int(f[1])/10, 'y': int(f[2])/10,
                                     'h': int(f[3])/100,
                                     'ox': int(f[4])/10, 'oy': int(f[5])/10,
                                     'oh': int(f[6])/100})
                    except ValueError:
                        pass
            elif s.startswith('DIAG:'):
                i = s.find('vel=')
                if i >= 0:
                    try:
                        vl, vr = s[i+4:].split(',')[0].split('/')
                        k = 0.8102/100
                        vel.append({'t': time.time(), 'l': int(vl)*k,
                                    'r': int(vr)*k})
                    except ValueError:
                        pass
            elif s.startswith('OCAL:'):
                fixes.append(s)
            elif s.startswith('TOUR:end'):
                break

        if name is None:
            continue
        run += 1
        stamp = f'{a.outdir}/{run:02d}-{name}'
        camrows = cam.since(t0)
        with open(stamp + '_pose.csv', 'w') as f:
            w = csv.writer(f)
            w.writerow(['t', 'dev_ms', 'enc_x_cm', 'enc_y_cm', 'enc_h_deg',
                        'otos_x_cm', 'otos_y_cm', 'otos_h_deg'])
            for p in pose:
                w.writerow([round(p['t'], 3), p['dev'], p['x'], p['y'],
                            p['h'], p['ox'], p['oy'], p['oh']])
        with open(stamp + '_cam.csv', 'w') as f:
            w = csv.writer(f)
            w.writerow(['t', 'x_cm', 'y_cm', 'yaw_deg'])
            for c in camrows:
                w.writerow([round(c[0], 3), round(c[1], 2), round(c[2], 2),
                            round(c[3], 2)])
        png = stamp + '.png'
        closure = chart(name, pose, vel, fixes, camrows, png)
        print(f'    {len(pose)} telemetry, {len(camrows)} camera samples, '
              f'{len(fixes)} corner fixes')
        if closure is not None:
            print(f'    closure {closure:.1f} cm (camera)')
        print(f'    -> {png}')
        subprocess.run(['open', png])
        print('watching for the next tour...')


if __name__ == '__main__':
    main()
