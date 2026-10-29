"""OTOS heading: scale error or drift? Spin both ways and compare to camera.

Zeroes the frame, then full pivots CCW and CW. After each, the fused
odometry heading (TLM h) and the OTOS's own (oh) are compared with an
averaged camera heading. A scale error flips sign with turn direction; a
gyro drift does not, and grows with time instead.
"""
import argparse
import json
import math
import time

from devlink import Cam, open_serial, send_move, still_pose, wrap

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='vevov')
ap.add_argument('--tag', type=int, default=53)
ap.add_argument('--turns', default='360,360,360,360,-360,-360,-360,-360')
ap.add_argument('--log', default=None)
a = ap.parse_args()

cam = Cam(tag=a.tag).start()
link = open_serial(a.robot)
hdr, tlm = [], {}


def pump(secs):
    for s in link.lines(secs):
        f = s.split()
        if f and f[0] == 'thdr':
            hdr[:] = f[1:]
        elif f and f[0] == 't' and len(f) - 1 == len(hdr):
            try:
                tlm.update(zip(hdr, (float(v) for v in f[1:])))
            except ValueError:
                pass


c0 = still_pose(cam, 4)
link.send('SET rebase 1')
pump(1.0)
t0 = time.time()
cam_total = odo_total = otos_total = 0.0
prev_cam, prev_odo, prev_otos = c0[2], 0.0, None
rows = []
for t in (float(v) for v in a.turns.split(',')):
    send_move(link, f'MOVE_X 0 {int(round(math.radians(t) * 1000))} 60 30000')
    q = still_pose(cam, 4)
    link.send('TLM POSE')
    pump(1.2)
    link.send('TLM OFF')
    pump(0.4)
    want = cam_total + t
    cam_total = want + wrap(q[2] - prev_cam - t)  # unwrap the camera around the commanded turn
    prev_cam = q[2]
    odo = tlm['h'] / 100
    odo_total = odo
    oh = tlm['oh'] / 100
    if prev_otos is None:
        otos_total = odo
    else:
        otos_total += wrap(oh - prev_otos)
    prev_otos = oh
    row = dict(t=time.time() - t0, turn=t, cam=cam_total, odom=odo_total, otos_raw=oh)
    rows.append(row)
    print(f'{row["t"]:5.0f}s turn {t:+.0f}: camera {cam_total:+8.2f}  fused {odo_total:+8.2f} (err {odo_total - cam_total:+.2f})')
if a.log:
    json.dump(dict(zero=c0, rows=rows), open(a.log, 'w'), indent=1)
link.close()
cam.close()
