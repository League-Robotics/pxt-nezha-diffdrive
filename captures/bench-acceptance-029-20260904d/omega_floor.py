"""omega_floor measurement (design S10.2): from rest, WHEELS_V +v -v 1500
sweeping v down from 70 mm/s per wheel; the lowest v with SUSTAINED
rotation over the whole 1.5 s is the floor. Camera heading sampled
continuously through each hold; "sustained" = the last third of the
hold still rotates at >= 50 % of the first third's rate. Pure rotation:
no path risk. Alternates sign so the heading nets to zero.
Usage: omega_floor.py host:port
"""
import sys, time, math, json, re
sys.path.insert(0, 'tools')
from wire_acceptance import TcpLink
from camlink import Cam
OUT = 'captures/bench-acceptance-029-20260904d/'
HALF_TRACK = 114.2 / 2 / 1.01   # [mm/rad] effective, slip 1.01 (this session)
cam = Cam()
def one():
    for t in cam.d.get_tags(cam.cam).tags:
        if t.tag.family.value == 'apriltag' and t.tag.number == 52 and t.world is not None:
            return math.degrees(t.yaw_rad)
    return None
L = TcpLink(sys.argv[1]); sid = 0
def ask(c, sec=0.8, seq=True):
    global sid
    if seq: sid += 1; c = f'{c} #{sid}'
    r = [l for l in L.ask(c, sec) if not l.startswith('DBG:') and not l.startswith('t ') and not l.startswith('thdr')]
    print(c, '->', r[:2]); return r
ask('HELLO', seq=False); ask('RUN:clearestop', seq=False); ask('STATUS', seq=False)
ask('SET twist_hold_gain 2'); ask('SET rotational_slip 1.01'); ask('GET omega_floor'); ask('GET v_floor')
ask('MOVE_X 2 0 100 3000', 1.5)   # kick after a reflash
rows = []; sign = 1
for v in (70, 60, 50, 40, 30, 25, 20, 15, 10):
    time.sleep(0.8)
    sid += 1; cmd = f'WHEELS_V {sign*v} {-sign*v} 1500 #{sid}'
    t0 = time.time(); L.s.sendall(cmd.encode() + b'\n')
    samples = []
    while time.time() - t0 < 2.2:
        h = one()
        if h is not None: samples.append((time.time() - t0, h))
        L.read(0.05)
    # unwrap
    un = []; prev = None; acc = 0.0
    for t, h in samples:
        if prev is not None:
            d = (h - prev + 180) % 360 - 180; acc += d
        un.append((t, acc)); prev = h
    def rate(a, b):
        seg = [(t, x) for t, x in un if a <= t <= b]
        return (seg[-1][1] - seg[0][1]) / (seg[-1][0] - seg[0][0]) if len(seg) > 1 and seg[-1][0] > seg[0][0] else 0.0
    r_first, r_last, r_all = rate(0.3, 0.7), rate(1.0, 1.45), rate(0.3, 1.45)
    total = un[-1][1] if un else 0.0
    cmd_rate = math.degrees(2 * v / (2 * HALF_TRACK))   # [deg/s] omega = 2v / track
    sustained = abs(r_last) >= 0.5 * abs(r_first) and abs(r_first) > 3
    rows.append({'v': v, 'sign': sign, 'cmd_rate_deg_s': cmd_rate, 'rate_first': r_first, 'rate_last': r_last, 'rate_mean': r_all,
                 'total_deg': total, 'sustained': sustained, 'samples': un})
    print(f'v={v:3d} mm/s (cmd {cmd_rate:5.1f} deg/s): rate first {r_first:+6.1f} last {r_last:+6.1f} mean {r_all:+6.1f} deg/s, total {total:+6.1f} deg, sustained={sustained}')
    sign = -sign
ask('STATUS', seq=False); L.close()
flo = [r['v'] for r in rows if r['sustained']]
print('omega_floor: lowest sustained v =', min(flo) if flo else None, 'mm/s per wheel ->',
      (math.degrees(2*min(flo)/(2*HALF_TRACK)) if flo else None), 'deg/s commanded')
json.dump(rows, open(OUT + 'omega-floor.json', 'w'), indent=1)
