#!/usr/bin/env python3
"""Square-tour closure metric: per-lap start-to-end distance and heading
residual, per mode, from `tour_capture.py` recordings.

Every number is ENCODER truth (kernel wheel odometry in the telemetry
frames). It says the wheels landed on their counts; it cannot see wheel
slip, tyre scrub, or a wrong trackwidth / travel_calib (a robot with a
placeholder geometry can close its odometry square perfectly and still
not close on the floor). Nothing here replaces an overhead camera.

Input is each lap's `<prefix>_tlm.csv` (the raw wire columns tlm.py
writes: seq,now,flags,x,y,h,ox,oy,oh,vl,vr,i2cf; x/y mm, h cdeg, vl/vr
mm/s, now device ms). One CSV is one lap; its first frame is the start
and its last frame the end, because the robot is idle at both. The pose
is NOT reset between laps, so each lap is scored on its own start/end.

Usage:
  python3 tools/square_closure.py --mode 0=captures/x/m0_lap*_tlm.csv \
      --mode 1=captures/x/m1_lap*_tlm.csv --out-prefix captures/x/closure \
      [--target-mm 11] [--normalize-dir DIR]

`--normalize-dir` also writes, per lap, a pose/vel CSV pair in the
tour_chart.py schema with the lap start moved to the origin and the start
heading to 0, so `tour_chart.py ... --side-mm <side_mm>` draws it
against the commanded square.
"""
import argparse
import csv
import glob
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MOVING_MMPS = 5.0   # a wheel above this speed counts as moving


def read_tlm_csv(path):
    """-> list of dict rows with float values (columns by name)."""
    with open(path) as f:
        rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]
    if len(rows) < 2:
        raise ValueError(f'{path}: need at least 2 frames, got {len(rows)}')
    for k in ('now', 'x', 'y', 'h', 'vl', 'vr', 'i2cf'):
        if k not in rows[0]:
            raise ValueError(f'{path}: missing column {k!r}')
    return rows


def score_lap(rows):
    """-> dict: closure_mm, heading_deg (signed residual), lap_s, i2cf_growth.

    Closure is |end - start| in the odometry plane. The heading residual is
    the end heading minus the start heading modulo 360, so a lap that turned
    360 deg + 3 deg reads +3. lap_s runs from the first frame with a wheel
    above MOVING_MMPS to the last such frame (device clock).
    """
    a, b = rows[0], rows[-1]
    closure = math.hypot(b['x'] - a['x'], b['y'] - a['y'])
    resid = ((b['h'] - a['h']) / 100.0 + 180.0) % 360.0 - 180.0
    moving = [r for r in rows
              if abs(r['vl']) > MOVING_MMPS or abs(r['vr']) > MOVING_MMPS]
    lap_s = ((moving[-1]['now'] - moving[0]['now']) / 1000.0) if moving else 0.0
    return {'closure_mm': closure, 'heading_deg': resid, 'lap_s': lap_s,
            'i2cf_growth': b['i2cf'] - a['i2cf']}


def summarize(laps):
    """-> dict of mean / worst across a list of score_lap() dicts."""
    n = len(laps)
    c = [l['closure_mm'] for l in laps]
    h = [abs(l['heading_deg']) for l in laps]
    return {
        'n': n,
        'closure_mean_mm': sum(c) / n, 'closure_worst_mm': max(c),
        'heading_mean_deg': sum(h) / n, 'heading_worst_deg': max(h),
        'lap_mean_s': sum(l['lap_s'] for l in laps) / n,
        'i2cf_mean': sum(l['i2cf_growth'] for l in laps) / n,
    }


def verdict(summary, target_mm):
    """'met' when the WORST lap closes better than target_mm, else 'not met'."""
    return 'met' if summary['closure_worst_mm'] < target_mm else 'not met'


def normalize_lap(rows):
    """-> (pose_rows, vel_rows): lap start at the origin, start heading 0."""
    a = rows[0]
    h0 = math.radians(a['h'] / 100.0)
    c, s = math.cos(-h0), math.sin(-h0)
    t0 = a['now']
    pose, vel = [], []
    for r in rows:
        dx, dy = r['x'] - a['x'], r['y'] - a['y']
        t = (r['now'] - t0) / 1000.0
        pose.append({'t_host': t, 'now': r['now'], 'x': round(dx * c - dy * s),
                     'y': round(dx * s + dy * c), 'h': r['h'] - a['h'],
                     'ox': 0, 'oy': 0, 'oh': 0})
        vel.append((round(t, 3), r['vl'], r['vr']))
    return pose, vel


def radial_deviation(rows, radius_mm, ccw=True):
    """-> (mean_mm, max_mm): how far the track strays from the commanded
    circle. The lap is moved to start at the origin heading 0 first, so the
    commanded centre is radius_mm to the left (CCW) or right (CW) of it.
    Encoder truth, like everything else here."""
    pose, _ = normalize_lap(rows)
    cy = radius_mm if ccw else -radius_mm
    dev = [abs(math.hypot(p['x'], p['y'] - cy) - radius_mm) for p in pose]
    return sum(dev) / len(dev), max(dev)


