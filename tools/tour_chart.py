#!/usr/bin/env python3
"""Square Tour chart — the project's standard bench-run plot (matplotlib).

Reads the two CSVs the capture step writes (pose stream + wheel-speed
samples) and renders one PNG with two panels:

  1. x-y trajectory (mm), equal aspect, commanded square overlaid
     dashed, start/end markers, start-to-end closure drawn + labeled.
  2. wheel speeds vs time (cm/s), left/right lines.

Outlier hygiene: telemetry can contain corrupted samples (see the
encoder glitch-rejection work); any pose jump or wheel speed beyond
physical plausibility is excluded from the plot and counted in the
title, never allowed to destroy the axes.

Run under uv (the user-level matplotlib install is broken):
  uv run --with numpy --with matplotlib python3 tools/tour_chart.py \
      POSE_CSV VEL_CSV OUT_PNG [--side-mm 300] [--travel-calib 0.8102]
"""
import argparse
import csv

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# dataviz reference palette (validated pair): series1 blue, series2 orange
S1, S2 = '#2a78d6', '#eb6834'
INK, INK2, MUTED = '#0b0b0b', '#52514e', '#b9b7b0'

MAX_POSE_MM = 2000        # any |x|,|y| beyond this is a corrupt sample
MAX_SPEED_CM_S = 60.0     # robot tops out ~20 cm/s


def read_csv(path):
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        return [[float(v) for v in row] for row in r if row]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pose_csv')
    ap.add_argument('vel_csv')
    ap.add_argument('out_png')
    ap.add_argument('--side-mm', type=float, default=300.0)
    ap.add_argument('--travel-calib', type=float, default=0.8102)
    ap.add_argument('--title', default='Square Tour')
    a = ap.parse_args()

    pose_all = read_csv(a.pose_csv)          # t, x_mm, y_mm, h_cdeg
    vel_all = read_csv(a.vel_csv)            # t, vel_l_counts, vel_r_counts
    k = a.travel_calib / 100.0               # counts/s -> cm/s

    pose = [p for p in pose_all
            if abs(p[1]) < MAX_POSE_MM and abs(p[2]) < MAX_POSE_MM]
    vel = [(t, l * k, r * k) for t, l, r in vel_all
           if abs(l * k) < MAX_SPEED_CM_S and abs(r * k) < MAX_SPEED_CM_S]
    n_bad = (len(pose_all) - len(pose)) + (len(vel_all) - len(vel))

    if not pose:
        raise SystemExit('no plausible pose data')
    sx, sy = pose[0][1], pose[0][2]
    ex, ey = pose[-1][1], pose[-1][2]
    closure = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5
    end_h = pose[-1][3] / 100.0
    s = a.side_mm

    fig = plt.figure(figsize=(12, 6.4), facecolor='#fcfcfb')
    fig.suptitle(
        f"{a.title}   —   closure {closure:.0f} mm,  end heading "
        f"{end_h:.1f}°"
        + (f"   ({n_bad} corrupt samples excluded)" if n_bad else ""),
        color=INK, fontsize=13)

    # ---- panel 1: trajectory -------------------------------------------
    ax = fig.add_subplot(1, 2, 1)
    ax.set_facecolor('#fcfcfb')
    ax.plot([0, s, s, 0, 0], [0, 0, s, s, 0], ls='--', lw=1.2,
            color=MUTED, label='commanded square', zorder=1)
    ax.plot([p[1] for p in pose], [p[2] for p in pose], lw=1.8,
            color=S1, label='odometry path', zorder=2)
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
          f"{end_h:.1f} deg, {n_bad} corrupt samples excluded)")


if __name__ == '__main__':
    main()
