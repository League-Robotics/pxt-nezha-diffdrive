#!/usr/bin/env python3
"""Probe tovez's MOVE_X sign conventions before driving any long leg.

Written after driving tovez into the north rail on 2026-09-18 by
assuming them (.claude/rules/probe-before-driving-never-inherit-conventions.md).
Every move here is an in-place pivot or a 12 cm probe aimed along the
field's X axis, where BOTH possible signs stay inside the limits.

Camera reads are RAW: registering tovez's mount with this daemon does
not change the reported yaw (verified twice this session), so the fixed
+90 deg front-edge convention is added in code by
field.robot_heading_from_tag_yaw().
"""
import math, sys, time
sys.path.insert(0, 'tools'); sys.path.insert(0, 'tests/system')
from camlink import Cam
from field import robot_heading_from_tag_yaw, wrap
from run_tour import Link

PIVOT_CRUISE, DRIVE_CRUISE = 188, 150
LIM_X, LIM_Y = 67.15, 44.65


def pose(cam):
    f = cam.fix(n=8)
    if f is None:
        raise SystemExit('camera lost the robot')
    x, y, tag_yaw = f
    return x, y, robot_heading_from_tag_yaw(tag_yaw, 0.0)


def show(tag, p):
    print(f'  {tag:22s} tag ({p[0]:6.1f},{p[1]:6.1f})  heading {p[2]:7.1f}',
          flush=True)


def main():
    cam = Cam(tag=52, cam='arducam-ov9782-usb-camera')
    link = Link('192.168.4.53', 37481)
    print(link.unseq('HELLO', r'^device '), flush=True)
    link._seq = 0
    link.seqd('TLM FULL')
    try:
        p0 = pose(cam); show('start', p0)

        # --- probe 1: which way does a POSITIVE mrad pivot turn? -----
        print('probe 1: MOVE_X 0 +785 (commanded +45 deg)', flush=True)
        link.seqd(f'MOVE_X 0 785 {PIVOT_CRUISE} 8000')
        link.await_motion(timeout=20); time.sleep(0.6)
        p1 = pose(cam); show('after +785 mrad', p1)
        d1 = wrap(p1[2] - p0[2])
        print(f'  turned {d1:+.1f} deg for a commanded +45', flush=True)
        if abs(abs(d1) - 45) > 25:
            raise SystemExit(f'pivot magnitude is wrong ({d1:+.1f} for 45) '
                             f'-- not driving today')
        rot_sign = 1 if d1 > 0 else -1
        print(f'  => rotation sign = {rot_sign:+d} '
              f'(positive mrad turns {"CCW/left" if rot_sign>0 else "CW/right"})',
              flush=True)

        # --- face WEST (180): both probe directions stay in-field ----
        turn = wrap(180.0 - p1[2])
        mrad = int(round(math.radians(turn) * 1000)) * rot_sign
        print(f'facing west: commanding {mrad} mrad for {turn:+.1f} deg',
              flush=True)
        link.seqd(f'MOVE_X 0 {mrad} {PIVOT_CRUISE} 9000')
        link.await_motion(timeout=25); time.sleep(0.6)
        p2 = pose(cam); show('facing west', p2)

        # --- probe 2: does a POSITIVE distance go forward? -----------
        print('probe 2: MOVE_X +120 0 (commanded 12 cm)', flush=True)
        link.seqd(f'MOVE_X 120 0 {DRIVE_CRUISE} 8000')
        link.await_motion(timeout=20); time.sleep(0.6)
        p3 = pose(cam); show('after +120 mm', p3)
        dx, dy = p3[0] - p2[0], p3[1] - p2[1]
        dist = math.hypot(dx, dy)
        bearing = math.degrees(math.atan2(dy, dx))
        off = wrap(bearing - p2[2])
        print(f'  moved {dist:5.1f} cm at bearing {bearing:+.1f} '
              f'({off:+.1f} deg off the nose)', flush=True)
        if dist < 6:
            raise SystemExit(f'only {dist:.1f} cm for a commanded 12 -- '
                             f'the robot is not driving; stopping')
        fwd = abs(off) < 90
        print(f'  => positive distance drives '
              f'{"FORWARD" if fwd else "BACKWARD"}', flush=True)
        print(f'\nCONVENTIONS: rot_sign={rot_sign:+d}  '
              f'dist_forward={fwd}  travel={dist/12.0:.3f} of commanded',
              flush=True)
    finally:
        link.close(); cam.close()


main()
