"""Tag dance: is the camera's registered pose the true centre of rotation?

Pivots in place and fits, over the rest poses, the body-frame point
(ex, ey) the registered pose sits from the real pivot centre:
    pose_i = C + R(h_i) (ex, ey)
A correct mount registration gives ex = ey = 0.
"""
import argparse
import json

import numpy as np

from devlink import Cam, movex, open_serial, still_pose

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='vevov')
ap.add_argument('--tag', type=int, default=53)
ap.add_argument('--turns', default='180,180,-180,-180,90,90,90,90,-90,-90,-90,-90')
ap.add_argument('--log', default=None)
a = ap.parse_args()

cam = Cam(tag=a.tag).start()
link = open_serial(a.robot)
poses = [still_pose(cam, 3)]
print(f'start ({poses[0][0]:.2f},{poses[0][1]:.2f}) hdg {poses[0][2]:.1f}')
for t in (float(v) for v in a.turns.split(',')):
    movex(link, cam, 0, t, 60)
    p = still_pose(cam, 3)
    poses.append(p)
    print(f'turn {t:+.0f}: ({p[0]:.2f},{p[1]:.2f}) hdg {p[2]:.1f}')

rows, rhs = [], []
for x, y, h in poses:
    c, s = np.cos(np.radians(h)), np.sin(np.radians(h))
    rows += [[1, 0, c, -s], [0, 1, s, c]]
    rhs += [x, y]
sol, res, *_ = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)
fit = np.array(rows) @ sol - np.array(rhs)
xs = np.array([p[0] for p in poses])
ys = np.array([p[1] for p in poses])
print(f'pose spread: x {xs.max() - xs.min():.2f} cm, y {ys.max() - ys.min():.2f} cm')
print(f'fitted offset of registered pose from pivot centre: ex {sol[2]:+.2f} cm (forward), ey {sol[3]:+.2f} cm (left); '
      f'rms residual {np.sqrt(np.mean(fit ** 2)):.2f} cm')
if a.log:
    json.dump(dict(poses=poses, ex=sol[2], ey=sol[3], centre=sol[:2].tolist()), open(a.log, 'w'), indent=1)
link.close()
cam.close()
