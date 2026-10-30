"""Ticket 010 disturbance check: the robot sits still while someone bumps it
or lifts and turns it; TLM FULL and the camera pose are logged throughout.
Touching --go sends GO_TO_W back to the estimator's start point, but only if
the estimator's displacement agrees with the camera's."""
import argparse
import json
import math
import os
import time

from devlink import Cam, open_serial, settled, status, wrap

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='tovez')
ap.add_argument('--tag', type=int, default=52)
ap.add_argument('--go', required=True, help='file whose creation triggers the return leg')
ap.add_argument('--minutes', type=float, default=10.0)
ap.add_argument('--log', required=True)
a = ap.parse_args()

cam = Cam(tag=a.tag).start()
link = open_serial(a.robot)
out = open(a.log, 'a')
c0 = settled(cam)
hdr, row, start, peak = [], {}, None, 0
link.send('TLM FULL')
t0 = last = time.time()
sent = None
while time.time() - t0 < a.minutes * 60:
    for s in link.lines(0.2):
        f = s.split()
        if f and f[0] == 'thdr':
            hdr = f[1:]
        elif f and f[0] == 't' and hdr and len(f) - 1 == len(hdr):
            try:
                row = dict(zip(hdr, map(float, f[1:])))
            except ValueError:
                continue
            start = start or row
            peak = max(peak, row.get('apk', 0))
            out.write(json.dumps(dict(t=time.time() - t0, cam=cam.latest, sent=sent, **row)) + '\n')
    if not row or time.time() - last < 1.0:
        continue
    last = time.time()
    c = cam.latest or (math.nan,) * 3
    cd, ch = math.hypot(c[0] - c0[0], c[1] - c0[1]), wrap(c[2] - c0[2])
    ed, eh = math.hypot(row['x'] - start['x'], row['y'] - start['y']) / 10, wrap((row['h'] - start['h']) / 100)
    print(f'{time.time() - t0:6.1f}s cam d{cd:6.1f} h{ch:+7.1f} | est d{ed:6.1f} h{eh:+7.1f} | '
          f'otos {row["ox"]:6.0f},{row["oy"]:6.0f} enc {row["posl"]:6.0f},{row["posr"]:6.0f} | '
          f'bias {row["bias"]:+4.0f} dist {row["dist"]:.0f} | a {row.get("ax", 0):+5.0f},{row.get("ay", 0):+5.0f},'
          f'{row.get("az", 0):+6.0f} pk {peak:4.0f}', flush=True)
    peak = 0
    if sent is None and os.path.exists(a.go):
        if abs(cd - ed) > 15 or abs(wrap(ch - eh)) > 20:
            print(f'NOT returning: camera d{cd:.1f} h{ch:+.1f} vs estimator d{ed:.1f} h{eh:+.1f}', flush=True)
            sent = 'refused'
        else:
            link.send(f'GO_TO_W {int(start["x"])} {int(start["y"])} 100 5 30000')
            sent = time.time() - t0
            print('GO_TO_W sent', flush=True)
    if isinstance(sent, float) and time.time() - t0 - sent > 25:
        break
link.send('TLM OFF')
list(link.lines(0.5))
c1 = settled(cam)
print(f'end cam {c1[0]:.2f},{c1[1]:.2f},{c1[2]:.2f}  from start {math.hypot(c1[0] - c0[0], c1[1] - c0[1]):.2f} cm  '
      f'dh {wrap(c1[2] - c0[2]):+.2f}', flush=True)
print(status(link), flush=True)
out.close()
link.close()
cam.close()
