"""How do encoder odometry and the OTOS drift over a long run?

One rebase at the start, then random GO_TO_Ws across the field until the
camera has seen --metres of travel. Nothing is ever re-zeroed: each
target is the camera's body-frame offset to a random point, laid onto
the robot's own current pose, so the robot stays on the field while its
pose sources drift freely. At every rest point one JSON line records the
camera pose and the TLM FULL row (fused odometry x y h, OTOS ox oy oh,
raw wheel counts posl posr, i2cf) for later analysis.
"""
import argparse
import json
import math
import random
import sys
import time

from devlink import CAPTURES, Cam, open_serial, send_move, still_pose, tlm

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='vevov')
ap.add_argument('--tag', type=int, default=53)
ap.add_argument('--metres', type=float, default=100.0)
ap.add_argument('--speed', type=int, default=120)
ap.add_argument('--xlim', type=float, default=50.0)
ap.add_argument('--xmin', type=float, help='lane: targets and guard keep x >= this')
ap.add_argument('--xmax', type=float, help='lane: targets and guard keep x <= this')
ap.add_argument('--ylim', type=float, default=30.0)
ap.add_argument('--log', default=str(CAPTURES / 'vevov-otos-drift-20261028' / 'drift1.jsonl'))
a = ap.parse_args()

GUARD_X, GUARD_Y = 58.0, 36.0
XMIN = a.xmin if a.xmin is not None else -a.xlim
XMAX = a.xmax if a.xmax is not None else a.xlim
GX0, GX1 = max(XMIN - 10, -GUARD_X), min(XMAX + 10, GUARD_X)
cam = Cam(tag=a.tag).start()
link = open_serial(a.robot)
out = open(a.log, 'a')


def guard():
    q = cam.latest
    if q and (not GX0 <= q[0] <= GX1 or abs(q[1]) > GUARD_Y):
        link.send('STOP')
        sys.exit(f'STOPPED: robot at ({q[0]:.1f},{q[1]:.1f}) left the guard box')


def record(n, target, st):
    c = still_pose(cam, 3)
    row = dict(n=n, t=time.time(), target=target, cam=c, tlm=tlm(link), status=st)
    out.write(json.dumps(row) + '\n')
    out.flush()
    return row


link.send('SET rebase 1')
list(link.lines(1.0))
r = record(0, None, {})
travelled = 0.0
n = 0
while travelled < a.metres * 100:
    n += 1
    cx, cy, ch = r['cam']
    while True:
        tx, ty = random.uniform(XMIN, XMAX), random.uniform(-a.ylim, a.ylim)
        if math.hypot(tx - cx, ty - cy) >= 25:
            break
    hc = math.radians(ch)
    bx = (tx - cx) * math.cos(hc) + (ty - cy) * math.sin(hc)
    by = -(tx - cx) * math.sin(hc) + (ty - cy) * math.cos(hc)
    t = r['tlm']
    ho = math.radians(t['h'] / 100)
    gx = t['x'] + 10 * (bx * math.cos(ho) - by * math.sin(ho))
    gy = t['y'] + 10 * (bx * math.sin(ho) + by * math.cos(ho))
    st = send_move(link, f'GO_TO_W {int(round(gx))} {int(round(gy))} {a.speed} 5 30000', 35, guard)
    r = record(n, [tx, ty], st)
    travelled += math.hypot(r['cam'][0] - cx, r['cam'][1] - cy)
    t = r['tlm']
    print(f'{n:4d} {travelled / 100:6.2f} m  miss {math.hypot(r["cam"][0] - tx, r["cam"][1] - ty):4.1f} cm  '
          f'cam {r["cam"][2]:+7.1f}  odo {t["h"] / 100:+8.1f}  otos {t["oh"] / 100:+7.1f}  i2cf {t.get("i2cf")}',
          flush=True)
out.close()
link.close()
cam.close()
