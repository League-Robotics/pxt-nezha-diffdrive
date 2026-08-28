#!/usr/bin/env python3
"""Square Tour chart — the project's standard bench-run plot (matplotlib).

Reads the two CSVs the capture step writes (pose stream + wheel-speed
samples) and renders one PNG with two panels:

  1. x-y trajectory (mm), equal aspect, commanded path overlaid
     dashed, start/end markers, start-to-end closure drawn + labeled.
  2. wheel speeds vs time (cm/s), left/right lines.

Outlier hygiene: telemetry can contain corrupted samples (see the
encoder glitch-rejection work); any pose jump or wheel speed beyond
physical plausibility is excluded from the plot and counted in the
title, never allowed to destroy the axes.

Run under uv (the user-level matplotlib install is broken):
  uv run --with numpy --with matplotlib python3 tools/tour_chart.py \
      POSE_CSV VEL_CSV OUT_PNG [--side-mm 300] [--travel-calib 0.7878]
"""
import argparse
import csv
import math
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tlm

# dataviz reference palette (validated pair): series1 blue, series2 orange
S1, S2 = '#2a78d6', '#eb6834'
S3 = '#2e9e6b'   # third series: the camera track (green)
INK, INK2, MUTED = '#0b0b0b', '#52514e', '#b9b7b0'

MAX_POSE_MM = 2000        # any |x|,|y| beyond this is a corrupt sample
MAX_SPEED_CM_S = 60.0     # robot tops out ~20 cm/s


