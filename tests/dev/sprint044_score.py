"""Score an otos_drift.py log taken on sprint 044 firmware (PoseEstimator in
TLM x y h, raw OTOS in ox oy oh, plus bias rej step dist).

The estimator and the raw OTOS heading are each aligned to the camera once,
at the first row (just after the rebase), and never again. Reports pose and
heading error against the camera over the run, arrival misses per leg, the
done reasons and the estimator counters.
"""
import argparse
import collections
import json
import math

import numpy as np

from devlink import wrap

ap = argparse.ArgumentParser()
ap.add_argument('logs', nargs='+')
a = ap.parse_args()


def rot(x, y, h):
    c, s = math.cos(h), math.sin(h)
    return x * c - y * s, x * s + y * c


def score(path):
    rows = [json.loads(s) for s in open(path)]
    r0 = rows[0]
    cx0, cy0, ch0 = r0['cam']
    t0 = r0['tlm']
    h0 = math.radians(ch0) - math.radians(t0['h'] / 100)
    oh0 = ch0 - t0['oh'] / 100
    pe, he, ohe, miss, dist = [], [], [], [], [0.0]
    for p, r in zip(rows, rows[1:]):
        dist.append(dist[-1] + math.hypot(r['cam'][0] - p['cam'][0], r['cam'][1] - p['cam'][1]))
    for r in rows:
        t = r['tlm']
        dx, dy = rot((t['x'] - t0['x']) / 10, (t['y'] - t0['y']) / 10, h0)
        ex, ey = r0['cam'][0] + dx, r0['cam'][1] + dy
        pe.append(math.hypot(ex - r['cam'][0], ey - r['cam'][1]))
        he.append(wrap(math.degrees(h0) + t['h'] / 100 - r['cam'][2]))
        ohe.append(wrap(oh0 + t['oh'] / 100 - r['cam'][2]))
        if r.get('target'):
            miss.append(math.hypot(r['cam'][0] - r['target'][0], r['cam'][1] - r['target'][1]))
    half = len(rows) // 2
    rms = lambda v: float(np.sqrt(np.mean(np.square(v))))
    reasons = collections.Counter(r.get('status', {}).get('reason') for r in rows[1:])
    last = rows[-1]['tlm']
    hours = (rows[-1]['t'] - rows[0]['t']) / 3600
    print(f'== {path}')
    print(f'  {len(rows) - 1} legs, {dist[-1] / 100:.1f} m, {hours * 60:.0f} min')
    print(f'  estimator pose err: end {pe[-1]:.1f} cm, 2nd-half rms {rms(pe[half:]):.1f} cm, max {max(pe):.1f} cm')
    print(f'  estimator heading err: end {he[-1]:+.2f} deg, 2nd-half rms {rms(he[half:]):.2f} deg')
    print(f'  raw OTOS heading err: end {ohe[-1]:+.2f} deg ({ohe[-1] / hours if hours else 0:+.1f} deg/h), 2nd-half rms {rms(ohe[half:]):.2f} deg')
    if miss:
        m = np.array(miss)
        print(f'  arrival miss (camera): median {np.median(m):.2f} cm, p90 {np.percentile(m, 90):.2f} cm, max {m.max():.2f} cm')
    print(f'  reasons {dict(reasons)}')
    print(f'  counters: wrng {last.get("wrng")} dist {last.get("dist")} rej {last.get("rej")} step {last.get("step")} '
          f'bias {last.get("bias")} cdeg/min ({last.get("bias", 0) * 0.6:+.1f} deg/h) i2cf {last.get("i2cf")}')


for p in a.logs:
    score(p)