def write_normalized(rows, prefix):
    import tlm
    pose, vel = normalize_lap(rows)
    tlm.write_pose_csv(pose, prefix + '_pose.csv')
    with open(prefix + '_vel.csv', 'w') as f:
        w = csv.writer(f)
        w.writerow(['t_host', 'vel_l_mmps', 'vel_r_mmps'])
        w.writerows(vel)


def parse_mode_arg(text):
    label, _, pattern = text.partition('=')
    paths = sorted(glob.glob(pattern))
    if not label or not paths:
        raise SystemExit(f'--mode {text!r}: need LABEL=GLOB matching files')
    return label, paths


def lap_name(path):
    base = os.path.basename(path)
    return base[:-len('_tlm.csv')] if base.endswith('_tlm.csv') else base


def render_markdown(per_lap, summaries, target_mm):
    out = ['**ENCODER truth (kernel wheel odometry). No camera: the encoders '
           'cannot see wheel slip, tyre scrub or a wrong trackwidth / '
           'travel_calib.**', '',
           '| mode | lap | closure [mm] | heading residual [deg] | '
           'lap time [s] | i2cf growth |', '|---|---|---|---|---|---|']
    for label, laps in per_lap:
        for name, l in laps:
            out.append(f"| {label} | {name} | {l['closure_mm']:.1f} | "
                       f"{l['heading_deg']:+.2f} | {l['lap_s']:.1f} | "
                       f"{l['i2cf_growth']:.0f} |")
    out += ['', f'| mode | laps | closure mean [mm] | closure worst [mm] | '
            f'heading mean abs [deg] | heading worst abs [deg] | '
            f'lap mean [s] | i2cf/lap | target < {target_mm:g} mm |',
            '|---|---|---|---|---|---|---|---|---|']
    for label, s in summaries:
        out.append(f"| {label} | {s['n']} | {s['closure_mean_mm']:.1f} | "
                   f"{s['closure_worst_mm']:.1f} | {s['heading_mean_deg']:.2f}"
                   f" | {s['heading_worst_deg']:.2f} | {s['lap_mean_s']:.1f}"
                   f" | {s['i2cf_mean']:.1f} | {verdict(s, target_mm)} |")
    return '\n'.join(out) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--mode', action='append', required=True,
                    metavar='LABEL=GLOB')
    ap.add_argument('--out-prefix', required=True,
                    help='writes <prefix>.csv and <prefix>.md')
    ap.add_argument('--target-mm', type=float, default=11.0)
    ap.add_argument('--normalize-dir', default=None)
    ap.add_argument('--circle-cm', type=float, default=None, metavar='R',
                    help='the path is a circle of this radius: also write '
                         '<prefix>_radial.csv with the per-lap mean and max '
                         'distance of the track from the commanded circle')
    ap.add_argument('--cw', action='store_true',
                    help='with --circle-cm: driven clockwise')
    a = ap.parse_args(argv)
    radial = []

    per_lap, summaries = [], []
    for text in a.mode:
        label, paths = parse_mode_arg(text)
        laps = []
        for p in paths:
            rows = read_tlm_csv(p)
            laps.append((lap_name(p), score_lap(rows)))
            if a.circle_cm is not None:
                radial.append((label, lap_name(p), *radial_deviation(
                    rows, a.circle_cm * 10.0, not a.cw)))
            if a.normalize_dir:
                os.makedirs(a.normalize_dir, exist_ok=True)
                write_normalized(rows, os.path.join(
                    a.normalize_dir, lap_name(p) + '_norm'))
        per_lap.append((label, laps))
        summaries.append((label, summarize([l for _, l in laps])))

    with open(a.out_prefix + '.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['mode', 'lap', 'closure_mm', 'heading_deg', 'lap_s',
                    'i2cf_growth'])
        for label, laps in per_lap:
            for name, l in laps:
                w.writerow([label, name, f"{l['closure_mm']:.2f}",
                            f"{l['heading_deg']:.3f}", f"{l['lap_s']:.2f}",
                            f"{l['i2cf_growth']:.0f}"])
        w.writerow([])
        w.writerow(['mode', 'n', 'closure_mean_mm', 'closure_worst_mm',
                    'heading_mean_abs_deg', 'heading_worst_abs_deg',
                    'lap_mean_s', 'i2cf_mean', f'target_{a.target_mm:g}mm'])
        for label, s in summaries:
            w.writerow([label, s['n'], f"{s['closure_mean_mm']:.2f}",
                        f"{s['closure_worst_mm']:.2f}",
                        f"{s['heading_mean_deg']:.3f}",
                        f"{s['heading_worst_deg']:.3f}",
                        f"{s['lap_mean_s']:.2f}", f"{s['i2cf_mean']:.1f}",
                        verdict(s, a.target_mm)])
    if radial:
        with open(a.out_prefix + '_radial.csv', 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['mode', 'lap', 'radial_dev_mean_mm',
                        'radial_dev_max_mm'])
            for label, name, mean, worst in radial:
                w.writerow([label, name, f'{mean:.1f}', f'{worst:.1f}'])
    md = render_markdown(per_lap, summaries, a.target_mm)
    with open(a.out_prefix + '.md', 'w') as f:
        f.write(md)
    print(md)


if __name__ == '__main__':
    main()
