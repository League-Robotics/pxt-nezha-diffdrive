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
ap.add_argument('--minutes', type=float, help='stop after this long; the log is usable at any length')
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
    for _ in range(8):
        try:
            c = still_pose(cam, 3)
            break
        except SystemExit as e:
            print(f'leg {n}: {e}; holding still and retrying', flush=True)
            link.send('STOP')
            time.sleep(10)
    else:
        sys.exit(f'STOPPED: leg {n} no camera fix for 2 minutes')
    row = dict(n=n, t=time.time(), target=target, cam=c, tlm=tlm(link), status=st)
    out.write(json.dumps(row) + '\n')
    out.flush()
    return row


link.send('SET rebase 1')
list(link.lines(1.0))
r = record(0, None, {})
travelled = 0.0
n = 0
still = 0
t0 = time.time()
while travelled < a.metres * 100 and not (a.minutes and time.time() - t0 > a.minutes * 60):
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
    prev_tlm = r['tlm']
    r = record(n, [tx, ty], st)
    cam_chord = math.hypot(r['cam'][0] - cx, r['cam'][1] - cy)
    otos_chord = math.hypot(r['tlm']['ox'] - prev_tlm['ox'], r['tlm']['oy'] - prev_tlm['oy']) / 10
    if abs(cam_chord - otos_chord) > 12:
        link.send('STOP')
        sys.exit(f'STOPPED: leg {n} camera chord {cam_chord:.1f} cm vs OTOS {otos_chord:.1f} cm -- stale camera or lost robot')
    travelled += math.hypot(r['cam'][0] - cx, r['cam'][1] - cy)
    still = still + 1 if cam_chord < 2 else 0
    if still >= 3:
        link.send('STOP')
        sys.exit(f'STOPPED: leg {n} is the third in a row that did not move -- battery flat?')
    t = r['tlm']
    print(f'{n:4d} {travelled / 100:6.2f} m  miss {math.hypot(r["cam"][0] - tx, r["cam"][1] - ty):4.1f} cm  '
          f'cam {r["cam"][2]:+7.1f}  odo {t["h"] / 100:+8.1f}  otos {t["oh"] / 100:+7.1f}  i2cf {t.get("i2cf")}',
          flush=True)
out.close()
link.close()
cam.close()
