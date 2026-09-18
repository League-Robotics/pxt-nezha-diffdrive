#!/usr/bin/env python3
"""Stage tovez on the square tour's start dot: (-30, -30) facing EAST.

HEADING CONVENTION -- MEASURED tovez 2026-09-18,
captures/tovez-square-20260918/unrail.log: with the tag's raw yaw fed
through field.robot_heading_from_tag_yaw() (the fleet's +90 deg
front-edge convention), a commanded 12 cm MOVE_X displaced the tag
12.11 cm at bearing +174.4 deg while that model said the nose was at
-98.0 deg -- 87.6 deg to the LEFT. The raw tag yaw at that moment was
+172 deg, matching the travel bearing to 2.4 deg. So tovez's plate is
mounted 90 deg off the fleet convention and its residual is -90, i.e.
the robot's heading IS the raw tag yaw. tools/field_calibration.json
still carries mount_yaw_residual_deg 0 for tovez; that is a defect, not
something this script should paper over silently.

Pivots on this board run 74-110% of commanded, so nothing here trusts a
single commanded turn: every hop is MEASURE - MOVE - REMEASURE, and no
hop is longer than 25 cm, which keeps a mis-aimed leg inside the field
even when the pivot before it misses.
"""
import math, sys, time
sys.path.insert(0, 'tools'); sys.path.insert(0, 'tests/system')
from camlink import Cam
from field import wrap
from run_tour import Link

TARGET = (-30.0, -30.0, 0.0)
MOUNT_X_CM = -4.1            # tag sits 4.1 cm BEHIND the centre
RESIDUAL = -90.0             # see the module docstring
PIVOT_CRUISE, DRIVE_CRUISE = 188, 180
HOP_MAX = 25.0               # [cm]
LIM_X, LIM_Y = 67.15, 44.65  # physical field; the hop guard uses these less 8 cm


def pose(cam):
    f = cam.fix(n=8)
    if f is None:
        raise SystemExit('camera lost the robot')
    x, y, tag_yaw = f
    h = wrap(tag_yaw + 90.0 + RESIDUAL)
    r = math.radians(h)
    return (x - MOUNT_X_CM * math.cos(r), y - MOUNT_X_CM * math.sin(r), h)


def safe(x, y):
    return abs(x) <= LIM_X - 8 and abs(y) <= LIM_Y - 8


def main():
    cam = Cam(tag=52, cam='arducam-ov9782-usb-camera')
    link = Link('192.168.4.53', 37481)
    print(link.unseq('HELLO', r'^device '), flush=True)
    link._seq = 0
    link.seqd('TLM FULL')
    try:
        for hop in range(1, 13):
            x, y, h = pose(cam)
            dist = math.hypot(TARGET[0] - x, TARGET[1] - y)
            print(f'[{hop:2d}] at ({x:6.1f},{y:6.1f}) {h:7.1f} deg '
                  f'-> {dist:5.1f} cm to go', flush=True)
            if dist <= 3.0:
                break
            bearing = math.degrees(math.atan2(TARGET[1] - y, TARGET[0] - x))
            herr = wrap(bearing - h)
            if abs(herr) > 8:
                mrad = int(round(math.radians(herr) * 1000))
                print(f'     aim {herr:+6.1f} deg', flush=True)
                link.seqd(f'MOVE_X 0 {mrad} {PIVOT_CRUISE} 9000')
                link.await_motion(timeout=25); time.sleep(0.5)
                continue
            leg = min(dist, HOP_MAX)
            ex = x + leg * math.cos(math.radians(h))
            ey = y + leg * math.sin(math.radians(h))
            if not safe(ex, ey):
                raise SystemExit(f'REFUSING: hop would end at '
                                 f'({ex:.1f},{ey:.1f}), outside the field')
            print(f'     drive {leg:5.1f} cm', flush=True)
            link.seqd(f'MOVE_X {int(round(leg*10))} 0 {DRIVE_CRUISE} 12000')
            link.await_motion(timeout=25); time.sleep(0.5)

        # --- final heading: east, closed by measure-pivot-remeasure ---
        for attempt in range(1, 6):
            x, y, h = pose(cam)
            herr = wrap(TARGET[2] - h)
            print(f'  face east [{attempt}]: {h:7.1f} '
                  f'({herr:+5.1f} off)', flush=True)
            if abs(herr) <= 2.0:
                break
            mrad = int(round(math.radians(herr) * 1000))
            link.seqd(f'MOVE_X 0 {mrad} {PIVOT_CRUISE} 9000')
            link.await_motion(timeout=25); time.sleep(0.5)

        x, y, h = pose(cam)
        print(f'\nSTAGED at ({x:6.1f},{y:6.1f}) heading {h:7.1f} '
              f'(target {TARGET})', flush=True)
        print(link.status(), flush=True)
    finally:
        link.close(); cam.close()


main()
