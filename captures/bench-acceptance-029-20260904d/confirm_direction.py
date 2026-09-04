"""Direction confirmation on the motor-baked firmware (report S9.1).

1. kick; camera pose (residual 0: daemon heading = robot front = the
   tag's arrow); MOVE_X +50; pose. PASS iff the displacement bearing is
   within 20 deg of the daemon heading (it was 177 deg off before).
2. MOVE_X -50 back.
3. Move to the south corridor (y ~ -25, other robots north) facing +x,
   then run field_dance.py --tcp for the record.
Usage: confirm_direction.py host:port
"""
import sys, time, math, subprocess, re
sys.path.insert(0, 'tools')
from wire_acceptance import TcpLink
from camlink import Cam
cam = Cam()
def one():
    for t in cam.d.get_tags(cam.cam).tags:
        if t.tag.family.value == 'apriltag' and t.tag.number == 52 and t.world is not None:
            return t.world.x, t.world.y, math.degrees(t.yaw_rad)
def pose(n=5):
    xs = ys = sy = cy = 0.0; k = 0
    for _ in range(n):
        r = one()
        if r: xs += r[0]; ys += r[1]; sy += math.sin(math.radians(r[2])); cy += math.cos(math.radians(r[2])); k += 1
        time.sleep(0.1)
    return (xs/k, ys/k, math.degrees(math.atan2(sy, cy)))
L = TcpLink(sys.argv[1]); sid = 0
def ask(c, sec=1.0, seq=True):
    global sid
    if seq: sid += 1; c = f'{c} #{sid}'
    r = [l for l in L.ask(c, sec) if not l.startswith('DBG:')]
    print(c, '->', r[:2]); return r
def move(cmd, limit=10.0):
    global sid
    sid += 1; c = f'{cmd} #{sid}'; t0 = time.time(); L.s.sendall(c.encode() + b'\n')
    while time.time() - t0 < limit:
        for l in L.read(0.15):
            if l.startswith('status ') and int(re.search(r'done=(\d+)', l).group(1)) == sid:
                time.sleep(0.5); L.read(0.3); return
        L.s.sendall(b'STATUS\n')
def face(t):
    for _ in range(3):
        p = pose(); d = (t - p[2] + 180) % 360 - 180
        if abs(d) <= 2.5: return p
        move(f'MOVE_X 0 {int(round(math.radians(d)*1000))} 100 6000')
    return pose()
ask('HELLO', seq=False); ask('RUN:clearestop', seq=False); ask('VER', seq=False); ask('STATUS', seq=False)
ask('GET rotational_slip'); ask('GET lag'); ask('GET stop_distance')
move('MOVE_X 2 0 100 3000')
p0 = pose(); print('pose before', p0)
move('MOVE_X 50 0 100 5000')
p1 = pose(); print('pose after ', p1)
dx, dy = p1[0]-p0[0], p1[1]-p0[1]; b = math.degrees(math.atan2(dy, dx))
off = (b - p0[2] + 180) % 360 - 180
print(f'PROBE: moved {math.hypot(dx,dy):.2f} cm at bearing {b:.1f}; daemon heading {p0[2]:.1f}; bearing - heading = {off:+.1f} deg -> '
      f'{"FORWARD (PASS)" if abs(off) < 20 else "NOT FORWARD (FAIL)"}')
move('MOVE_X -50 0 100 5000'); p2 = pose(); print('back at', p2)
if abs(off) >= 20:
    L.close(); raise SystemExit('direction still wrong -- stopping')
# NORTH half only now (stakeholder 2026-09-04 12:50): stay in y in [8, 33]
p = pose()
if p[1] < 8:
    face(90.0); move(f'MOVE_X {int(round((25 - p[1]) * 10))} 0 150 10000')
p = pose(); print('corridor pose', p)
if not (8 <= p[1] <= 33): raise SystemExit('not in the north corridor -- not running the dance')
# the dance drives +20/-40/+20 cm along the current heading: project it
import math as _m
for d in (20, -20, 20):
    ex = p[0] + d * _m.cos(_m.radians(p[2])); ey = p[1] + d * _m.sin(_m.radians(p[2]))
    if abs(ex) > 55 or not (8 <= ey <= 33): raise SystemExit(f'dance leg would reach ({ex:.0f},{ey:.0f}) -- outside the north corridor')
L.close()
print('--- field_dance:')
subprocess.run([sys.executable, 'tools/field_dance.py', '--tcp', sys.argv[1]])
