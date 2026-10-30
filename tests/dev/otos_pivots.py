"""In-place pivots: the camera says how far the pivot centre really moved;
the OTOS centre track (ox, oy, arm applied on the chip) should say the same.
A wrong arm shows up as a centre track that swings with every turn. Logs
the camera, TLM and done reason at each rest."""
import argparse
import json
import math
import time

from devlink import Cam, open_serial, send_move, still_pose, tlm, wrap

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='vevov')
ap.add_argument('--tag', type=int, default=53)
ap.add_argument('--turns', default='90,90,90,90,-90,-90,-90,-90,180,-180,45,-45')
ap.add_argument('--speed', type=int, default=100)
ap.add_argument('--log', required=True)
a = ap.parse_args()

cam = Cam(tag=a.tag).start()
link = open_serial(a.robot)
out = open(a.log, 'a')
prev = dict(cam=still_pose(cam, 3), tlm=tlm(link))
out.write(json.dumps(dict(n=0, t=time.time(), **prev)) + '\n')
for n, deg in enumerate((float(v) for v in a.turns.split(',')), 1):
    st = send_move(link, f'MOVE_X 0 {int(round(math.radians(deg) * 1000))} {a.speed} 15000', 20)
    r = dict(cam=still_pose(cam, 3), tlm=tlm(link))
    out.write(json.dumps(dict(n=n, t=time.time(), cmd=deg, status=st, **r)) + '\n')
    out.flush()
    cd = math.hypot(r['cam'][0] - prev['cam'][0], r['cam'][1] - prev['cam'][1])
    od = math.hypot(r['tlm']['ox'] - prev['tlm']['ox'], r['tlm']['oy'] - prev['tlm']['oy']) / 10
    ed = math.hypot(r['tlm']['x'] - prev['tlm']['x'], r['tlm']['y'] - prev['tlm']['y']) / 10
    print(f'{n:2d} cmd {deg:+6.1f}  dh cam {wrap(r["cam"][2] - prev["cam"][2]):+7.2f} '
          f'est {(r["tlm"]["h"] - prev["tlm"]["h"]) / 100:+7.2f} otos {wrap((r["tlm"]["oh"] - prev["tlm"]["oh"]) / 100):+7.2f}  '
          f'centre moved cam {cd:4.2f} otos {od:4.2f} est {ed:4.2f} cm  {st.get("reason")}', flush=True)
    prev = r
link.close()
cam.close()
