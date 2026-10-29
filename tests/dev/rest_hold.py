"""Stationary acceptance on sprint 044 firmware: the robot is never moved or
commanded, so only the idle read path feeds the estimator. Every --every
seconds log the camera pose and a TLM FULL row (estimator h, raw OTOS oh,
bias, dist, rej, step, wheel counts)."""
import argparse
import json
import time

from devlink import Cam, open_serial, still_pose, tlm

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='vevov')
ap.add_argument('--tag', type=int, default=53)
ap.add_argument('--minutes', type=float, default=30.0)
ap.add_argument('--every', type=float, default=20.0)
ap.add_argument('--log', required=True)
a = ap.parse_args()

cam = Cam(tag=a.tag).start()
link = open_serial(a.robot)
out = open(a.log, 'a')
t0 = time.time()
n = 0
while time.time() - t0 < a.minutes * 60:
    c = still_pose(cam, 1)
    t = tlm(link)
    out.write(json.dumps(dict(n=n, t=time.time(), cam=c, tlm=t)) + '\n')
    out.flush()
    print(f'{(time.time() - t0) / 60:6.1f} min  cam {c[2]:+8.2f}  est {t["h"] / 100:+8.2f}  otos {t["oh"] / 100:+8.2f}  '
          f'bias {t["bias"]:+5.0f}  dist {t["dist"]:.0f}  step {t["step"]:.0f}  posl {t["posl"]:.0f}', flush=True)
    n += 1
    time.sleep(max(0.0, t0 + n * a.every - time.time()))
out.close()
link.close()
cam.close()
