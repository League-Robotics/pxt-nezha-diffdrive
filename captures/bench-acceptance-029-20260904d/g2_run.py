"""G2 arc endpoint gate (design S10.1) on tovez over zilch, south corridor.

3x [MOVE_X 300 785 100 8000 (45 deg left arc, R = 382 mm) ; MOVE_X -300
-785 100 8000 (the same arc driven back)] = 6 arcs. For each arc the
camera pose at rest before/after gives the endpoint in the START pose's
body frame; expected (R sin th, R (1 - cos th)) = (+-270, 112) mm and a
heading change of +-45 deg. Bar: endpoint within 5 mm.
Usage: g2_run.py host:port lag stop_distance rotational_slip
"""
import sys, time, math, json, statistics, re
sys.path.insert(0, 'tools')
from wire_acceptance import TcpLink
from camlink import Cam

OUT = 'captures/bench-acceptance-029-20260904d/'
LIMX = 55.0; YMIN, YMAX = -33.0, -8.0
HARDX, HARDYN, HARDYS = 61.0, -3.0, -40.0
cam = Cam()
def one():
    for t in cam.d.get_tags(cam.cam).tags:
        if t.tag.family.value == 'apriltag' and t.tag.number == 52 and t.world is not None:
            return t.world.x, t.world.y, math.degrees(t.yaw_rad)
    return None
def pose(n=5):
    xs = ys = sy = cy = 0.0; k = 0; end = time.time() + 3
    while k < n and time.time() < end:
        r = one()
        if r:
            xs += r[0]; ys += r[1]; sy += math.sin(math.radians(r[2])); cy += math.cos(math.radians(r[2])); k += 1
        time.sleep(0.1)
    return (xs/k, ys/k, math.degrees(math.atan2(sy, cy))) if k else None
def frames_from(lines):
    out = []
    for l in lines:
        p = l.split()
        if p and p[0] == 't' and len(p) >= 18:
            out.append({'now': int(p[2]), 'x': int(p[4]), 'y': int(p[5]), 'h': int(p[6]),
                        'vl': int(p[10]), 'vr': int(p[11]), 'dutl': int(p[16]), 'dutr': int(p[17])})
    return out
L = TcpLink(sys.argv[1]); sid = 0; LOG = []
def ask(c, sec=0.8, seq=True):
    global sid
    if seq: sid += 1; c = f'{c} #{sid}'
    r = [l for l in L.ask(c, sec) if not l.startswith('DBG:') and not l.startswith('t ') and not l.startswith('thdr')]
    LOG.append((c, r)); print(c, '->', r[:2]); return r
def run_move(cmd, limit=10.0):
    global sid
    sid += 1; cmd = f'{cmd} #{sid}'
    t0 = time.time(); L.s.sendall(cmd.encode() + b'\n')
    lines = []; seen1 = False; tdone = None; reason = None; estop = False
    while time.time() - t0 < limit:
        got = L.read(0.12); lines += got
        for l in got:
            if l.startswith('status '):
                a = re.search(r'active=(\d)', l).group(1); rs = re.search(r'reason=(\w+)', l).group(1)
                dn = int(re.search(r'done=(\d+)', l).group(1))
                if a == '1': seen1 = True
                if dn == sid and tdone is None: tdone = round(time.time() - t0, 2); reason = rs; seen1 = True
        if tdone is not None and time.time() - t0 > tdone + 0.6: break
        r = one()
        if r and (abs(r[0]) > HARDX or r[1] > HARDYN or r[1] < HARDYS):
            L.s.sendall(b'ESTOP\n'); estop = True; print(f'!!! GEOFENCE ESTOP at ({r[0]:.1f},{r[1]:.1f})'); break
        L.s.sendall(b'STATUS\n')
    LOG.append((cmd, {'done_s': tdone, 'reason': reason, 'estop': estop}))
    return {'cmd': cmd, 'done_s': tdone, 'reason': reason, 'estop': estop, 'frames': frames_from(lines)}
def face(target_deg):
    for attempt in range(3):
        p = pose(); d = (target_deg - p[2] + 180) % 360 - 180
        print(f'face {target_deg}: at {p[2]:.1f}, delta {d:+.1f}')
        if abs(d) <= 2.5: return p
        run_move(f'MOVE_X 0 {int(round(math.radians(d)*1000))} 100 6000'); time.sleep(0.6)
    return pose()

