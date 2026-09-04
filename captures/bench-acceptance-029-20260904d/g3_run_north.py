"""G3/G4 straight-leg gates (design S10.1) on tovez over zilch.

Repositions to the west end of the long axis facing +x, then drives 6
alternating MOVE_X +-600 0 200 8000 legs. Camera pose at rest before and
after each leg; TLM FULL through each leg with completion detected by
STATUS polling; camera geofence (ESTOP) checked on every poll.
Usage: g3_run.py host:port lag stop_distance rotational_slip
"""
import sys, time, math, json, statistics, re
sys.path.insert(0, 'tools')
from wire_acceptance import TcpLink
from camlink import Cam

OUT = 'captures/bench-acceptance-029-20260904d/'
LIMX = 55.0                  # [cm] usable envelope (12 cm margin)
YMIN, YMAX = 8.0, 33.0       # [cm] NORTH corridor only (stakeholder 2026-09-04 12:50)
HARDX, HARDYN, HARDYS = 61.0, 40.0, 3.0   # [cm] ESTOP lines
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

def run_move(cmd, limit=10.0, geofence=True):
    """Send a sequenced move; poll STATUS until active 1->0; camera geofence."""
    global sid
    sid += 1; cmd = f'{cmd} #{sid}'
    t0 = time.time(); L.s.sendall(cmd.encode() + b'\n')
    lines = []; seen1 = False; tdone = None; reason = None; estop = False
    while time.time() - t0 < limit:
        got = L.read(0.12); lines += got
        for l in got:
            if l.startswith('status '):
                a = re.search(r'active=(\d)', l).group(1); rs = re.search(r'reason=(\w+)', l).group(1)
                if a == '1': seen1 = True
                if seen1 and a == '0' and tdone is None: tdone = round(time.time() - t0, 2); reason = rs
        if tdone is not None and time.time() - t0 > tdone + 0.6: break
        if geofence:
            r = one()
            if r and (abs(r[0]) > HARDX or r[1] > HARDYN or r[1] < HARDYS):
                L.s.sendall(b'ESTOP\n'); estop = True
                print(f'!!! GEOFENCE ESTOP at ({r[0]:.1f},{r[1]:.1f})'); break
        L.s.sendall(b'STATUS\n')
    LOG.append((cmd, {'done_s': tdone, 'reason': reason, 'estop': estop}))
    return {'cmd': cmd, 'done_s': tdone, 'reason': reason, 'estop': estop, 'frames': frames_from(lines)}

def face(target_deg):
    for attempt in range(3):
        p = pose(); d = (target_deg - p[2] + 180) % 360 - 180
        print(f'face {target_deg}: at {p[2]:.1f}, delta {d:+.1f}')
        if abs(d) <= 2.5: return p
        r = run_move(f'MOVE_X 0 {int(round(math.radians(d)*1000))} 100 6000', geofence=False)
        time.sleep(0.6)
    return pose()

def projected_ok(p, dist_cm):
    ex = p[0] + dist_cm*math.cos(math.radians(p[2])); ey = p[1] + dist_cm*math.sin(math.radians(p[2]))
    return abs(ex) <= LIMX and YMIN <= ey <= YMAX, (ex, ey)

ask('HELLO', seq=False); ask('RUN:clearestop', seq=False); ask('STATUS', seq=False)
for c in ('SET accel 400', 'SET decel 400', 'SET twist_hold_gain 2', f'SET lag {sys.argv[2]}',
          f'SET stop_distance {sys.argv[3]}', f'SET rotational_slip {sys.argv[4]}',
          'GET lag', 'GET stop_distance', 'GET rotational_slip', 'GET v_floor', 'GET v_max'):
    ask(c)

p = pose(); print('start pose', p)
if not (YMIN <= p[1] <= YMAX): raise SystemExit('not in the north corridor')
# start at the west end so a +600 leg fits: go to (-45, 20)
if p[0] > -35:
    brg = math.degrees(math.atan2(20 - p[1], -45 - p[0])); face(brg)
    p = pose(); dist = math.hypot(-45 - p[0], 20 - p[1]); ok, e = projected_ok(p, dist)
    print(f'reposition {dist:.1f} cm on {p[2]:.0f} -> {e} ok={ok}')
    if not ok: raise SystemExit('reposition leaves the corridor')
    run_move(f'MOVE_X {int(round(dist*10))} 0 150 10000'); time.sleep(0.6)
p = face(0.0); print('legs start pose', p)

