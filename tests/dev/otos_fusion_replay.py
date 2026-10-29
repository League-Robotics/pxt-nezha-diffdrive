"""Replay otos_drift.py's log through alternative pose fusions, leg by leg,
and score each against the camera.

The log holds one rest sample per leg, so this is a leg-resolution replay:
a leg turning at least the turn-first angle is a pivot then a straight,
anything smaller one arc whose chord runs along the mean of its start and
end headings. Every source is aligned to the camera once, at row 1.

Variants:
  enc            wheel counts only, baked track width
  fw             the firmware's fused odometry as logged
  otos           the OTOS's own x/y/heading (arm-corrected)
  otosH+enc      OTOS heading, encoder distance (fuseHeading without its
                 permanent re-anchor on rejected samples)
  otos-b / otosH-b+enc   the same with the OTOS heading's bias rate removed,
                 the rate fitted on the FIRST HALF only (scored on the second)
  otos-rls / otosH-rls+enc  bias estimated causally: at each leg a recursive fit of
                 (OTOS heading - encoder heading) on [1, minutes, encoder
                 net turn] using only earlier legs -- what an onboard filter
                 could do with no camera
  camH+enc / camH+otosD  controls: the camera's own heading with each
                 distance source. Their position error is the leg model's
                 own floor, so every '+enc' row is meaningful for heading
                 only; positions are comparable only for fw/otos rows,
                 which the robot integrated tick by tick.
"""
import argparse
import json
import math

import numpy as np

from devlink import CAPTURES, wrap

ap = argparse.ArgumentParser()
ap.add_argument('--log', default=str(CAPTURES / 'vevov-otos-drift-20261028' / 'drift1.jsonl'))
ap.add_argument('--arm', default='-4.28,0.21')
ap.add_argument('--track', type=float, default=111.6 / 0.969)
ap.add_argument('--split', type=float, default=50.0)
ap.add_argument('--warmup', type=int, default=15, help='legs before the causal estimator is trusted')
a = ap.parse_args()

rows = [json.loads(s) for s in open(a.log)]
rows = [r for r in rows if r['n'] >= 1]
N = len(rows)
half = N // 2
ex, ey = (float(v) for v in a.arm.split(','))
mins = np.array([(r['t'] - rows[0]['t']) / 60 for r in rows])
cam = np.array([r['cam'] for r in rows])


def rot(x, y, h):
    c, s = math.cos(h), math.sin(h)
    return x * c - y * s, x * s + y * c


def unwrap_deg(seq):
    out = [seq[0]]
    for v in seq[1:]:
        out.append(out[-1] + wrap(v - out[-1]))
    return np.array(out)


dl = np.diff([r['tlm']['posl'] for r in rows])
dr = np.diff([r['tlm']['posr'] for r in rows])
chord_fw = [math.hypot(q['tlm']['x'] - p['tlm']['x'], q['tlm']['y'] - p['tlm']['y']) for p, q in zip(rows, rows[1:])]
k = float(np.median([c / ((l + r) / 2) for c, l, r in zip(chord_fw, dl, dr)
                     if abs(l + r) / 2 > 1500 and abs(r - l) < 0.2 * abs(l + r)]))
dist = (dl + dr) / 2 * k / 10                                  # [cm] per leg
enc_h = np.concatenate([[0.0], np.cumsum(np.degrees((dr - dl) * k / a.track))])
otos_h = unwrap_deg([r['tlm']['oh'] / 100 for r in rows])
fw_h = np.array([r['tlm']['h'] / 100 for r in rows])


def dead_reckon(head, legs=None):
    """Per-leg distances [cm] (encoder by default) laid along a heading track [deg]."""
    x, y, out = 0.0, 0.0, [(0.0, 0.0)]
    for i, d in enumerate(dist if legs is None else legs):
        h0, h1 = math.radians(head[i]), math.radians(head[i + 1])
        if abs(math.degrees(h1 - h0)) >= a.split:
            x, y = x + d * math.cos(h1), y + d * math.sin(h1)
        else:
            dh = h1 - h0
            c = d * (math.sin(dh / 2) / (dh / 2) if dh else 1.0)
            x, y = x + c * math.cos(h0 + dh / 2), y + c * math.sin(h0 + dh / 2)
        out.append((x, y))
    return np.array(out)


