import sys, time, math, re
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
def raw(c, sec=1.0, seq=True):
    global sid
    if seq: sid += 1; c = f'{c} #{sid}'
    r = [l for l in L.ask(c, sec) if not l.startswith('DBG:')]
    print(c, '->', r); return r
raw('HELLO', seq=False); raw('RUN:clearestop', seq=False)
def face(t):
    for _ in range(3):
        p = pose(); d = (t - p[2] + 180) % 360 - 180
        if abs(d) <= 2.5: return p
        raw(f'MOVE_X 0 {int(round(math.radians(d)*1000))} 100 6000', 2.5); time.sleep(0.5)
    return pose()
p = pose(); print('pose', p)
if p[1] > -24:
    face(-90.0); raw(f'MOVE_X {int(round((p[1]+27)*10))} 0 120 6000', 3.0); time.sleep(0.5)
p = face(0.0); print('facing east at', p)
raw('STATUS', seq=False)
for cmd in ('MOVE_X 300 785 100 8000', 'MOVE_X 300 -785 100 8000', 'MOVE_X 300 400 100 8000'):
    p0 = pose()
    print('--- sending', cmd)
    r = raw(cmd, 3.5)
    raw('STATUS', seq=False); raw('DIAG', seq=False)
    p1 = pose(); print(f'  moved {math.hypot(p1[0]-p0[0], p1[1]-p0[1]):.1f} cm, dh {(p1[2]-p0[2]+180)%360-180:+.1f}')
    # come back along the same arc if it moved
    if math.hypot(p1[0]-p0[0], p1[1]-p0[1]) > 3:
        parts = cmd.split(); back = f'MOVE_X {-int(parts[1])} {-int(parts[2])} 100 8000'
        raw(back, 4.0); time.sleep(0.5); print('  back at', pose())
L.close()
