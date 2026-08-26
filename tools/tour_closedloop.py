#!/usr/bin/env python3
"""Camera-in-the-loop tour: seed truth before every leg, then drive.

The firmware is frozen, so this composes a tour from commands the robot
already exposes -- seedxy / goto / fix. The point is where the camera
sits: instead of seeding once at the start and hoping, this seeds the
robot's world frame from the overhead camera BEFORE EVERY LEG, so each
goto is planned from measured truth rather than from accumulated
sensor drift. A leg that lands outside tolerance is simply re-seeded
and re-driven.

It also records what the robot BELIEVED on arrival against what the
camera saw, which is the direct measure of camera/OTOS agreement.

  python3 tools/tour_closedloop.py [--laps 1] [--tol 2.5] [--tries 3]
"""
import argparse
import csv
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robotlink import open_link
from camproc import Cam
from field import DOTS, ORDER as LAP

LIGHTS_ON = 'http://192.168.1.122/rpc/switch.set?id=0&on=true'


class Robot:
    def __init__(self, link, cam):
        self.link = link
        self.cam = cam

    def seed(self, pose):
        self.link.send(f'RUN:seedxy:{pose[0]:.1f}:{pose[1]:.1f}:{pose[2]:.1f}')
        for s in self.link.lines(6):
            if s.startswith('OCAL:seeded'):
                return True
        return False

    def goto(self, x, y, wait=50):
        """Drive to (x, y). Returns what the robot BELIEVED on arrival."""
        self.link.send(f'RUN:goto:{x:.1f}:{y:.1f}')
        believed = None
        for s in self.link.lines(wait):
            if s.startswith('OCAL:arrived'):
                p = s.split(':')
                try:
                    believed = (int(p[2]) / 100.0, int(p[3]) / 100.0,
                                int(p[4]) / 100.0)
                except (ValueError, IndexError):
                    pass
            elif s.startswith('GOTO:end'):
                return believed
        return believed

    def stop(self):
        for _ in range(3):
            self.link.send('ESTOP')
            time.sleep(0.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--laps', type=int, default=1)
    ap.add_argument('--tol', type=float, default=2.5)
    ap.add_argument('--tries', type=int, default=3)
    ap.add_argument('--out', default='.tmp/closedloop')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    cam = Cam()
    if cam.err or cam.latest is None:
        subprocess.run(['curl', '-s', '--max-time', '8', LIGHTS_ON],
                       capture_output=True)
        time.sleep(2)
        if cam.latest is None:
            raise SystemExit(f'camera unusable: {cam.err or "no tag"}')
    link = open_link(radio=True)
    bot = Robot(link, cam)

    t_start = time.time()
    rows = []
    print(f'{"leg":>6} {"try":>3} {"target":>14} {"camera arrived":>16} '
          f'{"err":>6} {"robot believed":>16} {"cam-otos":>9}')
    try:
        for lap in range(1, a.laps + 1):
            for tag in LAP:
                tx, ty = DOTS[tag]
                for attempt in range(1, a.tries + 1):
                    pose = cam.fix()
                    if pose is None:
                        print('  camera lost the robot -- stopping')
                        bot.stop()
                        raise SystemExit(1)
                    if math.hypot(pose[0] - tx, pose[1] - ty) <= a.tol:
                        break
                    bot.seed(pose)
                    believed = bot.goto(tx, ty)
                    time.sleep(0.8)
                    got = cam.fix()
                    if got is None:
                        print('  camera lost the robot -- stopping')
                        bot.stop()
                        raise SystemExit(1)
                    err = math.hypot(got[0] - tx, got[1] - ty)
                    dis = (math.hypot(believed[0] - got[0],
                                      believed[1] - got[1])
                           if believed else float('nan'))
                    print(f'{tag:>6} {attempt:>3} ({tx:6.1f},{ty:6.1f}) '
                          f'({got[0]:7.1f},{got[1]:7.1f}) {err:6.1f} '
                          + (f'({believed[0]:7.1f},{believed[1]:7.1f})'
                             if believed else ' ' * 17)
                          + f' {dis:9.1f}')
                    rows.append({'lap': lap, 'corner': tag, 'try': attempt,
                                 'tx': tx, 'ty': ty, 'cx': got[0],
                                 'cy': got[1], 'err': round(err, 2),
                                 'bx': believed[0] if believed else '',
                                 'by': believed[1] if believed else '',
                                 'cam_otos': round(dis, 2) if believed else ''})
                    if err <= a.tol:
                        break
    finally:
        link.close()
        with open(a.out + '/legs.csv', 'w') as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        with open(a.out + '/cam.csv', 'w') as f:
            w = csv.writer(f)
            w.writerow(['t', 'x_cm', 'y_cm', 'yaw_deg'])
            w.writerows([[round(s[0] - t_start, 3), round(s[1], 2),
                          round(s[2], 2), round(s[3], 2)]
                         for s in cam.samples])
        cam.close()

    if rows:
        finals = {}
        for r in rows:
            finals[(r['lap'], r['corner'])] = r['err']
        errs = list(finals.values())
        dis = [r['cam_otos'] for r in rows if r['cam_otos'] != '']
        print('\nfinal corner errors: '
              + '  '.join(f'{k[1]} {v:.1f}' for k, v in finals.items()))
        print(f'worst {max(errs):.1f} cm, mean {sum(errs)/len(errs):.1f} cm')
        if dis:
            print(f'camera vs OTOS on arrival: median '
                  f'{sorted(dis)[len(dis)//2]:.1f} cm, worst {max(dis):.1f} cm')


if __name__ == '__main__':
    main()