centre = []
for r in rows:
    dx, dy = rot(ex, ey, math.radians(r['tlm']['oh'] / 100))
    centre.append((r['tlm']['ox'] / 10 - dx, r['tlm']['oy'] / 10 - dy))
centre = np.array(centre)


def otos_debiased(bias):
    """OTOS centre track with each leg's displacement turned back by the bias angle at its midpoint."""
    out = [centre[0]]
    for i in range(N - 1):
        b = math.radians((bias[i] + bias[i + 1]) / 2)
        d = centre[i + 1] - centre[i]
        out.append(out[-1] + np.array(rot(d[0], d[1], -b)))
    return np.array(out)


# bias rate from the first half (camera used only for this fit)
cam_h = unwrap_deg(list(cam[:, 2]))
herr = otos_h - otos_h[0] - (cam_h - cam_h[0])
rate = np.polyfit(mins[:half], herr[:half], 1)[0]
bias_fit = rate * mins

# causal recursive estimate of the OTOS bias from the encoders alone
diff = otos_h - enc_h
bias_rls = np.zeros(N)
for i in range(N):
    if i >= a.warmup:
        A = np.column_stack([np.ones(i), mins[:i], enc_h[:i]])
        c, *_ = np.linalg.lstsq(A, diff[:i], rcond=None)
        bias_rls[i] = c[1] * mins[i]

variants = {
    'enc': (dead_reckon(enc_h), enc_h),
    'fw': (np.array([(r['tlm']['x'] / 10, r['tlm']['y'] / 10) for r in rows]), fw_h),
    'otos': (centre, otos_h),
    'otosH+enc': (dead_reckon(otos_h), otos_h),
    'otos-b': (otos_debiased(bias_fit), otos_h - bias_fit),
    'otosH-b+enc': (dead_reckon(otos_h - bias_fit), otos_h - bias_fit),
    'otosH-rls+enc': (dead_reckon(otos_h - bias_rls), otos_h - bias_rls),
    'otos-rls': (otos_debiased(bias_rls), otos_h - bias_rls),
    'camH+enc': (dead_reckon(cam_h), cam_h),
    'camH+otosD': (dead_reckon(cam_h, np.hypot(*np.diff(centre, axis=0).T) * np.sign(dist)), cam_h),
}

dcam = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(cam[:, :2], axis=0).T))]) / 100
marks = [np.argmin(abs(dcam - m)) for m in (10, 25, 50, 75)] + [N - 1]
print(f'{N - 1} legs, {dcam[-1]:.1f} m, {mins[-1]:.0f} min; fitted OTOS bias {rate * 60:+.1f} deg/h; '
      f'causal estimate at end {bias_rls[-1] / mins[-1] * 60:+.1f} deg/h')
print(f'{"variant":<15}' + ''.join(f'{dcam[m]:>6.0f} m pos/head' for m in marks) + '   2nd-half rms pos/head')
for name, (pos, head) in variants.items():
    phi = math.radians(wrap(cam[0, 2] - head[0]))
    p = np.array([rot(x - pos[0, 0], y - pos[0, 1], phi) for x, y in pos]) + cam[0, :2]
    pe = np.hypot(*(p - cam[:, :2]).T)
    he = np.array([wrap(h + math.degrees(phi) - c) for h, c in zip(head, cam[:, 2])])
    print(f'{name:<15}' + ''.join(f'{pe[m]:>8.1f} {he[m]:+6.1f}  ' for m in marks)
          + f'   {np.sqrt(np.mean(pe[half:] ** 2)):6.1f} {np.sqrt(np.mean(he[half:] ** 2)):5.1f}')
