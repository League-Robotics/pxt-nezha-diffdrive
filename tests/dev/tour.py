"""Open-loop rectangle tour, camera-scored per leg and per lap."""
import argparse
import json
import math
import sys

from devlink import Cam, movex, open_serial, settled, wrap

ap = argparse.ArgumentParser()
ap.add_argument('--long', type=float, default=100.0)
ap.add_argument('--short', type=float, default=44.0)
ap.add_argument('--laps', type=int, default=1)
ap.add_argument('--legs', default=None)
ap.add_argument('--turns', default=None)
ap.add_argument('--drive', type=int, default=100)
ap.add_argument('--turn', type=int, default=60)
ap.add_argument('--set', action='append', default=[])
ap.add_argument('--robot', default='vevov')
ap.add_argument('--log', default=None)
a = ap.parse_args()

XLIM, YLIM = 56.0, 32.0
cam = Cam(tag=53).start()
link = open_serial(a.robot)
for kv in a.set:
    link.send('SET ' + kv.replace('=', ' '))
    list(link.lines(0.8))


rows = []
start = settled(cam)
nominal = start[2]
print(f'start ({start[0]:.1f},{start[1]:.1f}) hdg {start[2]:.2f}')
p = start
for lap in range(a.laps):
    legs = [float(v) for v in a.legs.split(',')] if a.legs else [a.long, a.short, a.long, a.short]
    turns = [float(v) for v in a.turns.split(',')] if a.turns else [90.0] * len(legs)
    for i, side in enumerate(legs):
        herr = wrap(p[2] - nominal)
        if abs(herr) > 8.0:
            sys.exit(f'ABORT: heading {herr:+.1f} deg off nominal before leg {i + 1}')
        ex = p[0] + side * math.cos(math.radians(p[2]))
        ey = p[1] + side * math.sin(math.radians(p[2]))
        if abs(ex) > XLIM or abs(ey) > YLIM:
            sys.exit(f'ABORT: leg {i + 1} would end at ({ex:.1f},{ey:.1f}), too close to the boards')
        q = movex(link, cam, side * 10, 0, a.drive)
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if d < 0.7 * side:
            sys.exit(f'ABORT: leg {i + 1} moved {d:.1f} of {side:.0f} cm (stuck?)')
        r = movex(link, cam, 0, turns[i], a.turn)
        t = wrap(r[2] - q[2])
        print(f'lap {lap + 1} leg {i + 1}: drive {side:.0f} -> {d:.1f} cm, heading drift {wrap(q[2] - p[2]):+.2f}; turn {turns[i]:+.0f} -> {t:+.2f}')
        rows.append(dict(lap=lap + 1, leg=i + 1, side=side, drove=d, drift=wrap(q[2] - p[2]), turn=t, end=r))
        p = r
        nominal = wrap(nominal + turns[i])
    close = math.hypot(p[0] - start[0], p[1] - start[1])
    hclose = wrap(p[2] - start[2])
    print(f'LAP {lap + 1} CLOSURE {close:.1f} cm (dx {p[0] - start[0]:+.1f}, dy {p[1] - start[1]:+.1f}), heading {hclose:+.2f} deg')
if a.log:
    json.dump(dict(start=start, rows=rows, args=vars(a)), open(a.log, 'w'), indent=1)
link.close()
cam.close()
