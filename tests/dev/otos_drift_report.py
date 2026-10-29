"""Score otos_drift.py's log: how far do encoder, fused odometry and OTOS
poses drift from the camera as distance and time accumulate?

Each source is aligned to the camera once, at the first post-rebase row,
and never again. The encoder-only pose is rebuilt from raw wheel counts:
a leg whose turn is at least the turn-first angle is a pivot then a
straight; anything smaller is one arc. The OTOS pose is the sensor track
moved back to the pivot centre through the arm otos_arm.py measured.
"""
import argparse
import csv
import json
import math

import numpy as np

from devlink import CAPTURES, wrap

ap = argparse.ArgumentParser()
ap.add_argument('--log', default=str(CAPTURES / 'vevov-otos-drift-20261028' / 'drift1.jsonl'))
ap.add_argument('--arm', default='-4.28,0.21', help='OTOS sensor offset from the pivot centre, cm forward,left')
ap.add_argument('--track', type=float, default=111.6 / 0.969, help='effective track width [mm]')
ap.add_argument('--split', type=float, default=50.0, help='turn-first angle [deg]')
a = ap.parse_args()

rows = [json.loads(s) for s in open(a.log)]
rows = [r for r in rows if r['n'] >= 1]
ex, ey = (float(v) for v in a.arm.split(','))


def rot(x, y, h):
    c, s = math.cos(h), math.sin(h)
    return x * c - y * s, x * s + y * c


dc = [((r['tlm']['posl'] - p['tlm']['posl']), (r['tlm']['posr'] - p['tlm']['posr'])) for p, r in zip(rows, rows[1:])]
chords = [math.hypot(r['tlm']['x'] - p['tlm']['x'], r['tlm']['y'] - p['tlm']['y']) for p, r in zip(rows, rows[1:])]
k = float(np.median([c / ((l + rr) / 2) for c, (l, rr) in zip(chords, dc) if abs(l + rr) / 2 > 1500 and abs(rr - l) < 0.2 * abs(l + rr)]))

enc = [(0.0, 0.0, 0.0)]
for l, rr in dc:
    x, y, h = enc[-1]
    b = (l + rr) / 2 * k
    dh = (rr - l) * k / a.track
    if abs(math.degrees(dh)) >= a.split:
        x, y = x + b * math.cos(h + dh), y + b * math.sin(h + dh)
    else:
        chord = b * (math.sin(dh / 2) / (dh / 2) if dh else 1.0)
        x, y = x + chord * math.cos(h + dh / 2), y + chord * math.sin(h + dh / 2)
    enc.append((x, y, h + dh))

src = {
    'enc': [(x / 10, y / 10, math.degrees(h)) for x, y, h in enc],
    'odo': [(r['tlm']['x'] / 10, r['tlm']['y'] / 10, r['tlm']['h'] / 100) for r in rows],
    'otos': [],
}
for r in rows:
    oh = math.radians(r['tlm']['oh'] / 100)
    dx, dy = rot(ex, ey, oh)
    src['otos'].append((r['tlm']['ox'] / 10 - dx, r['tlm']['oy'] / 10 - dy, r['tlm']['oh'] / 100))

cam = [tuple(r['cam']) for r in rows]
dist, turn, t0 = [0.0], [0.0], rows[0]['t']
for p, q in zip(cam, cam[1:]):
    dist.append(dist[-1] + math.hypot(q[0] - p[0], q[1] - p[1]) / 100)
    turn.append(turn[-1] + wrap(q[2] - p[2]))

err = {}
for name, poses in src.items():
    x0, y0, h0 = poses[0]
    phi = math.radians(wrap(cam[0][2] - h0))
    out = []
    for (x, y, h), c in zip(poses, cam):
        px, py = rot(x - x0, y - y0, phi)
        out.append((math.hypot(cam[0][0] + px - c[0], cam[0][1] + py - c[1]), wrap(h + math.degrees(phi) - c[2])))
    err[name] = out

miss = [math.hypot(r['cam'][0] - r['target'][0], r['cam'][1] - r['target'][1]) for r in rows[1:]]
stalls = [r['n'] for p, r in zip(rows, rows[1:]) if r['tlm'].get('wrng', 0) > p['tlm'].get('wrng', 0)]

out_csv = a.log.replace('.jsonl', '_scored.csv')
with open(out_csv, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['n', 'minutes', 'metres', 'net_turn_deg'] + [f'{s}_{q}' for s in src for q in ('pos_cm', 'head_deg')])
    for i, r in enumerate(rows):
        w.writerow([r['n'], round((r['t'] - t0) / 60, 2), round(dist[i], 3), round(turn[i], 1)]
                   + [round(v, 2) for s in src for v in err[s][i]])

print(f'{len(rows) - 1} legs, {dist[-1]:.1f} m, {(rows[-1]["t"] - t0) / 60:.0f} min, '
      f'net turn {turn[-1]:+.0f} deg, mm/count {k:.5f}')
print(f'arrival miss: median {np.median(miss):.1f} cm, 90% {np.percentile(miss, 90):.1f} cm; '
      f'{len(stalls)} wrong-way stalls at legs {stalls}')
print(f'\n{"metres":>7} {"min":>5} {"turn":>6}   ' + '   '.join(f'{s:>4} pos/head' for s in src))
step = max(1, len(rows) // 20)
for i in list(range(0, len(rows), step)) + [len(rows) - 1]:
    print(f'{dist[i]:7.1f} {(rows[i]["t"] - t0) / 60:5.1f} {turn[i]:+6.0f}   '
          + '   '.join(f'{err[s][i][0]:5.1f} {err[s][i][1]:+6.1f}' for s in src))
absturn = np.cumsum([0.0] + [abs(wrap(q[2] - p[2])) for p, q in zip(cam, cam[1:])])
minutes = np.array([(r['t'] - t0) / 60 for r in rows])
half = len(rows) // 2
for s in src:
    he = np.array([e[1] for e in err[s]])
    for label, cols in (('net turn + time', [turn, minutes]), ('net turn + |turn|', [turn, absturn])):
        A = np.column_stack([np.ones(len(he))] + cols)
        c, *_ = np.linalg.lstsq(A, he, rcond=None)
        ch, *_ = np.linalg.lstsq(A[:half], he[:half], rcond=None)
        unit = 'deg/hour' if cols[1] is minutes else '% of |turn|'
        scale = 60 if cols[1] is minutes else 100
        print(f'{s:>4} {label:<17}: {c[1] * 100:+.2f}% of net turn, {c[2] * scale:+.2f} {unit}; '
              f'resid sd {np.std(he - A @ c):.2f} deg, 2nd half from 1st-half fit {np.std(he[half:] - A[half:] @ ch):.2f} deg')
print(f'\nwrote {out_csv}')
