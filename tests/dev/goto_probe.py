"""One GO_TO_W per --target (world cm, camera frame), planned like
otos_drift.py. After each, read TLM at --reads times so a stale pose cache
shows up, and print the camera, estimator and OTOS chord for the leg."""
import argparse
import json
import math
import time

from devlink import Cam, open_serial, send_move, still_pose, tlm

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='tovez')
ap.add_argument('--tag', type=int, default=52)
ap.add_argument('--target', action='append', required=True, help='x,y in camera cm')
ap.add_argument('--reads', default='0,2,5')
ap.add_argument('--speed', type=int, default=120)
ap.add_argument('--log', required=True)
a = ap.parse_args()

cam = Cam(tag=a.tag).start()
link = open_serial(a.robot)
out = open(a.log, 'a')
c = still_pose(cam, 3)
t = tlm(link)
for spec in a.target:
    tx, ty = (float(v) for v in spec.split(','))
    hc = math.radians(c[2])
    bx = (tx - c[0]) * math.cos(hc) + (ty - c[1]) * math.sin(hc)
    by = -(tx - c[0]) * math.sin(hc) + (ty - c[1]) * math.cos(hc)
    ho = math.radians(t['h'] / 100)
    gx = t['x'] + 10 * (bx * math.cos(ho) - by * math.sin(ho))
    gy = t['y'] + 10 * (bx * math.sin(ho) + by * math.cos(ho))
    st = send_move(link, f'GO_TO_W {int(round(gx))} {int(round(gy))} {a.speed} 5 30000', 35)
    t_done = time.time()
    rows = []
    for d in (float(v) for v in a.reads.split(',')):
        time.sleep(max(0.0, t_done + d - time.time()))
        rows.append(dict(after=round(time.time() - t_done, 2), tlm=tlm(link)))
    c2 = still_pose(cam, 3)
    out.write(json.dumps(dict(target=[tx, ty], goal=[gx, gy], before=dict(cam=c, tlm=t), status=st, reads=rows, cam=c2)) + '\n')
    out.flush()
    cd = math.hypot(c2[0] - c[0], c2[1] - c[1])
    for r in rows:
        rt = r['tlm']
        print(f"  +{r['after']:4.1f}s  est ({rt['x']:.0f},{rt['y']:.0f}) h {rt['h'] / 100:.1f}  "
              f"est chord {math.hypot(rt['x'] - t['x'], rt['y'] - t['y']) / 10:.1f}  "
              f"otos chord {math.hypot(rt['ox'] - t['ox'], rt['oy'] - t['oy']) / 10:.1f}  rej {rt['rej']} step {rt['step']}")
    print(f"target ({tx},{ty}) cam end ({c2[0]:.1f},{c2[1]:.1f}) miss {math.hypot(c2[0] - tx, c2[1] - ty):.1f}  "
          f"cam chord {cd:.1f}  goal mm ({gx:.0f},{gy:.0f})  reason {st.get('reason')}", flush=True)
    c, t = c2, rows[-1]['tlm']
link.close()
cam.close()
