#!/usr/bin/env python3
"""Watch for button-triggered tours; record and chart each one.

Sits on the wireless link and waits. When the robot announces a tour
with `DBG:tour=<name>` (emitted the moment a button is pressed), this
starts recording telemetry and overhead-camera samples, stops at
`TOUR:end`, writes CSVs, renders the standard path chart and
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
from camlink import Cam, CamDown
from field import DOTS, RECT, clears_margin, usable_half_extent
import tlm

TOUR_TITLE = {
    'robot': 'Tour A — robot-relative goTo (encoder only)',
    'world': 'Tour B — world goToWorld (OTOS-guided)',
    'worldarc': 'Tour B′ — world, arc computed in test code',
    'wheels': 'Tour A+B — wheels square (open loop)',
}


def chart(name, pose, fixes, cam, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    S1, S2 = '#2a78d6', '#eb6834'
    INK, INK2, MUTED = '#0b0b0b', '#52514e', '#b9b7b0'
    BG = '#fcfcfb'

    fig = plt.figure(figsize=(7.0, 5.6), facecolor=BG)

    # ---- the rectangle ----------------------------------------------
    ax = fig.add_subplot(1, 1, 1)
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
        # `pose` rows are decoded telemetry frames, in wire units; this
        # panel is drawn in cm, so the conversion goes through
        # tlm.otos_cm() -- the one place that scale factor is written.
        otos = [tlm.otos_cm(p) for p in pose]
        ax.plot([o['x'] for o in otos], [o['y'] for o in otos], lw=1.6,
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
    ap.add_argument('--robot', default='vevov',
        help="board name -- resolves the zavaz relay's channel/group "
             "(field_calibration.json's override, else derived from the "
             "name) when driving over --radio; ignored for --wifi")
    ap.add_argument('--outdir', default='.tmp/tours')
    ap.add_argument('--tag', type=int, default=53)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    # Cam's own constructor already waits (up to 15s) for a first
    # sample or a dead stream, so no extra fixed sleep is needed here.
    # An unreachable daemon raises; a stream that dies after connecting
    # lands in `err`.
    try:
        cam = Cam(tag=a.tag)
    except CamDown as e:
        raise SystemExit(f'camera not usable: {e}') from e
    if cam.err:
        raise SystemExit(f'camera not usable: {cam.err}')
    link = open_link(radio=not a.wifi, wifi=a.wifi, robot=a.robot)
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
        pose, fixes = [], []
        t0 = None
        for s in link.lines(3600):
            if s.startswith('DBG:tour='):
                name = s.split('=', 1)[1].strip()
                t0 = time.time()
                stream = tlm.TlmStream()
                pose, fixes = [], []
                print(f'\n>>> {name} started, recording...')
                continue
            if name is None:
                continue
            # No wheel-speed series is charted here. It used to come from
            # a cleartext `DIAG:...vel=<l>/<r>` line (encoder counts/s,
            # scaled by travelCalib) that the firmware no longer emits at
            # all, and the empty list plus its "no wheel-speed samples"
            # chart placeholder outlived the parser by two sprints. Per-
            # frame wheel speed IS on the wire (`row['vl']`/`row['vr']`,
            # already mm/s -- see tools/tlm.py's wheels_mms()) and lands
            # in the `_tlm.csv` this run writes; plumb the chart from
            # there if the panel is wanted back, rather than from a list
            # nothing fills.
            if s.startswith('OCAL:'):
                fixes.append(s)
            elif s.startswith('TOUR:end'):
                break
            else:
                row = stream.feed(s)
                if row is not None:
                    # Recorded in the WIRE's own units, unconverted:
                    # the decoded frame is the pose row this tool
                    # writes (tlm.write_pose_csv()), and chart() below
                    # converts for display through tlm.otos_cm(). This
                    # tool used to record cm/degrees and write its own
                    # cm/degree header, which tour_chart.py then read as
                    # wire units -- the 10x mis-scale sprint 034 ticket
                    # 004 exists to kill.
                    pose.append(dict(row, t_host=time.time()))

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
        # tlm.py owns the pose-CSV schema (sprint 034 ticket 004): one
        # header, in wire units, that every reader binds by name.
        tlm.write_pose_csv(pose, stamp + '_pose.csv')
        with open(stamp + '_cam.csv', 'w') as f:
            w = csv.writer(f)
            w.writerow(['t', 'x_cm', 'y_cm', 'yaw_deg'])
            for c in camrows:
                w.writerow([round(c[0], 3), round(c[1], 2), round(c[2], 2),
                            round(c[3], 2)])
        png = stamp + '.png'
        closure = chart(name, pose, fixes, camrows, png)
        print(f'    {len(pose)} telemetry, {len(camrows)} camera samples, '
              f'{len(fixes)} corner fixes')
        print(f'    telemetry: {meta["frames"]} frames, '
              f'{meta["dropped"]} dropped ({meta["loss_pct"]:.1f}% loss)')
        if closure is not None:
            print(f'    closure {closure:.1f} cm (camera)')
        # This tool never commands motion, so it has no path to
        # pre-flight -- but it holds the camera rows, so it can say
        # whether the run the operator just triggered stayed inside
        # the margin (.claude/rules/playfield-testing.md).
        if camrows:
            hx, hy = usable_half_extent()
            print(f'    geofence: '
                  f'{"clear" if clears_margin(camrows) else "LEFT THE MARGIN"}'
                  f' (usable +/-{hx:.2f} x +/-{hy:.2f} cm)')
        print(f'    -> {png}')
        subprocess.run(['open', png])
        print('watching for the next tour...')


if __name__ == '__main__':
    main()
