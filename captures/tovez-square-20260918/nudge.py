#!/usr/bin/env python3
"""Final staging nudge: put the square's start dot far enough south and
west that all four corners clear the 12 cm margin.

Same measured heading convention as stage2.py (residual -90, see that
file's docstring and captures/tovez-square-20260918/unrail.log).
"""
import math, sys, time
sys.path.insert(0, 'tools'); sys.path.insert(0, 'tests/system')
from camlink import Cam
from field import wrap
from run_tour import Link

MOUNT_X_CM, RESIDUAL = -4.1, -90.0
PIVOT_CRUISE, DRIVE_CRUISE = 188, 180
TARGET = (-30.0, -31.0)


def pose(cam):
    f = cam.fix(n=8)
    if f is None:
        raise SystemExit('camera lost the robot')
    x, y, tag_yaw = f
    h = wrap(tag_yaw + 90.0 + RESIDUAL)
    r = math.radians(h)
    return (x - MOUNT_X_CM * math.cos(r), y - MOUNT_X_CM * math.sin(r), h)


def face(link, cam, want, tol=2.5):
    for _ in range(5):
        x, y, h = pose(cam)
        err = wrap(want - h)
        print(f'    face {want:+6.1f}: at {h:7.1f} ({err:+5.1f} off)',
              flush=True)
        if abs(err) <= tol:
            return pose(cam)
        link.seqd(f'MOVE_X 0 {int(round(math.radians(err)*1000))} '
                  f'{PIVOT_CRUISE} 9000')
        link.await_motion(timeout=25); time.sleep(0.5)
    return pose(cam)


def main():
    cam = Cam(tag=52, cam='arducam-ov9782-usb-camera')
    link = Link('192.168.4.53', 37481)
    print(link.unseq('HELLO', r'^device '), flush=True)
    link._seq = 0
    link.seqd('TLM FULL')
    try:
        x, y, h = pose(cam)
        print(f'start ({x:6.1f},{y:6.1f}) {h:7.1f}', flush=True)

        # south first
        if abs(y - TARGET[1]) > 2.5:
            face(link, cam, -90.0)
            x, y, h = pose(cam)
            leg = y - TARGET[1]
            if leg > 0:
                print(f'  drive south {leg:.1f} cm', flush=True)
                link.seqd(f'MOVE_X {int(round(leg*10))} 0 '
                          f'{DRIVE_CRUISE} 10000')
                link.await_motion(timeout=25); time.sleep(0.5)

        # then east, and close x with a reverse leg (no pivot after it)
        face(link, cam, 0.0)
        x, y, h = pose(cam)
        leg = TARGET[0] - x
        if abs(leg) > 2.0:
            print(f'  drive {leg:+.1f} cm along the nose', flush=True)
            link.seqd(f'MOVE_X {int(round(leg*10))} 0 {DRIVE_CRUISE} 10000')
            link.await_motion(timeout=25); time.sleep(0.5)

        x, y, h = pose(cam)
        print(f'\nSTART POSE ({x:6.1f},{y:6.1f}) heading {h:7.1f}',
              flush=True)
        c = [(x, y), (x+60, y), (x+60, y+60), (x, y+60)]
        print('  square corners: ' + ', '.join(f'({a:.0f},{b:.0f})'
                                               for a, b in c), flush=True)
        ok = all(abs(a) <= 55.15 and abs(b) <= 32.65 for a, b in c)
        print(f'  all corners inside the 12 cm margin: {ok}', flush=True)
    finally:
        link.close(); cam.close()


main()