def read_csv(path):
    """-> (rows, header). The header is DATA: the vel CSV names its units."""
    with open(path) as f:
        r = csv.reader(f)
        head = next(r)
        return [[float(v) for v in row] for row in r if row], head


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pose_csv')
    ap.add_argument('vel_csv')
    ap.add_argument('out_png')
    ap.add_argument('--rect-cm', type=float, nargs=2, default=[100.0, 60.0],
                    metavar=('W', 'H'),
                    help='commanded rectangle, CENTRED on the origin -- the '
                         'shape the tours actually drive')
    ap.add_argument('--side-mm', type=float, default=None,
                    help='LEGACY: an origin-anchored SQUARE of this side '
                         'instead. Not the current tour; kept for old '
                         'captures only.')
    ap.add_argument('--travel-calib', type=float, default=0.7878)
    ap.add_argument('--title', default='Square Tour')
    # Overhead-camera track (t_host, x_cm, y_cm, yaw_rad). The only one
    # of the three paths that cannot be fooled by a wheel that slipped,
    # so when it is present it is drawn as the reference and the
    # odometry is judged against it.
    ap.add_argument('--cam-csv', default=None,
                    help='overhead camera track to overlay (cm -> mm)')
    # Odometry lives in the ROBOT's own frame -- it starts wherever the
    # pose happened to be, not at the world origin (this run began at
    # (-47,-1) mm / 8.34 deg because the parking moves preceded the
    # recording). Overlaying the two frames without saying so would
    # invent an error that is pure frame mismatch. The capture's meta
    # sidecar carries the camera's start fix, which is exactly the
    # rigid transform needed.
    ap.add_argument('--meta', default=None,
                    help='capture meta JSON; aligns odometry into the '
                         'world frame using its camera start fix')
    a = ap.parse_args()

    # SUC-002: refuse to plot a run whose capture recorded zero telemetry
    # frames -- a chart drawn from an empty capture is exactly the
    # confident-wrong-conclusion failure mode this sprint's fail-loud
    # guards exist to prevent. A MISSING sidecar (older capture, or a
    # source that never wrote one) is not itself refused here.
    meta = tlm.read_meta_sidecar(a.pose_csv)
    if meta is not None and meta.get('frames', 0) == 0:
        raise SystemExit(
            f'refusing to plot {a.pose_csv}: its capture\'s telemetry '
            f'sidecar reports frames=0 -- no telemetry was recorded for '
            f'this run')

    pose_all, _ = read_csv(a.pose_csv)
    vel_all, vel_head = read_csv(a.vel_csv)
    # Units are READ, never assumed. vl/vr off the v6 wire are already
    # mm/s; DIAG's retired `vel=` was encoder counts/s and needed
    # travelCalib. Applying the counts scale to mm/s is a ~12x error
    # that plots perfectly plausibly.
    if any('mmps' in c for c in vel_head):
        k, unit_note = 0.1, 'mm/s'
    else:
        k, unit_note = a.travel_calib / 100.0, 'counts/s'

    # Pose CSV shapes: legacy 4-col (t, x, y, h), device-timestamped
    # 5-col (t_host, t_dev_ms, x, y, h), or dual-pose 8-col with the
    # OTOS world fix appended (ox, oy, oh). Prefer device time: host
    # arrival carries serial-buffering jitter. Normalized here to
    # [t, x, y, h] (+ [ox, oy, oh] when present).
    otos_all = []
    if pose_all and len(pose_all[0]) >= 5:
        t0d = next((r[1] for r in pose_all if r[1] >= 0), 0.0)
        wide = len(pose_all[0]) >= 8
        rows = []
        for r in pose_all:
            t = (r[1] - t0d) / 1000.0 if r[1] >= 0 else r[0]
            rows.append([t, r[2], r[3], r[4]])
            if wide:
                otos_all.append([t, r[5], r[6], r[7]])
        pose_all = rows

    # Truncate at end of motion: after a move ends nothing ticks the
    # kernel, so wheel-speed DIAG polls repeat the last tick's values
    # forever -- a phantom "still turning" tail. Cut both series 1 s
    # after the last actual pose change.
    t_last_motion = pose_all[0][0] if pose_all else 0.0
    for prev, cur in zip(pose_all, pose_all[1:]):
        if (cur[1], cur[2], cur[3]) != (prev[1], prev[2], prev[3]):
            t_last_motion = cur[0]
    t_cut = t_last_motion + 1.0
    pose_all = [p for p in pose_all if p[0] <= t_cut]

    pose = [p for p in pose_all
            if abs(p[1]) < MAX_POSE_MM and abs(p[2]) < MAX_POSE_MM]
    # The OTOS series is a step function: it only changes when the
    # motion layer takes a boundary fix, so plot the DISTINCT fixes as
    # markers rather than a line pretending to be a continuous track.
    otos = [o for o in otos_all
            if o[0] <= t_cut
            and abs(o[1]) < MAX_POSE_MM and abs(o[2]) < MAX_POSE_MM]
    # An OTOS that never initialised reports a constant (0,0,0). Taken
    # at face value that becomes a single "boundary fix" diamond at the
    # world origin -- a plausible-looking data point standing for a
    # sensor that said nothing. Detect the all-zero case and say so
    # instead; a series that was asked for and is absent must be
    # labelled absent, not quietly drawn.
    otos_dead = bool(otos_all) and all(
        o[1] == 0 and o[2] == 0 and o[3] == 0 for o in otos_all)
    fixes = []
    if not otos_dead:
        for o in otos:
            if not fixes or (o[1], o[2]) != (fixes[-1][1], fixes[-1][2]):
                fixes.append(o)
    vel_cut = [v for v in vel_all if v[0] <= t_cut]
    vel = [(t, l * k, r * k) for t, l, r in vel_cut
           if abs(l * k) < MAX_SPEED_CM_S and abs(r * k) < MAX_SPEED_CM_S]
    # ONLY implausible samples are corrupt. Comparing against the
    # UNtruncated velocity source made the correctly-cut post-motion
    # tail get announced as corruption -- 16 phantom "corrupt samples"
    # on a run that had none.
    n_bad = (len(pose_all) - len(pose)) + (len(vel_cut) - len(vel))

    if not pose:
        raise SystemExit('no plausible pose data')

    # ---- camera track, and the rigid transform that makes the two
    # frames comparable. Rotation is (world start heading - odometry
    # start heading); translation puts the odometry's first sample on
    # the camera's first fix. This is a CHANGE OF FRAME, not a fit --
    # nothing here is tuned to make the curves agree.
    cam = []
    if a.cam_csv and os.path.exists(a.cam_csv):
        cam_rows, _ = read_csv(a.cam_csv)
        cam = [[r[0], r[1] * 10.0, r[2] * 10.0, r[3]] for r in cam_rows
               if r[0] <= t_cut]
    aligned = False
    if a.meta and os.path.exists(a.meta):
        import json
        m = json.load(open(a.meta))
        sw = m.get('start_world_cm')
        if sw and pose:
            ox0, oy0 = pose[0][1], pose[0][2]
            oh0 = math.radians(pose[0][3] / 100.0)
            wx0, wy0, wh0 = sw[0] * 10.0, sw[1] * 10.0, sw[2]
            rot = wh0 - oh0
            c, sn = math.cos(rot), math.sin(rot)
            pose = [[t,
                     wx0 + c * (x - ox0) - sn * (y - oy0),
                     wy0 + sn * (x - ox0) + c * (y - oy0),
                     h] for (t, x, y, h) in pose]
            aligned = True
            # The OTOS keeps its OWN world frame -- its origin and its
            # heading zero are wherever the sensor happened to start, so
            # plotted raw it draws a correctly-shaped path at an
            # arbitrary rotation (measured 2026-08-28: ~45 deg off, which
            # reads as a wild error and is purely frame). Same rigid
            # transform, from its own first sample. Its heading is in
            # CENTIDEGREES, unlike the pose heading above.
            # NB transform `fixes`, not `otos_all`: fixes is built
            # further up and is what actually gets plotted, so rewriting
            # otos_all here would silently do nothing (it did, first try).
            if fixes:
                ax0, ay0 = fixes[0][1], fixes[0][2]
                ah0 = math.radians(fixes[0][3] / 100.0)
                rot2 = wh0 - ah0
                c2, s2 = math.cos(rot2), math.sin(rot2)
                fixes = [[t,
                          wx0 + c2 * (x - ax0) - s2 * (y - ay0),
                          wy0 + s2 * (x - ax0) + c2 * (y - ay0),
                          h] for (t, x, y, h) in fixes]

    sx, sy = pose[0][1], pose[0][2]
    ex, ey = pose[-1][1], pose[-1][2]
    closure = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5
    end_h = pose[-1][3] / 100.0
    if a.side_mm is not None:
        sq = a.side_mm
        cmd_x, cmd_y = [0, sq, sq, 0, 0], [0, 0, sq, sq, 0]
        clabel = f'commanded {sq:.0f} mm square (legacy)'
    else:
        hw, hh = a.rect_cm[0] * 5.0, a.rect_cm[1] * 5.0   # cm -> mm, halved
        cmd_x = [hw, -hw, -hw, hw, hw]
        cmd_y = [hh, hh, -hh, -hh, hh]
        clabel = f'commanded {a.rect_cm[0]:.0f}x{a.rect_cm[1]:.0f} cm'

    fig = plt.figure(figsize=(12, 6.4), facecolor='#fcfcfb')
    otos_note = ""
    if otos_dead:
        otos_note = ",  OTOS: NOT REPORTING (all-zero)"
    if len(fixes) >= 2:
        oc = ((fixes[-1][1] - fixes[0][1]) ** 2
              + (fixes[-1][2] - fixes[0][2]) ** 2) ** 0.5
        otos_note = f",  OTOS closure {oc:.0f} mm"
    fig.suptitle(
        f"{a.title}   —   closure {closure:.0f} mm,  end heading "
        f"{end_h:.1f}°" + otos_note
        + (f"   ({n_bad} corrupt samples excluded)" if n_bad else ""),
        color=INK, fontsize=13)

    # ---- panel 1: trajectory -------------------------------------------
    ax = fig.add_subplot(1, 2, 1)
    ax.set_facecolor('#fcfcfb')
    ax.plot(cmd_x, cmd_y, ls='--', lw=1.2, color=MUTED, label=clabel,
            zorder=1)
    ax.plot([p[1] for p in pose], [p[2] for p in pose], lw=1.8,
            color=S1,
            label='encoder odometry' + (' (aligned to world)' if aligned
                                        else ' (robot frame)'),
            zorder=2)
    if cam:
        ax.plot([c[1] for c in cam], [c[2] for c in cam], lw=2.0,
                color=S3, marker='o', ms=3.0, mec='none', alpha=0.95,
                label=f'camera (truth, n={len(cam)})', zorder=6)
    if fixes:
        # Sparse fixes are markers; a continuously-sampled OTOS (since the
        # 2026-08-28 background sampler) is a real track and must be drawn
        # as a line -- hundreds of diamonds read as noise, not a path.
        if len(fixes) > 40:
            ax.plot([f[1] for f in fixes], [f[2] for f in fixes], lw=1.6,
                    color=S2, alpha=0.9, zorder=5,
                    label=f'OTOS (n={len(fixes)})')
        else:
            ax.plot([f[1] for f in fixes], [f[2] for f in fixes], 'D', ms=6,
                    color=S2, mec='white', mew=1.2, zorder=5,
                    label='OTOS boundary fixes')
    if otos_dead:
        ax.plot([], [], ls='none', marker='D', ms=6, color=MUTED,
                label='OTOS: no data (never initialised)')
    ax.plot([sx], [sy], 'o', ms=10, color=S1, mec='white', mew=1.5,
            zorder=4)
    ax.annotate('start', (sx, sy), textcoords='offset points',
                xytext=(10, -12), color=INK2, fontsize=10)
    ax.plot([ex], [ey], 's', ms=10, color=S2, mec='white', mew=1.5,
            zorder=4)
    ax.annotate('end', (ex, ey), textcoords='offset points',
                xytext=(10, 8), color=INK2, fontsize=10)
    ax.plot([sx, ex], [sy, ey], ls=':', lw=1.2, color=INK2, zorder=3)
    ax.annotate(f'closure {closure:.0f} mm',
                ((sx + ex) / 2, (sy + ey) / 2),
                textcoords='offset points', xytext=(12, 0),
                color=INK, fontsize=10)
    ax.set_xlabel('x [mm]', color=INK2)
    ax.set_ylabel('y [mm]', color=INK2)
    ax.set_aspect('equal', adjustable='datalim')
    ax.margins(0.15)
    ax.grid(True, lw=0.5, color=MUTED, alpha=0.5)
    ax.tick_params(colors=INK2)
    for sp in ax.spines.values():
        sp.set_color(MUTED)
    ax.legend(loc='upper left', frameon=False, fontsize=9,
              labelcolor=INK2)
    ax.set_title('Trajectory', color=INK, fontsize=11, loc='left')

    # ---- panel 2: wheel speeds -----------------------------------------
    ax2 = fig.add_subplot(1, 2, 2)
    ax2.set_facecolor('#fcfcfb')
    if vel:
        ax2.plot([v[0] for v in vel], [v[1] for v in vel], lw=1.8,
                 color=S1, label='left')
        ax2.plot([v[0] for v in vel], [v[2] for v in vel], lw=1.8,
                 color=S2, label='right')
        ax2.annotate('left', (vel[-1][0], vel[-1][1]),
                     textcoords='offset points', xytext=(6, 0),
                     color=S1, fontsize=9)
        ax2.annotate('right', (vel[-1][0], vel[-1][2]),
                     textcoords='offset points', xytext=(6, -10),
                     color=S2, fontsize=9)
    ax2.axhline(0, lw=1.2, color=MUTED)
    ax2.set_xlabel('time [s]', color=INK2)
    ax2.set_ylabel('wheel speed [cm/s]', color=INK2)
    ax2.grid(True, lw=0.5, color=MUTED, alpha=0.5)
    ax2.tick_params(colors=INK2)
    for sp in ax2.spines.values():
        sp.set_color(MUTED)
    ax2.legend(loc='lower left', frameon=False, fontsize=9,
               labelcolor=INK2)
    ax2.set_title('Wheel speeds', color=INK, fontsize=11, loc='left')

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(a.out_png, dpi=160)
    print(f"wrote {a.out_png}  (closure {closure:.0f} mm, end heading "
          f"{end_h:.1f} deg, wheel speeds from {unit_note}, "
          f"{n_bad} corrupt samples excluded)")


if __name__ == '__main__':
    main()
