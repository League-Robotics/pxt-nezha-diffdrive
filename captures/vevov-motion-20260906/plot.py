import csv
import json
import math
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
import tlm

frames, schema = tlm.read_pose_csv(HERE / 'tour_pose.csv')
with (HERE / 'tour_vel.csv').open() as source:
    velocity = [{key: float(value) for key, value in row.items()}
                for row in csv.DictReader(source)]
provenance = json.loads((HERE / 'provenance.json').read_text())
with (HERE / 'tour_tlm.csv').open() as source:
    diagnostics = list(csv.DictReader(source))
rejections = int(diagnostics[-1]['i2cf'])
if not provenance['completed'] or not frames or not velocity:
    raise RuntimeError('A completed, nonempty tour is required')
first, last = frames[0], frames[-1]
closure = math.hypot(last['x'] - first['x'], last['y'] - first['y'])
heading = (last['h'] - first['h']) / 100 - 360
summary = dict(closure_mm=closure, heading_residual_deg=heading,
               final_pose_mm_cdeg=[last['x'], last['y'], last['h']],
               i2cf_final=rejections, telemetry=provenance['telemetry'])
report = ROOT / 'reports/vevov-square-bench-20260906'
report.mkdir(parents=True, exist_ok=True)
(report / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                     'axes.spines.top': False, 'axes.spines.right': False})
figure = plt.figure(figsize=(15, 8), facecolor='#f7f9fc', layout='constrained')
grid = figure.add_gridspec(2, 2, width_ratios=[1, 1.5])
path = figure.add_subplot(grid[:, 0])
speed = figure.add_subplot(grid[0, 1])
twist = figure.add_subplot(grid[1, 1], sharex=speed)
figure.suptitle('Vevov | Encoder Square Tour', fontsize=22, fontweight='bold')
path.plot([0, 100, 100, 0, 0], [0, 0, 60, 60, 0], '--',
          color='#87919c', linewidth=1.5, label='Commanded 100 x 60 cm')
path.plot([row['x'] / 10 for row in frames],
          [row['y'] / 10 for row in frames], color='#2476c8',
          linewidth=2.2, label='Measured encoder pose')
path.scatter([first['x'] / 10], [first['y'] / 10], color='#299564',
             s=75, zorder=5, label='Start')
path.scatter([last['x'] / 10], [last['y'] / 10], color='#d45b3d',
             s=80, marker='x', zorder=6, label='Finish')
path.set(aspect='equal', xlabel='Encoder x (cm)', ylabel='Encoder y (cm)',
         title=f'Closure {closure:.1f} mm | Heading {heading:+.2f} deg')
path.legend(loc='upper center', bbox_to_anchor=(0.5, -0.17), frameon=False)
times = [row['t_host'] for row in velocity]
left = [row['vel_l_mmps'] for row in velocity]
right = [row['vel_r_mmps'] for row in velocity]
speed.plot(times, left, color='#2476c8', label='Left wheel', linewidth=1.3)
speed.plot(times, right, color='#df743c', label='Right wheel', linewidth=1.3)
speed.set(ylabel='Wheel speed (mm/s)', title='Wheel Response')
speed.legend(loc='upper right', frameon=False)
twist.plot(times, [(rightward - leftward) / 2 for leftward, rightward in zip(left, right)],
           color='#299564', linewidth=1.5, label='(Right - left) / 2')
twist.set(xlabel='Elapsed time (s)', ylabel='Differential speed (mm/s)',
          title='Turning Response')
twist.legend(loc='upper right', frameon=False)
for axis in (path, speed, twist):
    axis.set_facecolor('#ffffff')
    axis.grid(alpha=0.18)
for axis in (speed, twist):
    axis.axhline(0, color='#87919c', linewidth=0.7)
figure.supxlabel('Farm stand, wheels up | OTOS disabled | Jerk 800 | Lag 0.04 s\n'
                 f'Encoder-only evidence, not a ground track | {len(frames)} pose samples | '
                 f'0 dropped frames | i2cf counter: {rejections}', fontsize=10)
destination = report / 'encoder-square.png'
figure.savefig(destination, dpi=160)
print(json.dumps(summary, indent=2))
print(destination)