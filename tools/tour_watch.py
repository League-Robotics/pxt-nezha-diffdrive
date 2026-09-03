#!/usr/bin/env python3
"""Watch for button-triggered tours; record and chart each one.

Sits on the wireless link and waits. When the robot announces a tour
with `DBG:tour=<name>` (emitted the moment a button is pressed), this
starts recording telemetry and overhead-camera samples, stops at
`TOUR:end`, writes CSVs, renders the standard two-panel chart and
opens it. Then it goes back to waiting, so all three tours can be run
back to back without touching the host.

Deliberately passive: it never sends a motion command, so nothing here
can perturb a run -- the one exception is the single `TLM POSE`
subscribe tools/tlm.py's require_stream() sends once at startup (a
subscribe, not a poll; v6 telemetry needs it, unlike the old v5 line,
which streamed unprompted). Telemetry itself is not polled after that --
a request/reply round-trip inside a move over the link is measured to
collapse a 197.5 mm leg to 0.3 mm; the thdr/t stream flows unprompted
once subscribed, and the camera is an independent process.

  python3 tools/tour_watch.py [--outdir .tmp/tours]
"""
import argparse
import csv
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from robotlink import open_link
from camproc import Cam
from field import DOTS, RECT
import tlm

TOUR_TITLE = {
    'robot': 'Tour A — robot-relative goTo (encoder only)',
    'world': 'Tour B — world goToWorld (OTOS-guided)',
    'worldarc': 'Tour B′ — world, arc computed in test code',
    'wheels': 'Tour A+B — wheels square (open loop)',
}


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
    ap.add_argument('--wifi', metavar='NAME|IP', default=None,
        help="drive the robot over its WiFi TCP server instead of the "
             "radio relay (the default carrier since 2026-09-02)")
    ap.add_argument('--outdir', default='.tmp/tours')
    ap.add_argument('--tag', type=int, default=53)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    # camproc.Cam's own constructor already waits (up to 15s) for a
    # first sample or an ERR, so no extra fixed sleep is needed here.
    cam = Cam(tag=a.tag)
    if cam.err:
        raise SystemExit(f'camera not usable: {cam.err}')
    link = open_link(radio=not a.wifi, wifi=a.wifi)
    # --- fail loud: no point waiting indefinitely for button-triggered
    # tours if telemetry is dead -- subscribed once, here, since this
    # tool never itself sends a RUN:tour: to hang the check off of
    # (SUC-001, applied to a passive watcher instead of a triggered run).
    try:
        tlm.require_stream(link, timeout=3.0)
    except tlm.DeadTelemetryError as e:
        raise SystemExit(str(e)) from e
    print('watching for a tour -- press A, B or A+B on the robot '
          '(ctrl-C to stop)')

    run = 0
    while True:
        name = None
        stream = tlm.TlmStream()
        pose, vel, fixes = [], [], []
        t0 = None
        for s in link.lines(3600):
            if s.startswith('DBG:tour='):
                name = s.split('=', 1)[1].strip()
                t0 = time.time()
                stream = tlm.TlmStream()
                pose, vel, fixes = [], [], []
                print(f'\n>>> {name} started, recording...')
                continue
            if name is None:
                continue
            # `vel` stays empty on this path: it used to be filled from a
            # cleartext `DIAG:...vel=<l>/<r>` line (encoder counts/s,
            # scaled by travelCalib), but the firmware no longer emits
            # that verb at all, so the branch that parsed it could never
            # fire and has been removed rather than re-pointed at a
            # constant that would just as silently never run. Wheel
            # speed IS available per-frame below (`row['vl']`/`row['vr']`,
            # already mm/s -- see tools/tlm.py's wheels_mms()) but is not
            # currently plumbed into `vel`; chart()'s "no wheel-speed
            # samples" fallback covers this path until that's done.
            if s.startswith('OCAL:'):
                fixes.append(s)
            elif s.startswith('TOUR:end'):
                break
            else:
                row = stream.feed(s)
                if row is not None:
                    enc = tlm.pose_cm(row)
                    otos = tlm.otos_cm(row)
                    pose.append({'t': time.time(), 'dev': row['now'],
                                 'x': enc['x'], 'y': enc['y'], 'h': enc['h'],
                                 'ox': otos['x'], 'oy': otos['y'],
                                 'oh': otos['h']})

        if name is None:
            continue
        run += 1
        stamp = f'{a.outdir}/{run:02d}-{name}'
        # SUC-002: an instrument that returned nothing must be a loud,
        # immediate failure, not a header-only CSV or a chart drawn from
        # zero telemetry -- refuse the whole run's outputs, not just the
        # tlm.py-owned CSV, when this happens.
        try:
            meta = tlm.write_tlm_csv(stream, stamp + '_tlm.csv')
        except tlm.EmptyCaptureError as e:
            print(f'    NO TELEMETRY CAPTURED FOR THIS RUN -- refusing '
                  f'to write a pose CSV or chart: {e}')
            print('watching for the next tour...')
            continue
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
        print(f'    telemetry: {meta["frames"]} frames, '
              f'{meta["dropped"]} dropped ({meta["loss_pct"]:.1f}% loss)')
        if closure is not None:
            print(f'    closure {closure:.1f} cm (camera)')
        print(f'    -> {png}')
        subprocess.run(['open', png])
        print('watching for the next tour...')


if __name__ == '__main__':
    main()