def expected(d_mm, th_rad):
    R = d_mm / th_rad
    return R*math.sin(th_rad), R*(1 - math.cos(th_rad))

def projected_ok(p, d_mm, th_rad):
    ex, ey = expected(d_mm, th_rad); h = math.radians(p[2])
    wx = p[0] + (ex*math.cos(h) - ey*math.sin(h))/10; wy = p[1] + (ex*math.sin(h) + ey*math.cos(h))/10
    return abs(wx) <= LIMX and YMIN <= wy <= YMAX, (wx, wy)

ask('HELLO', seq=False); ask('RUN:clearestop', seq=False); ask('STATUS', seq=False)
for c in ('SET accel 400', 'SET decel 400', 'SET twist_hold_gain 2', f'SET lag {sys.argv[2]}',
          f'SET stop_distance {sys.argv[3]}', f'SET rotational_slip {sys.argv[4]}', 'GET lag', 'GET rotational_slip'):
    ask(c)
p = pose(); print('start pose', p)
if not (YMIN <= p[1] <= YMAX): raise SystemExit('not in the south corridor')
if p[1] > -22:  # need ~11 cm of northward room for the left arc
    face(-90.0); run_move(f'MOVE_X {int(round((p[1]+26)*10))} 0 120 6000'); time.sleep(0.6)
p = face(0.0); print('arcs start pose', p)
ask('TLM FULL', 0.4)
arcs = []
for k in range(3):
    for (d, th) in ((300, 0.785), (-300, -0.785)):
        p0 = pose(); ok, e = projected_ok(p0, d, th)
        print(f'arc {len(arcs)} d={d} th={th} from ({p0[0]:.1f},{p0[1]:.1f},{p0[2]:.1f}) -> projected ({e[0]:.1f},{e[1]:.1f}) ok={ok}')
        if not ok: print('would leave the corridor -- stopping'); break
        mv = run_move(f'MOVE_X {d} {int(th*1000)} 100 8000'); time.sleep(0.6); post = frames_from(L.read(0.3))
        p1 = pose()
        h = math.radians(p0[2]); dx, dy = (p1[0]-p0[0])*10, (p1[1]-p0[1])*10
        bx = dx*math.cos(h) + dy*math.sin(h); by = -dx*math.sin(h) + dy*math.cos(h)
        ex, ey = expected(d, th); err = math.hypot(bx-ex, by-ey)
        dh = (p1[2]-p0[2]+180) % 360 - 180
        fr = mv['frames'] + post; peak = max((max(abs(f['vl']), abs(f['vr'])) for f in fr), default=None)
        row = {'i': len(arcs), 'd': d, 'th': th, 'p0': p0, 'p1': p1, 'body_end_mm': (bx, by), 'expected_mm': (ex, ey),
               'endpoint_err_mm': err, 'dheading_deg': dh, 'dheading_err_deg': dh - math.degrees(th), 'done_s': mv['done_s'],
               'reason': mv['reason'], 'estop': mv['estop'], 'peak_v': peak, 'frames': fr}
        arcs.append(row)
        print(f'  end body ({bx:+.0f},{by:+.0f}) expected ({ex:+.0f},{ey:+.0f}) err {err:.0f} mm; dh {dh:+.1f} (err {dh-math.degrees(th):+.1f}); done {mv["done_s"]}s {mv["reason"]} peak {peak}')
        if mv['estop']: break
    else:
        continue
    break
ask('TLM OFF', 0.4); L.read(0.4); ask('STATUS', seq=False); L.close()
if arcs:
    e = [a['endpoint_err_mm'] for a in arcs]; he = [a['dheading_err_deg'] for a in arcs]
    print(f'G2: endpoint err mean {statistics.mean(e):.1f} mm max {max(e):.1f} mm ({sum(1 for x in e if x <= 5)}/{len(e)} within 5 mm); '
          f'heading err mean {statistics.mean(he):+.2f} sd {statistics.pstdev(he):.2f} deg')
json.dump({'args': sys.argv[1:], 'arcs': arcs, 'log': LOG}, open(OUT + 'g2-run.json', 'w'), indent=1)
