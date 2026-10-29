"""Demo: GO_TO_W to random points, forever (or --moves N).

The frame is re-zeroed on the camera every --rezero moves while the robot
stands still; between zeros the go-tos fly on the robot's own odometry.
The camera also guards the boards: leaving the guard box sends STOP and
ends the demo.
"""
import argparse
import math
import random
import sys
import time

from devlink import Cam, open_serial, send_move, settled, still_pose

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='vevov')
ap.add_argument('--tag', type=int, default=53)
ap.add_argument('--moves', type=int, default=100000)
ap.add_argument('--rezero', type=int, default=4)
ap.add_argument('--speed', type=int, default=120)
ap.add_argument('--xlim', type=float, default=42.0)
ap.add_argument('--ylim', type=float, default=24.0)
ap.add_argument('--pause', type=float, default=1.0)
a = ap.parse_args()

GUARD_X, GUARD_Y = 58.0, 36.0
cam = Cam(tag=a.tag).start()
link = open_serial(a.robot)


def guard():
    q = cam.latest
    if q and (abs(q[0]) > GUARD_X or abs(q[1]) > GUARD_Y):
        link.send('STOP')
        sys.exit(f'STOPPED: robot at ({q[0]:.1f},{q[1]:.1f}) left the guard box')


def zero():
    c = still_pose(cam, 3)
    link.send('SET rebase 1')
    list(link.lines(1.0))
    return c


c0 = zero()
errs = []
p = c0
for n in range(a.moves):
    if n and n % a.rezero == 0:
        c0 = zero()
    while True:
        tx, ty = random.uniform(-a.xlim, a.xlim), random.uniform(-a.ylim, a.ylim)
        if math.hypot(tx - p[0], ty - p[1]) >= 25:
            break
    h0 = math.radians(c0[2])
    dx, dy = tx - c0[0], ty - c0[1]
    fx = (dx * math.cos(h0) + dy * math.sin(h0)) * 10
    fy = (-dx * math.sin(h0) + dy * math.cos(h0)) * 10
    st = send_move(link, f'GO_TO_W {int(round(fx))} {int(round(fy))} {a.speed} 5 30000', 35, guard)
    p = settled(cam, 15)
    e = math.hypot(p[0] - tx, p[1] - ty)
    errs.append(e)
    print(f'{n + 1:4d} go-to ({tx:+5.1f},{ty:+5.1f}) -> ({p[0]:+5.1f},{p[1]:+5.1f}) off {e:4.1f} cm '
          f'(mean {sum(errs) / len(errs):.1f}) i2cf {st.get("i2cf")}', flush=True)
    time.sleep(a.pause)
link.close()
cam.close()