ask('TLM FULL', 0.4)
legs = []; sign = 1
NLEGS = int(sys.argv[5]) if len(sys.argv) > 5 else 6
for i in range(NLEGS):
    p0 = pose()
    ok, e = projected_ok(p0, sign*60.0)
    print(f'leg {i} from ({p0[0]:.1f},{p0[1]:.1f},{p0[2]:.1f}) {sign*600:+d} mm -> projected ({e[0]:.1f},{e[1]:.1f}) ok={ok}')
    if not ok:
        # re-centre in the corridor: face north/south, short move to y=-20, face back
        print('leg would leave the corridor -- re-centring to y=20')
        ask('TLM OFF', 0.4); L.read(0.3)
        dy_cm = 20.0 - p0[1]
        face(90.0 if dy_cm > 0 else -90.0)
        run_move(f'MOVE_X {int(round(abs(dy_cm)*10))} 0 120 6000'); time.sleep(0.6)
        face(0.0 if sign > 0 else 180.0)
        ask('TLM FULL', 0.4)
        p0 = pose(); ok, e = projected_ok(p0, sign*60.0)
        print(f'leg {i} from ({p0[0]:.1f},{p0[1]:.1f},{p0[2]:.1f}) {sign*600:+d} mm -> projected ({e[0]:.1f},{e[1]:.1f}) ok={ok}')
        if not ok:
            print('still outside -- stopping the legs here'); break
    pre = frames_from(L.read(0.4))
    mv = run_move(f'MOVE_X {sign*600} 0 200 8000')
    time.sleep(0.6)
    post = frames_from(L.read(0.4))
    p1 = pose()
    fr = mv['frames'] + post
    dx, dy = p1[0]-p0[0], p1[1]-p0[1]
    cam_len = math.hypot(dx, dy) * 10  # [mm]
    brg = math.degrees(math.atan2(dy, dx)); want = p0[2] if sign > 0 else p0[2] + 180
    lateral = cam_len * math.sin(math.radians((brg - want + 180) % 360 - 180))
    dh = (p1[2] - p0[2] + 180) % 360 - 180
    odo_len = (math.hypot(fr[-1]['x']-pre[-1]['x'], fr[-1]['y']-pre[-1]['y']) if pre and fr else None)
    moving = [f for f in fr if f['vl'] or f['vr']]
    vmean = [0.5*(f['vl']+f['vr']) for f in moving]
    peak = max((max(abs(f['vl']), abs(f['vr'])) for f in fr), default=None)
    first_v = abs(vmean[0]) if vmean else None
    # accel/jerk from frames (mean wheel speed, frame dt)
    dvdt = []
    for a, b in zip(moving, moving[1:]):
        dt = (b['now'] - a['now'])/1000.0
        if dt > 0: dvdt.append((0.5*(b['vl']+b['vr']) - 0.5*(a['vl']+a['vr']))/dt)
    tail = [abs(v) for v in vmean[-10:]]
    monotone = all(b <= a + 8 for a, b in zip(tail, tail[1:]))  # 8 mm/s encoder quantum slack
    end_decel = min(dvdt[-10:]) if sign > 0 else -max(dvdt[-10:]) if dvdt else None
    row = {'i': i, 'sign': sign, 'p0': p0, 'p1': p1, 'cam_len_mm': cam_len, 'odo_len_mm': odo_len, 'lateral_mm': lateral,
           'dheading_deg': dh, 'done_s': mv['done_s'], 'reason': mv['reason'], 'estop': mv['estop'], 'peak_v': peak,
           'first_moving_v': first_v, 'max_accel': max(dvdt) if dvdt else None, 'min_accel': min(dvdt) if dvdt else None,
           'tail_monotone': monotone, 'tail_v': tail, 'frames': fr}
    legs.append(row)
    print(f'  cam {cam_len:.0f} mm (err {cam_len-600:+.0f}) odo {odo_len and round(odo_len)} lateral {lateral:+.0f} mm dh {dh:+.2f} '
          f'done {mv["done_s"]}s {mv["reason"]} peak {peak} first {first_v} accel[{min(dvdt) if dvdt else None:.0f},{max(dvdt) if dvdt else None:.0f}] tail_monotone={monotone} tail={tail}')
    if mv['estop']: break
    sign = -sign
ask('TLM OFF', 0.4); L.read(0.4); ask('STATUS', seq=False); L.close()
if legs:
    errs = [l['cam_len_mm'] - 600 for l in legs]
    print(f'G3: leg length err mean {statistics.mean(errs):+.1f} mm sd {statistics.pstdev(errs):.1f} max|err| {max(abs(e) for e in errs):.0f}; '
          f'peak v max {max(l["peak_v"] for l in legs)}; tail monotone {sum(1 for l in legs if l["tail_monotone"])}/{len(legs)}; '
          f'lateral mean {statistics.mean(l["lateral_mm"] for l in legs):+.0f} mm; dh mean {statistics.mean(l["dheading_deg"] for l in legs):+.2f}')
    print(f'G4: first moving v {[l["first_moving_v"] for l in legs]}; max accel {[round(l["max_accel"]) for l in legs]}; min accel {[round(l["min_accel"]) for l in legs]}')
json.dump({'args': sys.argv[1:], 'legs': legs, 'log': LOG}, open(OUT + (sys.argv[6] if len(sys.argv) > 6 else 'g3-run.json'), 'w'), indent=1)
