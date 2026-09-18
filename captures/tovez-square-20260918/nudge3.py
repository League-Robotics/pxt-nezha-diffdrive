#!/usr/bin/env python3
"""Nudge the square's start dot south so all four corners clear the
12 cm margin. Registered pose frame, yaw used unchanged (see stage3.py)."""
import math, os, sys, time
sys.path.insert(0, 'tools'); sys.path.insert(0, 'tests/system')
from camlink import Cam
from field import wrap
from run_tour import Link

MOUNT_X_CM = -4.1
PIVOT_CRUISE, DRIVE_CRUISE = 188, 180
TARGET = (-30.0, -31.5)


def pose(cam):
    f = cam.fix(n=8)
    if f is None:
        raise SystemExit('camera lost the robot')
    x, y, h = f[0], f[1], wrap(f[2])
    r = math.radians(h)
    return (x - MOUNT_X_CM*math.cos(r), y - MOUNT_X_CM*math.sin(r), h)


def face(link, cam, want, tol=1.5):
    for _ in range(5):
        x, y, h = pose(cam)
        err = wrap(want - h)
        print(f'    face {want:+6.1f}: at {h:7.1f} ({err:+5.1f})', flush=True)
        if abs(err) <= tol:
            return
        link.seqd(f'MOVE_X 0 {int(round(math.radians(err)*1000))} '
                  f'{PIVOT_CRUISE} 9000')
        link.await_motion(timeout=25); time.sleep(0.5)


def main():
    Cam.register('tovez')
    cam = Cam(tag=52, cam='arducam-ov9782-usb-camera')
    link = Link(os.environ.get('TOVEZ_HOST', '192.168.4.50'),
                int(os.environ.get('TOVEZ_PORT', '41069')))
    print(link.unseq('HELLO', r'^device '), flush=True)
    link._seq = 0
    link.seqd('TLM FULL')
    try:
        x, y, h = pose(cam)
        print(f'start ({x:6.1f},{y:6.1f}) {h:7.1f}', flush=True)
        face(link, cam, -90.0)
        x, y, h = pose(cam)
        leg = y - TARGET[1]
        if leg > 1.0:
            print(f'  south {leg:.1f} cm', flush=True)
            link.seqd(f'MOVE_X {int(round(leg*10))} 0 {DRIVE_CRUISE} 10000')
            link.await_motion(timeout=25); time.sleep(0.5)
        face(link, cam, 0.0)
        x, y, h = pose(cam)
        leg = TARGET[0] - x
        if abs(leg) > 1.5:
            print(f'  trim {leg:+.1f} cm', flush=True)
            link.seqd(f'MOVE_X {int(round(leg*10))} 0 {DRIVE_CRUISE} 10000')
            link.await_motion(timeout=25); time.sleep(0.5)
        x, y, h = pose(cam)
        print(f'\nSTART POSE ({x:6.1f},{y:6.1f}) heading {h:7.1f}', flush=True)
        c = [(x, y), (x+60, y), (x+60, y+60), (x, y+60)]
        print('  corners: ' + ', '.join(f'({a:.0f},{b:.0f})' for a, b in c),
              flush=True)
        print('  inside the 12 cm margin: '
              f'{all(abs(a)<=55.15 and abs(b)<=32.65 for a,b in c)}',
              flush=True)
    finally:
        link.close(); cam.close()


main()
