"""Put the robot on each orange dot, camera-corrected.

The camera's registered pose is already the centre of rotation (the tag
mount is part of the registration; tag_dance.py checks it), so that pose
is what goes on the dot. Each leg is driven open loop (pivot + straight),
then up to --tries camera fixes pull it onto the dot. The robot ends each dot facing
the next leg, which keeps its body inboard of the dot.
"""
import argparse
import json
import math
import sys

from devlink import DOTS, Cam, movex, open_serial, settled, wrap

XLIM, YLIM = 56.0, 34.0
ROUTE = [('SW', 0.0), ('SE', 90.0), ('NE', 180.0), ('NW', 270.0)]


def check(x, y):
    if abs(x) > XLIM or abs(y) > YLIM:
        sys.exit(f'ABORT: ({x:.1f},{y:.1f}) is outside the safe box')


class Placer:
    def __init__(self, link, cam, drive=100, turn=60):
        self.link, self.cam, self.drive, self.turn = link, cam, drive, turn

    def face(self, p, h):
        err = wrap(h - p[2])
        if abs(err) < 1.0:
            return p
        q = movex(self.link, self.cam, 0, err, self.turn)
        got = wrap(q[2] - p[2])
        if abs(err) > 5 and abs(got) < 0.3 * abs(err):
            sys.exit(f'ABORT: pivot {err:+.1f} produced {got:+.1f}')
        return q

    def go(self, p, c, final):
        d = math.hypot(c[0] - p[0], c[1] - p[1])
        if d < 0.3:
            return p
        brg = math.degrees(math.atan2(c[1] - p[1], c[0] - p[0]))
        if abs(wrap(brg - final)) > 90:
            brg = wrap(brg + 180)
        if abs(wrap(brg - p[2])) > 2.0 or d > 5:
            p = self.face(p, brg)
        h = math.radians(p[2])
        along = (c[0] - p[0]) * math.cos(h) + (c[1] - p[1]) * math.sin(h)
        check(p[0] + along * math.cos(h), p[1] + along * math.sin(h))
        q = movex(self.link, self.cam, along * 10, 0, self.drive)
        moved = math.hypot(q[0] - p[0], q[1] - p[1])
        if abs(along) > 5 and moved < 0.6 * abs(along):
            sys.exit(f'ABORT: asked {along:.1f} cm, moved {moved:.1f} (stuck?)')
        return q

    def park(self, p, c, fh, tol=1.0, tries=3):
        """Centre of rotation onto `c`, facing `fh`."""
        check(*c)
        for _ in range(tries + 1):
            p = self.face(self.go(p, c, fh), fh)
            if math.hypot(p[0] - c[0], p[1] - c[1]) <= tol:
                break
        return p

    def place(self, p, name, fh, tol=0.7, tries=4):
        """Returns (pose, first-arrival tag error, fixes used, final tag error)."""
        dot = DOTS[name]
        c = dot
        check(*c)
        p = self.face(self.go(p, c, fh), fh)
        t = p
        first = math.hypot(t[0] - dot[0], t[1] - dot[1])
        fixes = 0
        while math.hypot(t[0] - dot[0], t[1] - dot[1]) > tol and fixes < tries:
            p = self.face(self.go(p, c, fh), fh)
            t = p
            fixes += 1
        return p, first, fixes, math.hypot(t[0] - dot[0], t[1] - dot[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--robot', default='vevov')
    ap.add_argument('--tag', type=int, default=53)
    ap.add_argument('--laps', type=int, default=1)
    ap.add_argument('--tol', type=float, default=0.7)
    ap.add_argument('--tries', type=int, default=4)
    ap.add_argument('--log', default=None)
    a = ap.parse_args()

    cam = Cam(tag=a.tag).start()
    link = open_serial(a.robot)
    pl = Placer(link, cam)
    rows = []
    p = settled(cam)
    print(f'start ({p[0]:.1f},{p[1]:.1f}) hdg {p[2]:.1f}')
    for lap in range(a.laps):
        for name, fh in ROUTE:
            p, first, fixes, err = pl.place(p, name, fh, a.tol, a.tries)
            t = p
            print(f'lap {lap + 1} {name}: first arrival tag off {first:.1f} cm; after {fixes} fixes '
                  f'tag ({t[0]:.1f},{t[1]:.1f}) off {err:.2f} cm, hdg {p[2]:.1f} want {fh:.0f}')
            rows.append(dict(lap=lap + 1, dot=name, first=first, fixes=fixes, err=err, tag=t, pose=p))
    if a.log:
        json.dump(rows, open(a.log, 'w'), indent=1)
    link.close()
    cam.close()


if __name__ == '__main__':
    main()
