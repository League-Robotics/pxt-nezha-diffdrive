#!/usr/bin/env python3
"""Get tovez off the north rail, then re-probe translation in open field.

Pivots on this board are not tracking (49.4 deg for a commanded 45, then
71.2 for a commanded 96.5), so the heading is closed by MEASURE-PIVOT-
REMEASURE rather than by one commanded turn. Only when the nose points
south -- away from the rail and into open field -- is the 12 cm
translation probe meaningful.
"""
import math, sys, time
sys.path.insert(0, 'tools'); sys.path.insert(0, 'tests/system')
from camlink import Cam
from field import robot_heading_from_tag_yaw, wrap
from run_tour import Link

PIVOT_CRUISE, DRIVE_CRUISE = 188, 150


def pose(cam):
    f = cam.fix(n=8)
    if f is None:
        raise SystemExit('camera lost the robot')
    return f[0], f[1], robot_heading_from_tag_yaw(f[2], 0.0)


def main():
    cam = Cam(tag=52, cam='arducam-ov9782-usb-camera')
    link = Link('192.168.4.53', 37481)
    print(link.unseq('HELLO', r'^device '), flush=True)
    link._seq = 0
    link.seqd('TLM FULL')
    try:
        for attempt in range(1, 6):
            p = pose(cam)
            err = wrap(-90.0 - p[2])
            print(f'[{attempt}] tag ({p[0]:6.1f},{p[1]:6.1f}) '
                  f'heading {p[2]:7.1f}  -> {err:+6.1f} from south',
                  flush=True)
            if abs(err) <= 12:
                break
            mrad = int(round(math.radians(err) * 1000))
            link.seqd(f'MOVE_X 0 {mrad} {PIVOT_CRUISE} 9000')
            link.await_motion(timeout=25); time.sleep(0.6)

        p = pose(cam)
        print('probe: MOVE_X +120 0 with the nose in open field', flush=True)
        link.seqd(f'MOVE_X 120 0 {DRIVE_CRUISE} 8000')
        link.await_motion(timeout=20); time.sleep(0.8)
        q = pose(cam)
        dx, dy = q[0] - p[0], q[1] - p[1]
        dist = math.hypot(dx, dy)
        bearing = math.degrees(math.atan2(dy, dx))
        print(f'  tag ({q[0]:6.1f},{q[1]:6.1f}) heading {q[2]:7.1f}',
              flush=True)
        print(f'  moved {dist:5.2f} cm at bearing {bearing:+.1f} '
              f'(nose was {p[2]:+.1f}); {dist/12.0*100:.0f}% of commanded',
              flush=True)
        print(link.status(), flush=True)
    finally:
        link.close(); cam.close()


main()
