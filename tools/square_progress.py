#!/usr/bin/env python3
"""Square-tour progress chart: every lap of one or more "sets" overlaid on
the commanded square, plus per-lap closure against the target, in ONE PNG.

Built as a progress gauge: re-run it with a new set after each change and
the closure dots show whether the robot got better. Every number is ENCODER
truth (kernel wheel odometry, no camera): it cannot see wheel slip, tyre
scrub or a wrong trackwidth / travel_calib.

A set is `LABEL=DIR`: DIR holds the normalized lap pose CSVs that
`square_closure.py --normalize-dir` writes (`*_pose.csv`, columns
x_mm,y_mm,... with the lap start at the origin, start heading 0). One CSV
is one lap; closure is the distance from its first point to its last.

Usage (matplotlib is only available under uv):
  uv run --with numpy --with matplotlib python tools/square_progress.py \
      --set "mode 0 kernel=captures/x/square/norm/m0*" \
      --set "mode 1 motor loop=captures/x/square/norm/m1*" \
      --out captures/x/square/progress.png [--date 2026-10-27] \
      [--side 500] [--target 11]

LABEL=DIR where DIR may also be a glob of `*_pose.csv` files.
"""
import argparse
import csv
import glob
import math
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# dataviz reference palette (as tour_chart.py): series blue, orange, green
SERIES = ['#2a78d6', '#eb6834', '#2e9e6b', '#7a5bd6']
INK, INK2, MUTED = '#0b0b0b', '#52514e', '#b9b7b0'
PAPER = '#fcfcfb'


def read_lap(path):
    """-> list of (x, y) points [mm] from a normalized pose CSV, by name."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 2:
        raise ValueError(f'{path}: need at least 2 pose rows')
    for k in ('x_mm', 'y_mm'):
        if k not in rows[0]:
            raise ValueError(f'{path}: missing column {k!r}')
    return [(float(r['x_mm']), float(r['y_mm'])) for r in rows]


def closure(points):
    """Distance from the first to the last point [mm]."""
    (x0, y0), (x1, y1) = points[0], points[-1]
    return math.hypot(x1 - x0, y1 - y0)


def lap_files(spec):
    """A directory (its *_pose.csv) or a glob -> sorted list of paths."""
    if os.path.isdir(spec):
        spec = os.path.join(spec, '*_pose.csv')
    paths = sorted(glob.glob(spec))
    if not paths:
        raise SystemExit(f'no lap pose CSVs match {spec!r}')
    return paths


def load_set(label, spec):
    """-> dict(label, laps=[points], closures=[mm], mean, worst)."""
    laps = [read_lap(p) for p in lap_files(spec)]
    values = [closure(p) for p in laps]
    return {'label': label, 'laps': laps, 'closures': values,
            'mean': sum(values) / len(values), 'worst': max(values)}


def render(sets, out_path, date, side=500.0, target=11.0):
    fig, (ax, bx) = plt.subplots(
        1, 2, figsize=(13, 6.6), facecolor=PAPER,
        gridspec_kw={'width_ratios': [1.15, 1]})
    for a in (ax, bx):
        a.set_facecolor(PAPER)
        for side_name in ('top', 'right'):
            a.spines[side_name].set_visible(False)

    # Left: commanded square (start origin, heading 0 = +x, turning left).
    sq = [(0, 0), (side, 0), (side, side), (0, side), (0, 0)]
    ax.plot(*zip(*sq), color=INK2, ls='--', lw=1.2, label='commanded square')
    for i, s in enumerate(sets):
        col = SERIES[i % len(SERIES)]
        ax.plot([], [], color=col, lw=2,
                label=f"{s['label']}: closure mean {s['mean']:.1f} / "
                      f"worst {s['worst']:.1f} mm")
        for pts in s['laps']:
            ax.plot(*zip(*pts), color=col, lw=0.9, alpha=0.7)
            ax.plot(*pts[-1], 'o', color=col, ms=5, mec=INK, mew=0.5)
    ax.plot(0, 0, marker='s', color=INK, ms=8, ls='', label='start (origin)')
    ax.set_aspect('equal')
    ax.set_xlabel('x [mm]', color=INK2)
    ax.set_ylabel('y [mm]', color=INK2)
    ax.grid(color=MUTED, alpha=0.4, lw=0.5)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.1), fontsize=9,
              frameon=False)
    ax.set_title('lap tracks, dots = lap end points', color=INK2, fontsize=10)

    # Right: per-lap closure dots per set, target line.
    for i, s in enumerate(sets):
        col = SERIES[i % len(SERIES)]
        xs = [i + 1 + (j - (len(s['closures']) - 1) / 2) * 0.12
              for j in range(len(s['closures']))]
        bx.plot(xs, s['closures'], 'o', color=col, ms=8, mec=INK, mew=0.5)
        bx.hlines(s['mean'], i + 0.6, i + 1.4, color=col, lw=2)
        bx.text(i + 1.42, s['mean'], f"mean {s['mean']:.1f}", color=INK2,
                va='center', fontsize=9)
    bx.axhline(target, color='#c0392b', ls='--', lw=1.2)
    bx.text(0.5, target, f' target {target:g} mm', color='#c0392b',
            va='bottom', fontsize=9)
    bx.set_xlim(0.4, len(sets) + 0.9)
    bx.set_ylim(bottom=0)
    bx.set_xticks(range(1, len(sets) + 1))
    bx.set_xticklabels([s['label'] for s in sets], color=INK2)
    bx.set_ylabel('closure, start to end [mm]', color=INK2)
    bx.grid(axis='y', color=MUTED, alpha=0.4, lw=0.5)
    bx.set_title('closure per lap (line = mean)', color=INK2, fontsize=10)

    fig.suptitle(f'Square tour progress, {side:g} mm side - ENCODER truth '
                 f'(zuvat, no camera) - {date}', color=INK, fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=130, facecolor=PAPER)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--set', action='append', required=True, dest='sets',
                    metavar='LABEL=DIR', help='repeatable')
    ap.add_argument('--out', required=True)
    ap.add_argument('--date', required=True)
    ap.add_argument('--side', type=float, default=500.0)  # [mm]
    ap.add_argument('--target', type=float, default=11.0)  # [mm]
    a = ap.parse_args(argv)
    loaded = []
    for text in a.sets:
        label, _, spec = text.partition('=')
        if not label or not spec:
            raise SystemExit(f'--set {text!r}: need LABEL=DIR')
        loaded.append(load_set(label, spec))
    render(loaded, a.out, a.date, a.side, a.target)
    for s in loaded:
        print(f"{s['label']}: n={len(s['laps'])} closure mean "
              f"{s['mean']:.1f} worst {s['worst']:.1f} mm "
              f"({', '.join(f'{c:.1f}' for c in s['closures'])})")


if __name__ == '__main__':
    main()
