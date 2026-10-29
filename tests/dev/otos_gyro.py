"""Does the OTOS heading drift with the robot sitting still?

Rebase, nudge once so the rebase lands, then never move: every --every
seconds log the camera pose and the TLM row (OTOS oh, fused h, i2cf) as
one JSON line. The firmware only reads the OTOS inside tickDrive(), which
runs only while a motion is active, so each sample first sends a
zero-speed MOVE_V to refresh the cache; the wheels never turn.
"""
import argparse
import json
import time

from devlink import CAPTURES, Cam, open_serial, send_move, still_pose, tlm

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='vevov')
ap.add_argument('--tag', type=int, default=53)
ap.add_argument('--minutes', type=float, default=30.0)
ap.add_argument('--every', type=float, default=20.0)
ap.add_argument('--log', default=str(CAPTURES / 'vevov-otos-drift-20261028' / 'gyro1.jsonl'))
a = ap.parse_args()

cam = Cam(tag=a.tag).start()
link = open_serial(a.robot)
out = open(a.log, 'a')

link.send('SET rebase 1')
list(link.lines(1.0))
send_move(link, 'MOVE_X 10 0 40 5000')
send_move(link, 'MOVE_X -10 0 40 5000')
t0 = time.time()
n = 0
while time.time() - t0 < a.minutes * 60:
    c = still_pose(cam, 1)
    send_move(link, 'MOVE_V 0 0 300', 3)
    t = tlm(link)
    out.write(json.dumps(dict(n=n, t=time.time(), cam=c, tlm=t)) + '\n')
    out.flush()
    print(f'{(time.time() - t0) / 60:6.1f} min  cam {c[2]:+8.2f}  otos {t["oh"] / 100:+8.2f}  '
          f'odo {t["h"] / 100:+8.2f}  posl {t["posl"]:.0f}  i2cf {t["i2cf"]:.0f}', flush=True)
    n += 1
    time.sleep(max(0.0, t0 + n * a.every - time.time()))
out.close()
link.close()
cam.close()
