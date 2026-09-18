#!/usr/bin/env python3
"""Stage tovez on the square tour's start dot, post-reflash.

Pose frame: the tag is REGISTERED with the daemon, so `Cam.fix()`'s yaw
IS the robot's heading and is used unchanged -- never through
robot_heading_from_tag_yaw(), which is for a raw reading and would add
the +90 convention twice (the bug that put this robot in a rail earlier
today). Gate re-verified this session at 0.1 deg off the nose,
captures/tovez-turns-20260918/center2.log.
"""
import math, os, sys, time
sys.path.insert(0, 'tools'); sys.path.insert(0, 'tests/system')
from camlink import Cam
from field import wrap
from run_tour import Link

TARGET = (-30.0, -30.0, 0.0)
MOUNT_X_CM = -4.1
PIVOT_CRUISE, DRIVE_CRUISE = 188, 180
HOP_MAX = 25.0
LIM_X, LIM_Y = 67.15, 44.65


def pose(cam):
    f = cam.fix(n=8)
    if f is None:
        raise SystemExit('camera lost the robot')
    x, y, h = f[0], f[1], wrap(f[2])
    r = math.radians(h)
    return (x - MOUNT_X_CM * math.cos(r), y - MOUNT_X_CM * math.sin(r), h)


def main():
    Cam.register('tovez')
    cam = Cam(tag=52, cam='arducam-ov9782-usb-camera')
    link = Link(os.environ.get('TOVEZ_HOST', '192.168.4.50'),
                int(os.environ.get('TOVEZ_PORT', '41069')))
    print(link.unseq('HELLO', r'^device '), flush=True)
    link._seq = 0
    link.seqd('TLM FULL')
    try:
        for hop in range(1, 14):
            x, y, h = pose(cam)
            d = math.hypot(TARGET[0]-x, TARGET[1]-y)
            print(f'[{hop:2d}] ({x:6.1f},{y:6.1f}) {h:7.1f} -> {d:5.1f} cm',
                  flush=True)
            if d <= 2.5:
                break
            bearing = math.degrees(math.atan2(TARGET[1]-y, TARGET[0]-x))
            herr = wrap(bearing - h)
            if abs(herr) > 6:
                link.seqd(f'MOVE_X 0 {int(round(math.radians(herr)*1000))} '
                          f'{PIVOT_CRUISE} 9000')
                link.await_motion(timeout=25); time.sleep(0.5)
                continue
            leg = min(d, HOP_MAX)
            ex = x + leg*math.cos(math.radians(h))
            ey = y + leg*math.sin(math.radians(h))
            if abs(ex) > LIM_X-8 or abs(ey) > LIM_Y-8:
                raise SystemExit(f'REFUSING hop to ({ex:.1f},{ey:.1f})')
            link.seqd(f'MOVE_X {int(round(leg*10))} 0 {DRIVE_CRUISE} 12000')
            link.await_motion(timeout=25); time.sleep(0.5)

        for _ in range(5):
            x, y, h = pose(cam)
            herr = wrap(TARGET[2]-h)
            print(f'  face east: {h:7.1f} ({herr:+5.1f} off)', flush=True)
            if abs(herr) <= 1.5:
                break
            link.seqd(f'MOVE_X 0 {int(round(math.radians(herr)*1000))} '
                      f'{PIVOT_CRUISE} 9000')
            link.await_motion(timeout=25); time.sleep(0.5)

        x, y, h = pose(cam)
        # close x with a pure translation -- no pivot after it
        leg = TARGET[0] - x
        if abs(leg) > 2.0 and abs(h) < 6:
            print(f'  trim {leg:+.1f} cm along the nose', flush=True)
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
