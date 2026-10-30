"""Does the OTOS heading drift with the robot sitting still?

Rebase, then never move: every --every seconds log the TLM row (OTOS oh,
fused h, wheel counts, i2cf) and, with --tag, the camera pose as one JSON
line. The firmware only reads the OTOS inside tickDrive(), which runs only
while a motion is active, so each sample first sends a zero-speed MOVE_V
to refresh the cache (and to land the rebase); the wheels never turn.
--tag 0 runs off-camera (bench): stillness is then the wheel counts only.
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

cam = Cam(tag=a.tag).start() if a.tag else None
link = open_serial(a.robot)
out = open(a.log, 'a')

link.send('SET rebase 1')
list(link.lines(1.0))
send_move(link, 'MOVE_V 0 0 300', 3)
t0 = time.time()
n = 0
while time.time() - t0 < a.minutes * 60:
    c = still_pose(cam, 1) if cam else None
    send_move(link, 'MOVE_V 0 0 300', 3)
    t = tlm(link)
    out.write(json.dumps(dict(n=n, t=time.time(), cam=c, tlm=t)) + '\n')
    out.flush()
    print(f'{(time.time() - t0) / 60:6.1f} min  cam {c[2] if c else float("nan"):+8.2f}  otos {t["oh"] / 100:+8.2f}  '
          f'odo {t["h"] / 100:+8.2f}  posl {t["posl"]:.0f} posr {t["posr"]:.0f}  i2cf {t["i2cf"]:.0f}', flush=True)
    n += 1
    time.sleep(max(0.0, t0 + n * a.every - time.time()))
out.close()
link.close()
if cam:
    cam.close()
