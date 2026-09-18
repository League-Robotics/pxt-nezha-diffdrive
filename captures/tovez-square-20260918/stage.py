#!/usr/bin/env python3
"""Stage tovez on the square tour's start pose, camera-verified.

The square tour starts at (-30, -30) cm facing EAST (tours/square.tour's
own sizing note). This drives the robot there with host-issued MOVE_X --
never a `RUN` motion verb, which resets the board
(memory: run-fiber-motion-resets-the-board).

The camera read is RAW: the aprilcam daemon on this field applies no
mount correction (registering tovez's mount via camlink.Cam.register()
left the reported yaw unchanged at ~179.6 deg, i.e. the raw front-edge
yaw), so the +90 deg convention is added here by
field.robot_heading_from_tag_yaw(), exactly as
.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md prescribes for an
unregistered reading. Tag-height parallax is therefore UNCORRECTED; it
is a few cm at the field edge and does not reach the tour, which is
scored in pure odometry.
"""
import math
import sys
import time

sys.path.insert(0, 'tools')
sys.path.insert(0, 'tests/system')

from camlink import Cam
from field import robot_heading_from_tag_yaw, require_clear_path, wrap
import park
from run_tour import Link

TARGET = (-30.0, -30.0, 0.0)       # x_cm, y_cm, heading_deg (East)
TAG, MOUNT_X_CM = 52, -4.1         # tag sits 4.1 cm BEHIND the centre
PIVOT_CRUISE = 188                 # [mm/s] 180 deg/s at b/2 = 60 mm
DRIVE_CRUISE = 200                 # [mm/s]


def pose(cam):
    """Robot CENTRE pose (x_cm, y_cm, heading_deg) from a raw tag fix."""
    f = cam.fix(n=8)
    if f is None:
        return None
    x, y, tag_yaw = f
    h = robot_heading_from_tag_yaw(tag_yaw, 0.0)
    # centre = tag + |mount_x| forward, since the tag is behind it
    r = math.radians(h)
    return (x - MOUNT_X_CM * math.cos(r), y - MOUNT_X_CM * math.sin(r), h)


def main():
    cam = Cam(tag=TAG, cam='arducam-ov9782-usb-camera')
    link = Link('192.168.4.53', 37481)
    print(link.unseq('HELLO', r'^device '), flush=True)
    link._seq = 0
    link.seqd('TLM FULL')
    try:
        for attempt in range(1, 4):
            p = pose(cam)
            if p is None:
                raise SystemExit('camera lost the robot')
            print(f'[{attempt}] at ({p[0]:6.1f}, {p[1]:6.1f}) '
                  f'{p[2]:7.1f} deg', flush=True)
            moves = park.plan(p, TARGET, pos_tol=2.0, head_tol=2.0)
            if not moves:
                print('  parked', flush=True)
                break
            print(f'  plan: {moves}', flush=True)
            # Pre-flight EVERY projected waypoint before the first byte.
            x, y, h = p
            pts = [(x, y)]
            for kind, amt in moves:
                if kind == park.PIVOT:
                    h = wrap(h + amt)
                else:
                    x += amt * math.cos(math.radians(h))
                    y += amt * math.sin(math.radians(h))
                    pts.append((x, y))
            require_clear_path(pts, what='stage to the square start dot')
            for kind, amt in moves:
                if kind == park.PIVOT:
                    mrad = int(round(math.radians(amt) * 1000))
                    link.seqd(f'MOVE_X 0 {mrad} {PIVOT_CRUISE} 8000')
                else:
                    link.seqd(f'MOVE_X {int(round(amt * 10))} 0 '
                              f'{DRIVE_CRUISE} 15000')
                ok = link.await_motion(timeout=20)
                print(f'    {kind} {amt:+7.1f} '
                      f'{"ok" if ok else "TIMEOUT"}', flush=True)
                time.sleep(0.5)
        p = pose(cam)
        print(f'staged at ({p[0]:6.1f}, {p[1]:6.1f}) {p[2]:7.1f} deg '
              f'(target {TARGET})', flush=True)
    finally:
        link.close()
        cam.close()


main()
