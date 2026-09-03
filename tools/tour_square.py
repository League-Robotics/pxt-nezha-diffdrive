#!/usr/bin/env python3
"""Drive the square with the firmware as it currently stands.

The on-robot goToWorld commits to an arc of 2*bearing, so a leg that
starts badly off-bearing drives a half-circle. blocks/world.ts's own
turnFirstDeg already pivots first beyond a 12 deg bearing error, but
this tool still points at the target FIRST using the robot's own
on-device face loop, so goto always starts nearly on-bearing and its
arc stays gentle regardless.

Camera discipline is kept: seed once at the start, score at the end,
NEVER during. The per-leg pose used for aiming comes from RUN:fix --
that is the robot's own OTOS, not the overhead camera.

  python3 tools/tour_square.py [--laps 1]
"""
import argparse, csv, math, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robotlink import open_link
from camproc import Cam
from field import DOTS, ORDER, score_corners, path_deviation

# The camera subprocess can DIE mid-run (daemon hiccup, and its stream
# exits on a CamDown). Silence then reads as "the robot stopped
# moving", and a score computed over the surviving samples is fiction
# -- measured as phantom 53 and 69 cm corner errors when the robot had
# actually arrived. So: respawn=True below, and cam.deaths records WHEN
# it was blind so the score can be flagged untrustworthy.


def robot_pose(link):
    """The ROBOT's own belief (OTOS). Not the camera."""
    link.send('RUN:fix')
    for s in link.lines(8):
        if s.startswith('OCAL:now'):
            p = s.split(':')
            try:
                return int(p[2]) / 100.0, int(p[3]) / 100.0, int(p[4]) / 100.0
            except (ValueError, IndexError):
                return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wifi', metavar='NAME|IP', default=None,
        help="drive the robot over its WiFi TCP server instead of the "
             "radio relay (the default carrier since 2026-09-02)")
    ap.add_argument('--laps', type=int, default=1)
    ap.add_argument('--out', default='.tmp/square')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    cam = Cam(respawn=True)
    if cam.latest is None:
        raise SystemExit('camera cannot see the robot')
    link = open_link(radio=not a.wifi, wifi=a.wifi)

    # --- camera use 1 of 2: seed once ---
    p = cam.fix(n=10)
    link.send(f'RUN:seedxy:{p[0]:.1f}:{p[1]:.1f}:{p[2]:.1f}')
    for s in link.lines(6):
        if s.startswith('OCAL:seeded'):
            break
    print(f'seeded ({p[0]:.1f}, {p[1]:.1f}) {p[2]:.1f} deg')
    t0 = time.time()

    # One pose query per leg. Asking twice in a row would be suppressed
    # by the firmware's 3 s RUN-dedupe (identical text), which silently
    # returns nothing -- so the pose read AFTER a leg is reused as the
    # pose BEFORE the next one.
    rp = robot_pose(link)
    for _lap in range(a.laps):
        for tag in ORDER:
            tx, ty = DOTS[tag]
            if rp is None:
                print('  no pose from the robot'); break
            # Splitting long legs was tried and made things worse
            # (SE 10.7 -> 24.0 cm); one hop per corner.
            hops = [(tx, ty)]
            for hx, hy in hops:
                if rp is None:
                    break
                brg = math.degrees(math.atan2(hy - rp[1], hx - rp[0]))
                link.send(f'RUN:face:{brg:.1f}')
                for s in link.lines(30):
                    if s.startswith('FACE:end'):
                        break
                link.send(f'RUN:goto:{hx:.1f}:{hy:.1f}')
                for s in link.lines(60):
                    if s.startswith('GOTO:end'):
                        break
                rp = robot_pose(link)
            print(f'  {tag}: {len(hops)} hop(s), robot now '
                  + (f'({rp[0]:6.1f},{rp[1]:6.1f})' if rp else '   ?'))

    # --- camera use 2 of 2: score ---
    rows = cam.since(t0)
    link.close()
    deaths = [d for d in cam.deaths if d >= t0]
    if deaths:
        print(f'\n  WARNING: the camera process died {len(deaths)} time(s) '
              f'mid-run and was respawned. Corner scores that depend on '
              f'those windows are NOT trustworthy.')
    span = rows[-1][0] - t0 if rows else 0
    moving = tot = 0
    for x, y in zip(rows, rows[1:]):
        dt = y[0] - x[0]
        if not (0.02 < dt < 0.5):
            continue
        v = math.hypot(y[1] - x[1], y[2] - x[2]) / dt
        if v > 200:
            continue
        tot += 1
        if v > 3:
            moving += 1
    corner = score_corners(rows)
    devs = path_deviation(rows)
    print(f'\n{span:.0f}s, moving {100*moving/tot if tot else 0:.0f}%')
    print('corners: ' + '  '.join(
        (f'{t} {corner[t]:.1f}cm' if corner[t] is not None
         else f'{t} unobserved') for t in ORDER))
    print(f'path deviation: median {devs[len(devs)//2]:.1f} cm, '
          f'90th {devs[int(len(devs)*0.9)]:.1f}, max {devs[-1]:.1f}')
    with open(a.out + '/cam.csv', 'w') as f:
        w = csv.writer(f); w.writerow(['t','x_cm','y_cm','yaw_deg'])
        w.writerows([[round(r[0]-t0,3),round(r[1],2),round(r[2],2),
                      round(r[3],2)] for r in rows])
    cam.close()


if __name__ == '__main__':
    main()
