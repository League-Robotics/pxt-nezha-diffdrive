"""Does the OTOS measure straight-line distance? Drive --legs straights of
--mm alternately forward and back (no turns, so the lever arm drops out) and
log the camera, the OTOS centre track and the wheel counts at each rest.
Refuses to start unless both ends of the leg stay inside --box."""
import argparse
import json
import math
import sys
import time

from devlink import Cam, open_serial, send_move, still_pose, tlm

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='vevov')
ap.add_argument('--tag', type=int, default=53)
ap.add_argument('--mm', type=int, default=250)
ap.add_argument('--legs', type=int, default=6)
ap.add_argument('--speed', type=int, default=100)
ap.add_argument('--box', default='-55,-8,-33,33', help='xmin,xmax,ymin,ymax [cm]')
ap.add_argument('--log', required=True)
a = ap.parse_args()

x0, x1, y0, y1 = (float(v) for v in a.box.split(','))
cam = Cam(tag=a.tag).start()
c = still_pose(cam, 3)
h = math.radians(c[2])
ex, ey = c[0] + a.mm / 10 * math.cos(h), c[1] + a.mm / 10 * math.sin(h)
if not (x0 + 8 <= ex <= x1 - 8 and y0 + 8 <= ey <= y1 - 8):
    sys.exit(f'refusing: leg end ({ex:.1f},{ey:.1f}) is outside the box {a.box}')
link = open_serial(a.robot)
out = open(a.log, 'a')
prev = dict(cam=c, tlm=tlm(link))
out.write(json.dumps(dict(n=0, t=time.time(), **prev)) + '\n')
for n in range(1, a.legs + 1):
    mm = a.mm if n % 2 else -a.mm
    st = send_move(link, f'MOVE_X {mm} 0 {a.speed} 15000', 20)
    r = dict(cam=still_pose(cam, 3), tlm=tlm(link))
    out.write(json.dumps(dict(n=n, t=time.time(), cmd=mm, status=st, **r)) + '\n')
    out.flush()
    cd = math.hypot(r['cam'][0] - prev['cam'][0], r['cam'][1] - prev['cam'][1])
    od = math.hypot(r['tlm']['ox'] - prev['tlm']['ox'], r['tlm']['oy'] - prev['tlm']['oy']) / 10
    ed = math.hypot(r['tlm']['x'] - prev['tlm']['x'], r['tlm']['y'] - prev['tlm']['y']) / 10
    print(f'{n:2d} cmd {mm / 10:+6.1f}  cam {cd:5.2f}  otos {od:5.2f} ({od / cd:.3f})  est {ed:5.2f}  '
          f'dh cam {r["cam"][2] - prev["cam"][2]:+5.1f} otos {(r["tlm"]["oh"] - prev["tlm"]["oh"]) / 100:+5.1f}  '
          f'rej {r["tlm"].get("rej")} i2cf {r["tlm"]["i2cf"]}', flush=True)
    prev = r
link.close()
cam.close()
