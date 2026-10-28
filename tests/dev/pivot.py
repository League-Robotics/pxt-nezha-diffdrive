"""One camera-scored pivot: asked vs encoders vs camera."""
import argparse
import math
import sys
import time

from devlink import Cam, open_serial, settled as _settled, wrap

ap = argparse.ArgumentParser()
ap.add_argument('deg', type=float, nargs='?')
ap.add_argument('--cruise', type=int, default=150)
ap.add_argument('--set', action='append', default=[])
ap.add_argument('--robot', default='vevov')
a = ap.parse_args()

cam = Cam(tag=53).start()


def settled():
    return _settled(cam, 25)


hdr = None
frame = {}


def pump(link, secs):
    global hdr
    for s in link.lines(secs):
        p = s.split()
        if p and p[0] == 'thdr':
            hdr = p[1:]
        elif p and p[0] == 't' and hdr and len(p) - 1 == len(hdr):
            frame.update(zip(hdr, [float(v) if v.lstrip('-').isdigit() else 0.0 for v in p[1:]]))


def unwrap_to(got, want):
    while got - want > 180:
        got -= 360
    while got - want < -180:
        got += 360
    return got


p0 = settled()
print(f'pose ({p0[0]:.1f},{p0[1]:.1f}) hdg {p0[2]:.2f}')
if a.deg is None:
    sys.exit()

link = open_serial(a.robot)
for kv in a.set:
    link.send('SET ' + kv.replace('=', ' '))
    print('  ', [x for x in link.lines(1.0) if not x.startswith('DBG')])
link.send('TLM POSE')
pump(link, 1.5)
h0 = frame.get('h')
link.send(f'MOVE_X 0 {int(round(math.radians(a.deg) * 1000))} {a.cruise} 15000')
t0 = time.time()
while time.time() - t0 < 15:
    pump(link, 0.3)
    if time.time() - t0 > 1.0 and abs(frame.get('vl', 1)) < 1 and abs(frame.get('vr', 1)) < 1:
        break
t_move = time.time() - t0
p1 = settled()
pump(link, 0.8)
h1 = frame.get('h')
link.send('TLM OFF')
cam_got = unwrap_to(wrap(p1[2] - p0[2]), a.deg)
odo = unwrap_to(wrap((h1 - h0) / 100.0), a.deg) if h0 is not None and h1 is not None else float('nan')
print(f'asked {a.deg:+.1f} | encoders {odo:+.2f} | camera {cam_got:+.2f} (err {cam_got - a.deg:+.2f}, {100 * cam_got / a.deg:.1f}%) '
      f'| drift {math.hypot(p1[0] - p0[0], p1[1] - p0[1]):.2f} cm | wheels stopped {t_move:.1f}s | i2cf {frame.get("i2cf")}')
link.close()
cam.close()
