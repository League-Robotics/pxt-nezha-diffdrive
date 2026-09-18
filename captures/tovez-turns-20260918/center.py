#!/usr/bin/env python3
"""Put tovez in the middle of the field, then prove the pose frame.

POSE FRAME -- the thing I got wrong earlier today. `Cam.register()`
registers the mount with the daemon, after which the reported `yaw_rad`
IS the robot's heading. It must NOT go through
`robot_heading_from_tag_yaw()`; that is for a raw/unregistered reading
only, and adding the +90 deg convention twice rotates every absolute
bearing by 90 (.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md,
"registered vs raw: who adds the 90"; the same double-add bit
tools/field_dance.py on tovez, 2026-09-04). So: registered read, yaw
used unchanged.

Finishes with a 12 cm probe whose travel bearing must land within a few
degrees of the heading. That is the gate: if it does not, the frame is
wrong and nothing downstream is worth measuring.
"""
import math, os, sys, time
sys.path.insert(0, 'tools'); sys.path.insert(0, 'tests/system')
from camlink import Cam
from field import wrap
from run_tour import Link

PIVOT_CRUISE, DRIVE_CRUISE = 188, 180
HOP_MAX = 25.0


def pose(cam):
    """(x_cm, y_cm, heading_deg) -- registered read, yaw UNCHANGED."""
    f = cam.fix(n=8)
    if f is None:
        raise SystemExit('camera lost the robot')
    return f[0], f[1], wrap(f[2])


def main():
    Cam.register('tovez')
    cam = Cam(tag=52, cam='arducam-ov9782-usb-camera')
    link = Link(os.environ.get('TOVEZ_HOST','192.168.4.50'), int(os.environ.get('TOVEZ_PORT','41069')))
    print(link.unseq('HELLO', r'^device '), flush=True)
    link._seq = 0
    link.seqd('TLM FULL')
    try:
        for hop in range(1, 13):
            x, y, h = pose(cam)
            dist = math.hypot(x, y)
            print(f'[{hop:2d}] ({x:6.1f},{y:6.1f}) {h:7.1f} deg '
                  f'-> {dist:5.1f} cm from centre', flush=True)
            if dist <= 4.0:
                break
            bearing = math.degrees(math.atan2(-y, -x))
            herr = wrap(bearing - h)
            if abs(herr) > 8:
                print(f'     aim {herr:+6.1f}', flush=True)
                link.seqd(f'MOVE_X 0 {int(round(math.radians(herr)*1000))} '
                          f'{PIVOT_CRUISE} 9000')
                link.await_motion(timeout=25); time.sleep(0.5)
                continue
            leg = min(dist, HOP_MAX)
            print(f'     drive {leg:5.1f} cm', flush=True)
            link.seqd(f'MOVE_X {int(round(leg*10))} 0 {DRIVE_CRUISE} 12000')
            link.await_motion(timeout=25); time.sleep(0.5)

        # --- frame gate: forward must mean forward -------------------
        p = pose(cam)
        print('\ngate: MOVE_X +120 0 -- travel bearing vs heading',
              flush=True)
        link.seqd(f'MOVE_X 120 0 {DRIVE_CRUISE} 8000')
        link.await_motion(timeout=20); time.sleep(0.8)
        q = pose(cam)
        dx, dy = q[0]-p[0], q[1]-p[1]
        d = math.hypot(dx, dy)
        b = math.degrees(math.atan2(dy, dx))
        off = wrap(b - p[2])
        print(f'  nose {p[2]:+7.1f}  travelled {d:5.2f} cm at {b:+7.1f} '
              f'=> {off:+6.1f} off the nose', flush=True)
        print(f'  FRAME {"OK" if abs(off) < 12 else "WRONG -- STOP"}',
              flush=True)
        x, y, h = pose(cam)
        print(f'\nfinal ({x:6.1f},{y:6.1f}) heading {h:7.1f}', flush=True)
    finally:
        link.close(); cam.close()


main()
