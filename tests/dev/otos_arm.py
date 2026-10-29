"""Where is the OTOS on the robot? Pivot in place and fit the circle it draws.

With the firmware's arm at zero the OTOS reports the sensor's own track.
In a pure pivot the sensor circles the centre of rotation:
    sensor_i = C + R(oh_i) (ex, ey)
A straight leg first gives the sensor's yaw (travel direction minus its
heading) and its linear scale against the camera.
"""
import argparse
import json
import math

import numpy as np

from devlink import CAPTURES, Cam, open_serial, send_move, still_pose, tlm, wrap

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='vevov')
ap.add_argument('--tag', type=int, default=53)
ap.add_argument('--leg', type=int, default=300)
ap.add_argument('--turns', default='90,90,90,90,-90,-90,-90,-90,180,180,-180,-180')
ap.add_argument('--log', default=str(CAPTURES / 'vevov-otos-drift-20261028' / 'arm1.json'))
a = ap.parse_args()

cam = Cam(tag=a.tag).start()
link = open_serial(a.robot)
rows = []


def rest(label):
    c = still_pose(cam, 3)
    t = tlm(link)
    rows.append(dict(label=label, cam=c, tlm=t))
    print(f'{label:>8}: cam ({c[0]:+6.2f},{c[1]:+6.2f}) {c[2]:+7.2f}  '
          f'otos ({t["ox"] / 10:+6.2f},{t["oy"] / 10:+6.2f}) {t["oh"] / 100:+7.2f}', flush=True)


link.send('SET rebase 1')
list(link.lines(1.0))
rest('start')
send_move(link, f'MOVE_X {a.leg} 0 100 15000')
rest('leg')
for t in (float(v) for v in a.turns.split(',')):
    send_move(link, f'MOVE_X 0 {int(round(math.radians(t) * 1000))} 60 30000')
    rest(f'{t:+.0f}')
send_move(link, f'MOVE_X {-a.leg} 0 100 15000')
rest('back')

s, e = rows[0], rows[1]
cam_d = math.hypot(e['cam'][0] - s['cam'][0], e['cam'][1] - s['cam'][1])
odx, ody = (e['tlm']['ox'] - s['tlm']['ox']) / 10, (e['tlm']['oy'] - s['tlm']['oy']) / 10
yaw = wrap(math.degrees(math.atan2(ody, odx)) - (s['tlm']['oh'] + e['tlm']['oh']) / 200)
print(f'straight leg: camera {cam_d:.2f} cm, OTOS {math.hypot(odx, ody):.2f} cm '
      f'(scale {cam_d / math.hypot(odx, ody):.4f}); travel is {yaw:+.2f} deg off the OTOS heading')

A, b = [], []
for r in rows[1:-1]:
    h = math.radians(r['tlm']['oh'] / 100)
    c, si = math.cos(h), math.sin(h)
    A += [[1, 0, c, -si], [0, 1, si, c]]
    b += [r['tlm']['ox'] / 10, r['tlm']['oy'] / 10]
sol, *_ = np.linalg.lstsq(np.array(A), np.array(b), rcond=None)
rms = float(np.sqrt(np.mean((np.array(A) @ sol - np.array(b)) ** 2)))
ex, ey = sol[2], sol[3]
y = math.radians(yaw)
fx, fy = ex * math.cos(y) + ey * math.sin(y), -ex * math.sin(y) + ey * math.cos(y)
cams = np.array([r['cam'][:2] for r in rows[1:-1]])
print(f'arm in OTOS frame: ({ex:+.2f}, {ey:+.2f}) cm, radius {math.hypot(ex, ey):.2f} cm, rms {rms:.2f} cm')
print(f'arm in robot frame (yaw removed): forward {fx:+.2f} cm, left {fy:+.2f} cm')
print(f'camera pivot-centre spread during pivots: x {np.ptp(cams[:, 0]):.2f} cm, y {np.ptp(cams[:, 1]):.2f} cm')
json.dump(dict(rows=rows, arm_otos=[ex, ey], arm_robot=[fx, fy], yaw=yaw, rms=rms,
               leg_cam=cam_d, leg_otos=math.hypot(odx, ody)), open(a.log, 'w'), indent=1)
link.close()
cam.close()
